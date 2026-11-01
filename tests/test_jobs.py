from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from django.core.management import call_command
from django.core.management.base import CommandError

from dpdpkit import Kit, kit_from_config, sync_notice
from dpdpkit.config import STARTER_CONFIG
from dpdpkit.django import conf, tasks
from dpdpkit.django.models import ConsentEventRow
from dpdpkit.django.repository import DjangoRepository

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def kit() -> Iterator[Kit]:
    cfg = yaml.safe_load(STARTER_CONFIG)
    k = kit_from_config(cfg, DjangoRepository(), signing_key="k")
    sync_notice(k, cfg)
    conf.set_kit(k)
    yield k
    conf.set_kit(None)


def _run(name: str, *args: str) -> str:
    out = io.StringIO()
    call_command(name, *args, stdout=out)
    return out.getvalue()


def test_run_retention_command_and_task() -> None:
    assert "retention run" in _run("dpdp_run_retention")
    run = json.loads(_run("dpdp_run_retention", "--json"))
    assert run["erased"] == 0 and run["tenant_id"] == "default"
    assert tasks.run_retention()["warned"] == 0


def test_verify_ledger_ok_then_tampered(kit: Kit) -> None:
    kit.consent.record("u1", {"marketing": True}, source="test")
    assert "ledger OK" in _run("dpdp_verify_ledger")
    assert tasks.verify_ledger()["ok"] is True
    ConsentEventRow.objects.update(principal="someone-else")
    with pytest.raises(CommandError, match="FAILED"):
        _run("dpdp_verify_ledger")
    assert tasks.verify_ledger()["ok"] is False


def test_export_principal(kit: Kit) -> None:
    kit.consent.record("u1", {"marketing": True}, source="test")
    data = json.loads(_run("dpdp_export", "--principal", "u1"))
    assert data["principal"] == "u1" and data["consents"]
    assert "<html" in _run("dpdp_export", "--principal", "u1", "--format", "html")


def test_export_to_files(tmp_path: Path, kit: Kit) -> None:
    kit.consent.record("u1", {"marketing": True}, source="test")
    pack = tmp_path / "pack.zip"
    _run("dpdp_export", "--evidence-pack", "-o", str(pack))
    assert "summary.pdf" in zipfile.ZipFile(pack).namelist()
    with pytest.raises(CommandError, match="--output"):
        _run("dpdp_export", "--evidence-pack")

    roots = tmp_path / "roots.jsonl"
    _run("dpdp_export", "--root-file", str(roots))
    tasks.export_root(str(roots))
    assert len(roots.read_text(encoding="utf-8").splitlines()) == 2
