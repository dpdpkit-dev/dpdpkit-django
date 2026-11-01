from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Any

import pytest
import yaml
from django.template import Context, Template
from django.test import RequestFactory

from dpdpkit import Kit, kit_from_config, sync_notice
from dpdpkit.config import STARTER_CONFIG
from dpdpkit.django import conf
from dpdpkit.django.consent import record_preferences
from dpdpkit.django.http import Unauthenticated
from dpdpkit.django.repository import DjangoRepository
from dpdpkit.django.signals import connect_kit, consent_withdrawn, erasure_due, request_opened
from dpdpkit.models import ConsentStatus, Contact, RequestKind
from dpdpkit.notify import MemoryNotifier

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


class Catcher:
    def __init__(self, signal: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self.signal = signal
        signal.connect(self, weak=False)

    def __call__(self, sender: Any, **kwargs: Any) -> None:
        self.calls.append(kwargs)

    def close(self) -> None:
        self.signal.disconnect(self)


@pytest.fixture
def caught() -> Iterator[dict[str, Catcher]]:
    c = {"withdrawn": Catcher(consent_withdrawn), "due": Catcher(erasure_due), "opened": Catcher(request_opened)}
    yield c
    for catcher in c.values():
        catcher.close()


def test_consent_withdrawn_signal(kit: Kit, caught: dict[str, Catcher]) -> None:
    kit.consent.record("u1", {"marketing": True}, source="test")
    assert caught["withdrawn"].calls == []
    kit.consent.withdraw("u1", "marketing", source="test")
    (call,) = caught["withdrawn"].calls
    assert call["principal"] == "u1" and call["purpose"] == "marketing" and call["tenant_id"] == "default"
    assert call["event"].type == "consent.withdrawn"


def test_request_opened_signal(kit: Kit, caught: dict[str, Catcher]) -> None:
    kit.rights.open("u1", RequestKind.ERASURE, {})
    (call,) = caught["opened"].calls
    assert call["principal"] == "u1" and call["kind"] == "erasure" and call["request_id"]


def test_erasure_due_signal(kit: Kit, caught: dict[str, Catcher]) -> None:
    kit.consent.record("u1", {"marketing": True}, source="test")
    kit.consent.withdraw("u1", "marketing", source="test")
    kit.notifier = MemoryNotifier()
    kit.contact_resolver = lambda principal: Contact(email="u1@example.in")
    kit.retention.run(kit.now() + dt.timedelta(days=1))  # sends the warning
    kit.retention.run(kit.now() + dt.timedelta(days=60))
    assert [c["purpose"] for c in caught["due"].calls] == ["marketing"]


def test_failing_receiver_does_not_block_others(kit: Kit, caught: dict[str, Catcher]) -> None:
    def boom(sender: Any, **kwargs: Any) -> None:
        raise RuntimeError("nope")

    consent_withdrawn.connect(boom, weak=False)
    try:
        kit.consent.record("u1", {"marketing": True}, source="test")
        kit.consent.withdraw("u1", "marketing", source="test")
    finally:
        consent_withdrawn.disconnect(boom)
    assert len(caught["withdrawn"].calls) == 1


def test_connect_kit_is_idempotent(kit: Kit, caught: dict[str, Catcher]) -> None:
    connect_kit(kit)
    connect_kit(kit)
    kit.consent.record("u1", {"marketing": True}, source="test")
    kit.consent.withdraw("u1", "marketing", source="test")
    assert len(caught["withdrawn"].calls) == 1


def render(source: str, who: str | None = "u1") -> str:
    request = rf.get("/", **({"HTTP_X_PRINCIPAL": who} if who else {}))
    return Template("{% load dpdpkit %}" + source).render(Context({"request": request, "csrf_token": "tok"}))


def test_dpdp_notice_tag() -> None:
    html = render("{% dpdp_notice %}", None)
    assert "How we use your personal data" in html and "Send you offers" in html
    assert 'data-notice-version="1"' in html


def test_dpdp_notice_tag_locale() -> None:
    assert 'lang="hi"' in render('{% dpdp_notice locale="hi" %}', None)


def test_dpdp_preferences_tag_nothing_preticked(kit: Kit) -> None:
    html = render('{% dpdp_preferences action="/prefs/" %}')
    assert 'action="/prefs/"' in html and 'value="marketing"' in html and 'value="tok"' in html
    assert "checked" not in html


def test_dpdp_preferences_tag_shows_granted(kit: Kit) -> None:
    kit.consent.record("u1", {"marketing": True}, source="test")
    html = render("{% dpdp_preferences %}")
    assert 'value="marketing" checked' in html


def test_dpdp_preferences_tag_anonymous_renders_nothing() -> None:
    assert render("{% dpdp_preferences %}", None).strip() == ""


def test_record_preferences_grant_then_withdraw(kit: Kit) -> None:
    post = rf.post("/", {"purpose": ["marketing"], "notice_version": "1", "locale": "en"}, HTTP_X_PRINCIPAL="u1")
    states = {s.purpose: s.status for s in record_preferences(post)}
    assert states["marketing"] is ConsentStatus.GRANTED
    post = rf.post("/", {"notice_version": "1"}, HTTP_X_PRINCIPAL="u1")
    states = {s.purpose: s.status for s in record_preferences(post)}
    assert states["marketing"] is ConsentStatus.WITHDRAWN


def test_record_preferences_requires_sign_in() -> None:
    with pytest.raises(Unauthenticated):
        record_preferences(rf.post("/", {}))
