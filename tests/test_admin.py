from __future__ import annotations

import datetime as dt

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import Client, RequestFactory
from django.utils import timezone

from dpdpkit.django.admin import RetentionMonitorAdmin, RightsRequestAdmin, format_remaining
from dpdpkit.django.models import AuditRow, ConsentEventRow, RequestRow, ScheduleRow
from dpdpkit.django.repository import DjangoRepository
from dpdpkit.models import ErasureSchedule, RequestKind, RequestStatus, RetentionTrigger, RightsRequest, ScheduleStatus

pytestmark = pytest.mark.django_db


def _request(rid: str, status: RequestStatus, due_in: dt.timedelta) -> RightsRequest:
    now = timezone.now()
    return RightsRequest(
        id=rid,
        principal="p1",
        kind=RequestKind.ACCESS,
        status=status,
        opened_at=now - dt.timedelta(days=1),
        due_at=now + due_in,
        max_due_at=now + dt.timedelta(days=60),
        updated_at=now,
    )


def test_format_remaining() -> None:
    assert format_remaining(dt.timedelta(days=3, hours=4, minutes=5)) == "3d 4h left"
    assert format_remaining(-dt.timedelta(days=2, hours=1)) == "2d 1h overdue"
    assert format_remaining(dt.timedelta(minutes=90)) == "1h 30m left"


def test_request_queue_sla() -> None:
    repo = DjangoRepository()
    repo.save_request(_request("open", RequestStatus.RECEIVED, dt.timedelta(days=5, hours=1)))
    repo.save_request(_request("late", RequestStatus.IN_PROGRESS, -dt.timedelta(days=2, hours=1)))
    repo.save_request(_request("done", RequestStatus.COMPLETED, -dt.timedelta(days=9)))
    ma = RightsRequestAdmin(RequestRow, admin.site)
    assert "left" in str(ma.sla(RequestRow.objects.get(id="open")))
    assert "overdue" in str(ma.sla(RequestRow.objects.get(id="late")))
    assert ma.sla(RequestRow.objects.get(id="done")) == "closed"
    assert ma.kind(RequestRow.objects.get(id="open")) == "access"
    assert ma.assignee(RequestRow.objects.get(id="open")) == "-"


def test_retention_monitor_columns() -> None:
    now = timezone.now()
    sch = ErasureSchedule(
        id="s1",
        principal="p1",
        purpose="marketing",
        trigger=RetentionTrigger.LAST_ACTIVITY,
        status=ScheduleStatus.NEEDS_ATTENTION,
        erase_at=now + dt.timedelta(days=2),
        warn_at=now - dt.timedelta(hours=1),
        attention_reason="warning failed",
        created_at=now,
        updated_at=now,
    )
    DjangoRepository().save_schedule(sch)
    ma = RetentionMonitorAdmin(ScheduleRow, admin.site)
    row = ScheduleRow.objects.get(id="s1")
    assert ma.note(row) == "warning failed"
    assert ma.erasure_in(row) == "-"
    row.status = ScheduleStatus.SCHEDULED.value
    assert "left" in ma.erasure_in(row)


def test_admin_is_read_only() -> None:
    request = RequestFactory().get("/")
    for model in (RequestRow, ConsentEventRow, AuditRow, ScheduleRow):
        ma = admin.site._registry[model]
        assert not ma.has_add_permission(request)
        assert not ma.has_change_permission(request)
        assert not ma.has_delete_permission(request)


@pytest.mark.urls("tests.urls_admin")
def test_changelists_render() -> None:
    DjangoRepository().save_request(_request("open", RequestStatus.RECEIVED, dt.timedelta(days=5)))
    User.objects.create_superuser("root", "root@example.com", "pw")
    client = Client()
    client.login(username="root", password="pw")
    for name in ("requestrow", "consenteventrow", "auditrow", "schedulerow", "holdrow"):
        response = client.get(f"/admin/dpdpkit/{name}/")
        assert response.status_code == 200, name
    assert b"left" in client.get("/admin/dpdpkit/requestrow/").content
