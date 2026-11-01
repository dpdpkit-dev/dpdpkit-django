"""``DjangoRepository``: dpdpkit-core's Repository on the Django ORM (Postgres, MySQL, SQLite)."""

from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import Collection, Iterator
from typing import Any, TypeVar

from pydantic import BaseModel

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, IntegrityError, transaction
from dpdpkit._util import as_utc
from dpdpkit.errors import SequenceConflict
from dpdpkit.models import (
    ACTIVE_SCHEDULE_STATUSES,
    AuditEntry,
    ConsentAction,
    ConsentEvent,
    DeliveryReceipt,
    ErasureSchedule,
    LegalHold,
    Nominee,
    Notice,
    RequestStatus,
    RightsRequest,
    ScheduleStatus,
)

from .models import (
    ActivityRow,
    AuditRow,
    ConsentEventRow,
    DeliveryRow,
    HoldRow,
    NomineeRow,
    NoticeRow,
    RequestRow,
    ScheduleRow,
)

M = TypeVar("M", bound=BaseModel)


def _doc(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _load(cls: type[M], doc: dict[str, Any]) -> M:
    return cls.model_validate(doc)


def _db(value: dt.datetime) -> dt.datetime:
    """The value to store: UTC, and naive when the project runs with ``USE_TZ = False``."""
    utc = as_utc(value)
    return utc if settings.USE_TZ else utc.replace(tzinfo=None)


class DjangoRepository:
    def __init__(self, using: str = DEFAULT_DB_ALIAS) -> None:
        """``using`` is the alias of the database (``settings.DATABASES``) that holds the dpdpkit tables."""
        self.using = using

    @contextlib.contextmanager
    def transaction(self) -> Iterator[None]:
        """Join the app's current transaction if there is one (as a savepoint), otherwise open one."""
        with transaction.atomic(using=self.using):
            yield

    def _qs(self, model: Any) -> Any:
        return model.objects.using(self.using)

    def _insert(self, row: Any, what: str) -> None:
        try:
            with transaction.atomic(using=self.using):  # a savepoint: a conflict must not poison the outer transaction
                row.save(force_insert=True, using=self.using)
        except IntegrityError as exc:
            raise SequenceConflict(f"{what} sequence conflict") from exc

    # ------------------------------------------------------------------ consent ledger

    @staticmethod
    def _event(r: ConsentEventRow) -> ConsentEvent:
        return ConsentEvent(
            tenant_id=r.tenant_id,
            id=r.id,
            seq=r.seq,
            principal=r.principal,
            purpose=r.purpose,
            action=ConsentAction(r.action),
            notice_version=r.notice_version,
            notice_hash=r.notice_hash,
            locale=r.locale,
            source=r.source,
            occurred_at=as_utc(r.occurred_at),
            metadata=r.meta or {},
            prev_hash=r.prev_hash,
            hash=r.hash,
        )

    def append_consent_event(self, e: ConsentEvent) -> None:
        self._insert(
            ConsentEventRow(
                id=e.id,
                tenant_id=e.tenant_id,
                seq=e.seq,
                principal=e.principal,
                purpose=e.purpose,
                action=e.action.value,
                notice_version=e.notice_version,
                notice_hash=e.notice_hash,
                locale=e.locale,
                source=e.source,
                occurred_at=_db(e.occurred_at),
                meta=e.metadata,
                prev_hash=e.prev_hash,
                hash=e.hash,
            ),
            "consent ledger",
        )

    def last_consent_event(self, tenant_id: str) -> ConsentEvent | None:
        row = self._qs(ConsentEventRow).filter(tenant_id=tenant_id).order_by("-seq").first()
        return self._event(row) if row else None

    def latest_consent_event(self, tenant_id: str, principal: str, purpose: str) -> ConsentEvent | None:
        row = (
            self._qs(ConsentEventRow)
            .filter(tenant_id=tenant_id, principal=principal, purpose=purpose)
            .order_by("-seq")
            .first()
        )
        return self._event(row) if row else None

    def list_consent_events(
        self, tenant_id: str, *, principal: str | None = None, after_seq: int = 0, limit: int | None = None
    ) -> list[ConsentEvent]:
        q = self._qs(ConsentEventRow).filter(tenant_id=tenant_id, seq__gt=after_seq)
        if principal is not None:
            q = q.filter(principal=principal)
        q = q.order_by("seq")
        if limit is not None:
            q = q[:limit]
        return [self._event(r) for r in q]

    # ------------------------------------------------------------------ audit

    @staticmethod
    def _audit(r: AuditRow) -> AuditEntry:
        return AuditEntry(
            tenant_id=r.tenant_id,
            id=r.id,
            seq=r.seq,
            actor=r.actor,
            action=r.action,
            subject_type=r.subject_type,
            subject_id=r.subject_id,
            occurred_at=as_utc(r.occurred_at),
            data=r.data or {},
            prev_hash=r.prev_hash,
            hash=r.hash,
        )

    def append_audit(self, a: AuditEntry) -> None:
        self._insert(
            AuditRow(
                id=a.id,
                tenant_id=a.tenant_id,
                seq=a.seq,
                actor=a.actor,
                action=a.action,
                subject_type=a.subject_type,
                subject_id=a.subject_id,
                occurred_at=_db(a.occurred_at),
                data=a.data,
                prev_hash=a.prev_hash,
                hash=a.hash,
            ),
            "audit",
        )

    def last_audit(self, tenant_id: str) -> AuditEntry | None:
        row = self._qs(AuditRow).filter(tenant_id=tenant_id).order_by("-seq").first()
        return self._audit(row) if row else None

    def list_audit(
        self, tenant_id: str, *, subject_id: str | None = None, after_seq: int = 0, limit: int | None = None
    ) -> list[AuditEntry]:
        q = self._qs(AuditRow).filter(tenant_id=tenant_id, seq__gt=after_seq)
        if subject_id is not None:
            q = q.filter(subject_id=subject_id)
        q = q.order_by("seq")
        if limit is not None:
            q = q[:limit]
        return [self._audit(r) for r in q]

    # ------------------------------------------------------------------ notices

    def save_notice(self, notice: Notice) -> None:
        self._qs(NoticeRow).update_or_create(
            tenant_id=notice.tenant_id,
            version=notice.version,
            locale=notice.locale,
            defaults={
                "content_hash": notice.content_hash,
                "published_at": _db(notice.published_at),
                "doc": _doc(notice),
            },
        )

    def list_notices(self, tenant_id: str, *, version: int | None = None) -> list[Notice]:
        q = self._qs(NoticeRow).filter(tenant_id=tenant_id)
        if version is not None:
            q = q.filter(version=version)
        return [_load(Notice, r.doc) for r in q.order_by("version", "locale")]

    # ------------------------------------------------------------------ rights

    def save_request(self, req: RightsRequest) -> None:
        self._qs(RequestRow).update_or_create(
            id=req.id,
            defaults={
                "tenant_id": req.tenant_id,
                "principal": req.principal,
                "status": req.status.value,
                "opened_at": _db(req.opened_at),
                "doc": _doc(req),
            },
        )

    def get_request(self, tenant_id: str, request_id: str) -> RightsRequest | None:
        row = self._qs(RequestRow).filter(tenant_id=tenant_id, id=request_id).first()
        return _load(RightsRequest, row.doc) if row else None

    def list_requests(
        self,
        tenant_id: str,
        *,
        principal: str | None = None,
        statuses: Collection[RequestStatus] | None = None,
    ) -> list[RightsRequest]:
        q = self._qs(RequestRow).filter(tenant_id=tenant_id)
        if principal is not None:
            q = q.filter(principal=principal)
        if statuses is not None:
            q = q.filter(status__in=[st.value for st in statuses])
        return [_load(RightsRequest, r.doc) for r in q.order_by("opened_at")]

    def save_nominee(self, nominee: Nominee) -> None:
        self._qs(NomineeRow).update_or_create(
            id=nominee.id,
            defaults={"tenant_id": nominee.tenant_id, "principal": nominee.principal, "doc": _doc(nominee)},
        )

    def list_nominees(self, tenant_id: str, principal: str) -> list[Nominee]:
        return [_load(Nominee, r.doc) for r in self._qs(NomineeRow).filter(tenant_id=tenant_id, principal=principal)]

    # ------------------------------------------------------------------ retention

    def save_schedule(self, sch: ErasureSchedule) -> None:
        self._qs(ScheduleRow).update_or_create(
            id=sch.id,
            defaults={
                "tenant_id": sch.tenant_id,
                "principal": sch.principal,
                "purpose": sch.purpose,
                "status": sch.status.value,
                "warn_at": _db(sch.warn_at),
                "erase_at": _db(sch.erase_at),
                "doc": _doc(sch),
            },
        )

    def get_schedule(self, tenant_id: str, schedule_id: str) -> ErasureSchedule | None:
        row = self._qs(ScheduleRow).filter(tenant_id=tenant_id, id=schedule_id).first()
        return _load(ErasureSchedule, row.doc) if row else None

    def list_schedules(
        self,
        tenant_id: str,
        *,
        principal: str | None = None,
        statuses: Collection[ScheduleStatus] | None = None,
    ) -> list[ErasureSchedule]:
        q = self._qs(ScheduleRow).filter(tenant_id=tenant_id)
        if principal is not None:
            q = q.filter(principal=principal)
        if statuses is not None:
            q = q.filter(status__in=[st.value for st in statuses])
        return [_load(ErasureSchedule, r.doc) for r in q.order_by("erase_at", "id")]

    def due_erasures(self, tenant_id: str, now: dt.datetime) -> list[ErasureSchedule]:
        from django.db.models import Q

        now = _db(now)
        q = self._qs(ScheduleRow).filter(
            Q(warn_at__lte=now) | Q(erase_at__lte=now),
            tenant_id=tenant_id,
            status__in=[st.value for st in ACTIVE_SCHEDULE_STATUSES],
        )
        return [_load(ErasureSchedule, r.doc) for r in q.order_by("erase_at")]

    def save_hold(self, hold: LegalHold) -> None:
        self._qs(HoldRow).update_or_create(
            id=hold.id,
            defaults={
                "tenant_id": hold.tenant_id,
                "principal": hold.principal,
                "active": hold.released_at is None,
                "doc": _doc(hold),
            },
        )

    def list_holds(self, tenant_id: str, *, principal: str | None = None, active_only: bool = True) -> list[LegalHold]:
        q = self._qs(HoldRow).filter(tenant_id=tenant_id)
        if principal is not None:
            q = q.filter(principal=principal)
        if active_only:
            q = q.filter(active=True)
        return [_load(LegalHold, r.doc) for r in q.order_by("id")]

    def record_activity(self, tenant_id: str, principal: str, at: dt.datetime) -> None:
        with transaction.atomic(using=self.using):
            row, created = (
                self._qs(ActivityRow)
                .select_for_update()
                .get_or_create(tenant_id=tenant_id, principal=principal, defaults={"last_at": _db(at)})
            )
            if not created and as_utc(row.last_at) < as_utc(at):
                row.last_at = _db(at)
                row.save(update_fields=["last_at"], using=self.using)

    def last_activity(self, tenant_id: str, principal: str) -> dt.datetime | None:
        row = self._qs(ActivityRow).filter(tenant_id=tenant_id, principal=principal).first()
        return as_utc(row.last_at) if row else None

    # ------------------------------------------------------------------ notifications

    def save_delivery(self, receipt: DeliveryReceipt) -> None:
        self._qs(DeliveryRow).update_or_create(
            id=receipt.id,
            defaults={"tenant_id": receipt.tenant_id, "created_at": _db(receipt.created_at), "doc": _doc(receipt)},
        )

    def get_delivery(self, tenant_id: str, receipt_id: str) -> DeliveryReceipt | None:
        row = self._qs(DeliveryRow).filter(tenant_id=tenant_id, id=receipt_id).first()
        return _load(DeliveryReceipt, row.doc) if row else None
