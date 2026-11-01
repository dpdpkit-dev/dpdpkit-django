from __future__ import annotations

import datetime as dt

import pytest
import yaml
from django.core.management import call_command
from django.db import connection

from dpdpkit import Contact, Kit, LedgerTampered, MemoryNotifier, kit_from_config, sync_notice
from dpdpkit.config import STARTER_CONFIG
from dpdpkit.django.models import ConsentEventRow
from dpdpkit.django.repository import DjangoRepository
from dpdpkit.errors import SequenceConflict
from dpdpkit.models import ScheduleStatus
from dpdpkit.repository import Repository

pytestmark = pytest.mark.django_db(transaction=True)

T0 = dt.datetime(2027, 6, 1, 9, 0, 0, 123456, tzinfo=dt.timezone.utc)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> dt.datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def repo() -> DjangoRepository:
    return DjangoRepository()


@pytest.fixture
def kit(repo: DjangoRepository, clock: Clock) -> Kit:
    cfg = yaml.safe_load(STARTER_CONFIG)
    k = kit_from_config(
        cfg,
        repo,
        notifier=MemoryNotifier(),
        clock=clock,
        signing_key="k",
        contact_resolver=lambda p: Contact(email=f"{p}@example.in"),
    )
    sync_notice(k, cfg)
    return k


def test_implements_repository_protocol(repo: DjangoRepository) -> None:
    assert isinstance(repo, Repository)


def test_migrations_match_models() -> None:
    call_command("makemigrations", "dpdpkit", check=True, dry_run=True, verbosity=0)


def test_ledger_roundtrip_keeps_hashes_valid(kit: Kit) -> None:
    kit.consent.grant("u1", "marketing")
    kit.consent.withdraw("u1", "marketing")
    kit.rights.open("u1", "access")
    result = kit.ledger.verify()
    assert result.ok and result.checked >= 3
    [first, _second] = kit.repository.list_consent_events(kit.tenant_id)
    assert first.occurred_at == T0 and first.occurred_at.tzinfo is not None


def test_tamper_is_detected_and_names_the_row(kit: Kit) -> None:
    kit.consent.grant("u1", "marketing")
    kit.consent.grant("u2", "marketing")
    target = kit.repository.list_consent_events(kit.tenant_id)[0]
    ConsentEventRow.objects.filter(id=target.id).update(action="deny")
    with pytest.raises(LedgerTampered) as exc:
        kit.ledger.verify()
    assert exc.value.row_id == target.id


def test_row_deletion_is_detected(kit: Kit) -> None:
    for p in ("u1", "u2", "u3"):
        kit.consent.grant(p, "marketing")
    middle = kit.repository.list_consent_events(kit.tenant_id)[1]
    ConsentEventRow.objects.filter(id=middle.id).delete()
    report = kit.ledger.verify_report()
    assert not report.ok and "seq" in (report.reason or "")


def test_duplicate_sequence_raises_conflict(kit: Kit) -> None:
    kit.consent.grant("u1", "marketing")
    event = kit.repository.last_consent_event(kit.tenant_id)
    assert event is not None
    with pytest.raises(SequenceConflict):
        kit.repository.append_consent_event(event.model_copy(update={"id": "ce_dup"}))
    with kit.repository.transaction():  # a conflict inside a transaction must not poison it
        with pytest.raises(SequenceConflict):
            kit.repository.append_consent_event(event.model_copy(update={"id": "ce_dup2"}))
        kit.consent.grant("u2", "marketing")
    kit.ledger.verify()


def test_transaction_rolls_back_together(kit: Kit) -> None:
    with pytest.raises(RuntimeError), kit.repository.transaction():
        kit.consent.grant("u1", "marketing")
        raise RuntimeError("boom")
    assert kit.repository.list_consent_events(kit.tenant_id) == []


def test_retention_flow(kit: Kit, clock: Clock) -> None:
    erased: list[str] = []
    kit.retention.register_handler(lambda p, purposes: erased.append(p))
    kit.consent.grant("u1", "marketing")
    kit.consent.withdraw("u1", "marketing")
    kit.retention.run()
    [s] = kit.retention.schedules("u1")
    assert s.status is ScheduleStatus.WARNED
    clock.now += dt.timedelta(hours=48)
    assert kit.retention.run().erased == 1
    assert erased == ["u1"]


def test_ist_schedule_times_compare_correctly(kit: Kit, clock: Clock) -> None:
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    erase_at = (T0 + dt.timedelta(days=5)).astimezone(ist)
    kit.retention.schedule("u1", "marketing", erase_at, reason="test", actor="t")
    clock.now = erase_at - dt.timedelta(hours=48, minutes=1)
    assert kit.repository.due_erasures(kit.tenant_id, clock.now) == []
    clock.now += dt.timedelta(minutes=2)
    assert len(kit.repository.due_erasures(kit.tenant_id, clock.now)) == 1


def test_holds_activity_and_nominees(kit: Kit) -> None:
    hold = kit.retention.place_hold("u1", "audit", actor="dpo")
    assert [h.id for h in kit.retention.holds("u1")] == [hold.id]
    kit.retention.release_hold(hold.id, actor="dpo")
    assert kit.retention.holds("u1") == []
    kit.retention.record_activity("u1")
    assert kit.repository.last_activity(kit.tenant_id, "u1") == T0
    kit.rights.open("u1", "nomination", {"name": "A", "contact": "a@example.in"})
    assert len(kit.rights.nominees("u1")) == 1


def test_tables_use_shared_names() -> None:
    assert {"dpdp_consent_events", "dpdp_audit", "dpdp_notices", "dpdp_requests"} <= set(
        connection.introspection.table_names()
    )
