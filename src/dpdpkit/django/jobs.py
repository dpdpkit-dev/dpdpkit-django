"""The scheduled jobs, as plain functions: the management commands and the Celery tasks both call these.

Each returns JSON-friendly data, so a Celery result backend can store it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dpdpkit.ledger import FileRootSink

from .conf import get_kit


def run_retention() -> dict[str, Any]:
    """Send due erasure warnings and perform due erasures. Safe to run as often as you like."""
    result: dict[str, Any] = get_kit().retention.run().model_dump(mode="json")
    return result


def verify_ledger() -> dict[str, Any]:
    """Check both hash chains. Returns the report; ``ok`` is false when a row was altered or removed."""
    result: dict[str, Any] = get_kit().ledger.verify_report().model_dump(mode="json")
    return result


def export_root(path: str | Path) -> dict[str, Any]:
    """Append the current ledger root hash to ``path`` (point it at storage the operator cannot rewrite)."""
    result: dict[str, Any] = get_kit().ledger.export_root(FileRootSink(path)).model_dump(mode="json")
    return result
