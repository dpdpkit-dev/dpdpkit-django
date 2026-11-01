"""Django admin: a request queue with SLA countdowns, a read-only ledger viewer and a retention monitor.

Registered automatically when ``django.contrib.admin`` is installed (the admin autodiscovers this module)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.utils import timezone
from django.utils.html import format_html
from dpdpkit.models import OPEN_REQUEST_STATUSES, ErasureSchedule, RightsRequest, ScheduleStatus

from .models import AuditRow, ConsentEventRow, HoldRow, RequestRow, ScheduleRow

_UPCOMING = {ScheduleStatus.SCHEDULED.value, ScheduleStatus.WARNING_PENDING.value, ScheduleStatus.WARNED.value}


def _aware(value: dt.datetime) -> dt.datetime:
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def format_remaining(delta: dt.timedelta) -> str:
    """``"3d 4h left"`` or ``"2d 1h overdue"``."""
    seconds = int(delta.total_seconds())
    overdue = seconds < 0
    seconds = abs(seconds)
    days, rest = divmod(seconds, 86400)
    hours = rest // 3600
    text = f"{days}d {hours}h" if days else f"{hours}h {rest % 3600 // 60}m"
    return f"{text} overdue" if overdue else f"{text} left"


class _ReadOnlyAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """No add, change or delete: ledger rows are append-only and hash-chained."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(RequestRow)
class RightsRequestAdmin(_ReadOnlyAdmin):
    """The request queue, most urgent first, with an SLA countdown per open request."""

    list_display = ("id", "tenant_id", "principal", "kind", "status", "assignee", "due_at", "sla")
    list_filter = ("tenant_id", "status")
    search_fields = ("id", "principal")
    ordering = ("opened_at",)

    def _req(self, obj: RequestRow) -> RightsRequest:
        return RightsRequest.model_validate(obj.doc)

    @admin.display(description="Kind")
    def kind(self, obj: RequestRow) -> str:
        return str(self._req(obj).kind.value)

    @admin.display(description="Assignee")
    def assignee(self, obj: RequestRow) -> str:
        return self._req(obj).assignee or "-"

    @admin.display(description="Due")
    def due_at(self, obj: RequestRow) -> dt.datetime:
        return self._req(obj).due_at

    @admin.display(description="SLA")
    def sla(self, obj: RequestRow) -> str:
        req = self._req(obj)
        if req.status not in OPEN_REQUEST_STATUSES:
            return "closed"
        delta = _aware(req.due_at) - timezone.now()
        text = format_remaining(delta)
        if _aware(req.max_due_at) < timezone.now():
            text += " (ceiling breached)"
        colour = "#b00020" if delta.total_seconds() < 0 else "inherit"
        return format_html('<span style="color:{}">{}</span>', colour, text)


@admin.register(ConsentEventRow)
class ConsentLedgerAdmin(_ReadOnlyAdmin):
    list_display = ("tenant_id", "seq", "principal", "purpose", "action", "notice_version", "occurred_at", "hash")
    list_filter = ("tenant_id", "action", "purpose")
    search_fields = ("principal", "hash")
    ordering = ("tenant_id", "-seq")


@admin.register(AuditRow)
class AuditLedgerAdmin(_ReadOnlyAdmin):
    list_display = ("tenant_id", "seq", "actor", "action", "subject_type", "subject_id", "occurred_at", "hash")
    list_filter = ("tenant_id", "action", "subject_type")
    search_fields = ("actor", "subject_id", "hash")
    ordering = ("tenant_id", "-seq")


@admin.register(ScheduleRow)
class RetentionMonitorAdmin(_ReadOnlyAdmin):
    """Upcoming erasures, failed warnings and schedules needing attention."""

    list_display = ("id", "tenant_id", "principal", "purpose", "status", "warn_at", "erase_at", "erasure_in", "note")
    list_filter = ("tenant_id", "status", "purpose")
    search_fields = ("id", "principal")
    ordering = ("erase_at",)

    def _sch(self, obj: ScheduleRow) -> ErasureSchedule:
        return ErasureSchedule.model_validate(obj.doc)

    @admin.display(description="Erasure")
    def erasure_in(self, obj: ScheduleRow) -> str:
        if obj.status not in _UPCOMING:
            return "-"
        return format_remaining(_aware(obj.erase_at) - timezone.now()).replace("overdue", "past due")

    @admin.display(description="Note")
    def note(self, obj: ScheduleRow) -> str:
        sch = self._sch(obj)
        return sch.attention_reason or sch.cancelled_reason or "-"


@admin.register(HoldRow)
class LegalHoldAdmin(_ReadOnlyAdmin):
    list_display = ("id", "tenant_id", "principal", "active", "purpose", "reason", "placed_by")
    list_filter = ("tenant_id", "active")
    search_fields = ("principal", "id")

    def _doc(self, obj: HoldRow, key: str) -> str:
        return str(obj.doc.get(key) or "-")

    @admin.display(description="Purpose")
    def purpose(self, obj: HoldRow) -> str:
        return self._doc(obj, "purpose") if obj.doc.get("purpose") else "all purposes"

    @admin.display(description="Reason")
    def reason(self, obj: HoldRow) -> str:
        return self._doc(obj, "reason")

    @admin.display(description="Placed by")
    def placed_by(self, obj: HoldRow) -> str:
        return self._doc(obj, "placed_by")
