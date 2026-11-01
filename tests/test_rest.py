from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
import yaml
from django.conf import settings
from django.test import Client
from django.test.utils import override_settings

from dpdpkit import Contact, Kit, MemoryNotifier, kit_from_config, sync_notice
from dpdpkit.config import STARTER_CONFIG
from dpdpkit.django import conf
from dpdpkit.django.repository import DjangoRepository

pytestmark = pytest.mark.django_db(transaction=True)

USER = {"HTTP_X_PRINCIPAL": "u1"}


def admin(role: str = "admin", who: str = "ops") -> dict[str, str]:
    return {"HTTP_X_ROLE": role, "HTTP_X_PRINCIPAL": who}


@pytest.fixture(autouse=True)
def kit() -> Iterator[Kit]:
    cfg = yaml.safe_load(STARTER_CONFIG)
    k = kit_from_config(
        cfg,
        DjangoRepository(),
        notifier=MemoryNotifier(),
        signing_key="k",
        contact_resolver=lambda p: Contact(email=f"{p}@example.in"),
    )
    sync_notice(k, cfg)
    conf.set_kit(k)
    yield k
    conf.set_kit(None)


@pytest.fixture(params=["tests.urls_plain", "tests.urls_drf"])
def client(request: pytest.FixtureRequest) -> Iterator[Client]:
    with override_settings(ROOT_URLCONF=request.param):
        yield Client()


def post(client: Client, url: str, body: Any, **extra: str) -> Any:
    return client.post(url, json.dumps(body), content_type="application/json", **extra)


def test_current_notice_is_public_and_others_need_sign_in(client: Client) -> None:
    r = client.get("/dpdp/notices/current")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 1 and body["available_locales"]
    assert client.get("/dpdp/consents/me").status_code == 401


def test_grant_withdraw_and_state(client: Client) -> None:
    r = post(client, "/dpdp/consents", {"decisions": [{"purpose": "marketing", "granted": True}]}, **USER)
    assert r.status_code == 201
    assert [c["purpose"] for c in r.json()["consents"]] == ["marketing"]
    assert client.get("/dpdp/consents/me", **USER).json()["consents"][0]["status"] == "granted"
    r = post(client, "/dpdp/consents/marketing/withdraw", {}, **USER)
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"
    assert "consents" in client.get("/dpdp/consents/me/receipt", **USER).json()


def test_error_bodies_follow_the_contract(client: Client) -> None:
    r = post(client, "/dpdp/consents", {"decisions": []}, **USER)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request" and r.json()["error"]["details"]["errors"]
    r = client.post("/dpdp/consents", "{nope", content_type="application/json", **USER)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    dup = {"decisions": [{"purpose": "marketing", "granted": True}, {"purpose": "marketing", "granted": False}]}
    assert post(client, "/dpdp/consents", dup, **USER).status_code == 422
    r = client.get("/dpdp/requests/missing", **USER)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.delete("/dpdp/consents/me", **USER)
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"


def test_rights_request_roundtrip_and_privacy_of_fields(client: Client) -> None:
    r = post(client, "/dpdp/requests", {"kind": "access"}, **USER)
    assert r.status_code == 201
    req = r.json()
    assert "principal" not in req and req["overdue"] is False
    assert client.get(f"/dpdp/requests/{req['id']}", **USER).status_code == 200
    assert client.get(f"/dpdp/requests/{req['id']}", HTTP_X_PRINCIPAL="u2").status_code == 404
    assert [i["id"] for i in client.get("/dpdp/requests", **USER).json()["items"]] == [req["id"]]
    assert post(client, "/dpdp/requests", {"kind": "bogus"}, **USER).status_code == 422


def test_export_formats(client: Client) -> None:
    assert "text/html" in client.get("/dpdp/me/export?format=html", **USER)["Content-Type"]
    assert client.get("/dpdp/me/export", **USER).status_code == 200
    assert client.get("/dpdp/me/export?format=xml", **USER).status_code == 422


