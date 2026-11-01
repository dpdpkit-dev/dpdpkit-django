"""Celery tasks (``pip install celery``; picked up by ``app.autodiscover_tasks()``).

Schedule them with Celery beat, for example::

    CELERY_BEAT_SCHEDULE = {
        "dpdp-retention": {"task": "dpdpkit.django.run_retention", "schedule": 3600},
        "dpdp-verify": {"task": "dpdpkit.django.verify_ledger", "schedule": 86400},
    }

Without Celery this module still imports and the functions are plain callables; use the management commands
(``dpdp_run_retention``, ``dpdp_verify_ledger``, ``dpdp_export``) from cron instead.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from . import jobs

log = logging.getLogger("dpdpkit.django")

try:
    from celery import shared_task  # type: ignore[import-not-found,unused-ignore]
except ImportError:  # Celery is optional

    def shared_task(*args: Any, **kwargs: Any) -> Any:
        if args and callable(args[0]):
            return args[0]
        return lambda fn: fn


def _task(name: str) -> Callable[[Callable[..., dict[str, Any]]], Any]:
    return shared_task(name=f"dpdpkit.django.{name}", ignore_result=False)


@_task("run_retention")
def run_retention() -> dict[str, Any]:
    """Send due erasure warnings and perform due erasures."""
    return jobs.run_retention()


@_task("verify_ledger")
def verify_ledger() -> dict[str, Any]:
    """Verify both ledger chains. A failed check is logged at error level and returned with ``ok`` false."""
    report = jobs.verify_ledger()
    if not report["ok"]:
        log.error("ledger verification failed: %s row %s: %s", report["chain"], report["failed_row"], report["reason"])
    return report


@_task("export_root")
def export_root(path: str) -> dict[str, Any]:
    """Append the current ledger root hash to the file at ``path``."""
    return jobs.export_root(path)
