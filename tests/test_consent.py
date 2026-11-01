from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

import pytest
import yaml
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.test import RequestFactory
from django.views import View

from dpdpkit import Kit, kit_from_config, sync_notice
from dpdpkit.config import STARTER_CONFIG
from dpdpkit.django import conf
from dpdpkit.django.consent import RequiresConsentMixin, requires_consent
from dpdpkit.django.repository import DjangoRepository
from dpdpkit.errors import DpdpkitError

pytestmark = pytest.mark.django_db(transaction=True)

rf = RequestFactory()


@pytest.fixture(autouse=True)
def kit() -> Iterator[Kit]:
    cfg = yaml.safe_load(STARTER_CONFIG)
    k = kit_from_config(cfg, DjangoRepository(), signing_key="k")
    sync_notice(k, cfg)
    conf.set_kit(k)
    yield k
    conf.set_kit(None)


def get(who: str | None = "u1") -> HttpRequest:
    return rf.get("/", **({"HTTP_X_PRINCIPAL": who} if who else {}))


@requires_consent("marketing")
def offer(request: HttpRequest, name: str = "x") -> HttpResponse:
    return HttpResponse(f"offer {name}")


class OfferView(RequiresConsentMixin, View):
    consent_purposes = ("marketing",)

    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("offer")


def error(response: HttpResponse) -> dict[str, object]:
    body: dict[str, dict[str, object]] = json.loads(response.content)
    return body["error"]


def test_anonymous_gets_401(kit: Kit) -> None:
    r = offer(get(None))
    assert r.status_code == 401 and error(r)["code"] == "unauthenticated"


def test_without_consent_gets_403_with_the_purpose(kit: Kit) -> None:
    r = offer(get())
    assert r.status_code == 403
    assert error(r)["code"] == "consent_required" and error(r)["details"] == {"purpose": "marketing"}


def test_granted_runs_the_view_then_withdrawal_blocks_it(kit: Kit) -> None:
    kit.consent.record("u1", {"marketing": True}, source="test")
    r = offer(get(), name="kwarg")
    assert r.status_code == 200 and r.content == b"offer kwarg"
    kit.consent.withdraw("u1", "marketing", source="test")
    assert offer(get()).status_code == 403


def test_consent_is_per_principal(kit: Kit) -> None:
    kit.consent.record("u1", {"marketing": True}, source="test")
    assert offer(get("u2")).status_code == 403


def test_every_purpose_is_required(kit: Kit) -> None:
    both = requires_consent("account", "marketing")(lambda request: HttpResponse("ok"))
    kit.consent.record("u1", {"account": True}, source="test")
    r = both(get())
    assert r.status_code == 403 and error(r)["details"] == {"purpose": "marketing"}
    kit.consent.record("u1", {"marketing": True}, source="test")
    assert both(get()).status_code == 200


def test_unknown_purpose_is_a_programming_error(kit: Kit) -> None:
    with pytest.raises(DpdpkitError):
        requires_consent("no_such_purpose")(lambda request: HttpResponse("ok"))(get())


def test_on_denied_replaces_the_response(kit: Kit) -> None:
    view = requires_consent("marketing", on_denied=lambda request, exc: HttpResponseRedirect("/consent/"))(offer)
    r = view(get())
    assert r.status_code == 302 and r["Location"] == "/consent/"


def test_decorator_needs_a_purpose() -> None:
    with pytest.raises(ValueError):
        requires_consent()


def test_decorator_keeps_the_view_name() -> None:
    assert offer.__name__ == "offer"


def test_async_view(kit: Kit) -> None:
    @requires_consent("marketing")
    async def aoffer(request: HttpRequest) -> HttpResponse:
        return HttpResponse("async offer")

    assert asyncio.run(aoffer(get())).status_code == 403  # type: ignore[arg-type]
    kit.consent.record("u1", {"marketing": True}, source="test")
    r = asyncio.run(aoffer(get()))  # type: ignore[arg-type]
    assert r.status_code == 200 and r.content == b"async offer"


def test_mixin(kit: Kit) -> None:
    view = OfferView.as_view()
    assert view(get(None)).status_code == 401
    assert view(get()).status_code == 403
    kit.consent.record("u1", {"marketing": True}, source="test")
    assert view(get()).content == b"offer"


def test_mixin_consent_denied_override(kit: Kit) -> None:
    class Redirecting(OfferView):
        def consent_denied(self, request: HttpRequest, error: DpdpkitError) -> HttpResponse:
            return HttpResponseRedirect("/consent/")

    assert Redirecting.as_view()(get()).status_code == 302


def test_mixin_needs_purposes() -> None:
    class Bare(RequiresConsentMixin, View):
        pass

    with pytest.raises(ValueError):
        Bare.as_view()(get())