def test_admin_roles(client: Client) -> None:
    assert client.get("/dpdp/admin/requests").status_code == 401
    assert client.get("/dpdp/admin/requests", **USER).status_code == 403
    assert client.get("/dpdp/admin/requests", **admin("viewer")).status_code == 200
    r = post(client, "/dpdp/admin/ledger/verify", {}, **admin("viewer"))
    assert r.status_code == 200 and r.json()["ok"] is True
    assert client.get("/dpdp/admin/audit/export", **admin("handler")).status_code == 403
    r = client.get("/dpdp/admin/audit/export", **admin("admin"))
    assert r.status_code == 200 and r["Content-Type"] == "application/zip" and "attachment" in r["Content-Disposition"]


def test_admin_request_workflow(client: Client) -> None:
    req = post(client, "/dpdp/requests", {"kind": "access"}, **USER).json()
    url = f"/dpdp/admin/requests/{req['id']}"
    assert client.get(url, **admin("viewer")).json()["principal"] == "u1"
    r = client.patch(url, json.dumps({"action": "assign", "assignee": "ops"}), "application/json", **admin("viewer"))
    assert r.status_code == 403
    r = client.patch(url, json.dumps({"action": "assign"}), "application/json", **admin("handler"))
    assert r.status_code == 422
    r = client.patch(url, json.dumps({"action": "assign", "assignee": "ops"}), "application/json", **admin("handler"))
    assert r.status_code == 200 and r.json()["assignee"] == "ops"
    r = client.get("/dpdp/admin/requests?open=true&status=received", **admin("viewer"))
    assert r.status_code == 200
    assert client.get("/dpdp/admin/requests?status=nope", **admin("viewer")).status_code == 422


def test_retention_preview_activity_and_incident_stubs(client: Client) -> None:
    r = client.get("/dpdp/admin/retention/preview?hours=24", **admin("viewer"))
    assert r.status_code == 200 and set(r.json()) == {"items", "needs_attention"}
    assert client.get("/dpdp/admin/retention/preview?hours=0", **admin("viewer")).status_code == 422
    assert post(client, "/dpdp/events/activity", {"principal": "u1"}, **admin("handler")).status_code == 202
    assert post(client, "/dpdp/events/activity", {"principal": "u1"}, **USER).status_code == 403
    r = client.get("/dpdp/admin/incidents", **admin("viewer"))
    assert r.status_code == 501 and r.json()["error"]["code"] == "not_implemented"


def test_plain_views_enforce_csrf_unless_exempt() -> None:
    with override_settings(ROOT_URLCONF="tests.urls_plain"):
        csrf = Client(enforce_csrf_checks=True)
        body = {"decisions": [{"purpose": "marketing", "granted": True}]}
        assert post(csrf, "/dpdp/consents", body, **USER).status_code == 403


def test_include_picks_drf_when_installed() -> None:
    from dpdpkit.django import urls

    assert urls._use_drf() is True
    with override_settings(DPDPKIT={**settings.DPDPKIT, "DRF": False}):
        assert urls._use_drf() is False
    with override_settings(ROOT_URLCONF="tests.urls_auto"):
        assert Client().get("/dpdp/notices/current", **USER).status_code == 200


def test_kit_from_settings() -> None:
    conf.set_kit(None)
    with override_settings(DPDPKIT={"POLICY": "dpdp-rules-2025.v1", "TENANT_ID": "acme"}):
        assert conf.get_kit().tenant_id == "acme"
    conf.set_kit(None)
    with override_settings(DPDPKIT={}):
        with pytest.raises(Exception, match="DPDPKIT"):
            conf.get_kit()


def test_default_hooks_use_the_django_user() -> None:
    class User:
        pk = 7
        is_authenticated = True
        is_superuser = False
        is_staff = True

    class Req:
        user = User()

    with override_settings(DPDPKIT={}):
        assert conf.resolve_principal(Req()) == "7"  # type: ignore[arg-type]
        role = conf.resolve_role(Req())  # type: ignore[arg-type]
        assert role is not None and role.value == "handler"
