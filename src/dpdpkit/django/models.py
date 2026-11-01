# mypy: disable-error-code="var-annotated"
# (field types are only inferred with the django-stubs plugin, which needs a settings module)
"""Django models. Ledger and audit rows use real columns; mutable aggregates store their model as a JSON
document next to the indexed columns used for lookups. Table names match dpdpkit-fastapi's."""

from __future__ import annotations

from django.db import models


class ConsentEventRow(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    tenant_id = models.CharField(max_length=64)
    seq = models.BigIntegerField()
    principal = models.CharField(max_length=255)
    purpose = models.CharField(max_length=128)
    action = models.CharField(max_length=16)
    notice_version = models.IntegerField(null=True)
    notice_hash = models.CharField(max_length=64, null=True)
    locale = models.CharField(max_length=16, null=True)
    source = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()
    meta = models.JSONField(default=dict)
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64)

    class Meta:
        db_table = "dpdp_consent_events"
        constraints = [models.UniqueConstraint(fields=["tenant_id", "seq"], name="uq_dpdp_consent_events_tenant_seq")]
        indexes = [models.Index(fields=["tenant_id", "principal", "purpose", "seq"], name="ix_dpdp_consent_lookup")]


class AuditRow(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    tenant_id = models.CharField(max_length=64)
    seq = models.BigIntegerField()
    actor = models.CharField(max_length=255)
    action = models.CharField(max_length=128)
    subject_type = models.CharField(max_length=64)
    subject_id = models.CharField(max_length=255)
    occurred_at = models.DateTimeField()
    data = models.JSONField(default=dict)
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64)

    class Meta:
        db_table = "dpdp_audit"
        constraints = [models.UniqueConstraint(fields=["tenant_id", "seq"], name="uq_dpdp_audit_tenant_seq")]
        indexes = [models.Index(fields=["tenant_id", "subject_id"], name="ix_dpdp_audit_subject")]


class NoticeRow(models.Model):
    tenant_id = models.CharField(max_length=64)
    version = models.IntegerField()
    locale = models.CharField(max_length=16)
    content_hash = models.CharField(max_length=64)
    published_at = models.DateTimeField()
    doc = models.JSONField()

    class Meta:
        db_table = "dpdp_notices"
        constraints = [models.UniqueConstraint(fields=["tenant_id", "version", "locale"], name="uq_dpdp_notices_key")]


class RequestRow(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    tenant_id = models.CharField(max_length=64)
    principal = models.CharField(max_length=255)
    status = models.CharField(max_length=32)
    opened_at = models.DateTimeField()
    doc = models.JSONField()

    class Meta:
        db_table = "dpdp_requests"
        indexes = [
            models.Index(fields=["tenant_id", "principal"], name="ix_dpdp_requests_principal"),
            models.Index(fields=["tenant_id", "status"], name="ix_dpdp_requests_status"),
        ]


class NomineeRow(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    tenant_id = models.CharField(max_length=64)
    principal = models.CharField(max_length=255)
    doc = models.JSONField()

    class Meta:
        db_table = "dpdp_nominees"
        indexes = [models.Index(fields=["tenant_id", "principal"], name="ix_dpdp_nominees_principal")]


class ScheduleRow(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    tenant_id = models.CharField(max_length=64)
    principal = models.CharField(max_length=255)
    purpose = models.CharField(max_length=128)
    status = models.CharField(max_length=32)
    warn_at = models.DateTimeField()
    erase_at = models.DateTimeField()
    doc = models.JSONField()

    class Meta:
        db_table = "dpdp_erasure_schedules"
        indexes = [
            models.Index(fields=["tenant_id", "status", "warn_at"], name="ix_dpdp_schedules_due"),
            models.Index(fields=["tenant_id", "principal"], name="ix_dpdp_schedules_principal"),
        ]


class HoldRow(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    tenant_id = models.CharField(max_length=64)
    principal = models.CharField(max_length=255)
    active = models.BooleanField()
    doc = models.JSONField()

    class Meta:
        db_table = "dpdp_legal_holds"
        indexes = [models.Index(fields=["tenant_id", "principal", "active"], name="ix_dpdp_holds_principal")]


class ActivityRow(models.Model):
    tenant_id = models.CharField(max_length=64)
    principal = models.CharField(max_length=255)
    last_at = models.DateTimeField()

    class Meta:
        db_table = "dpdp_activity"
        constraints = [models.UniqueConstraint(fields=["tenant_id", "principal"], name="uq_dpdp_activity_key")]


class DeliveryRow(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    tenant_id = models.CharField(max_length=64)
    created_at = models.DateTimeField()
    doc = models.JSONField()

    class Meta:
        db_table = "dpdp_deliveries"
