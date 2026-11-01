"""``manage.py dpdp_export``: a principal's data export, the audit evidence pack, or the ledger root hash."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from dpdpkit.django import jobs
from dpdpkit.django.conf import get_kit


class Command(BaseCommand):
    help = (
        "Export one of: a principal's data (--principal), the audit evidence pack zip (--evidence-pack), "
        "or append the ledger root hash to a file (--root-file)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        what = parser.add_mutually_exclusive_group(required=True)
        what.add_argument("--principal", help="id of the principal whose data to export")
        what.add_argument("--evidence-pack", action="store_true", help="build the audit evidence pack (zip)")
        what.add_argument("--root-file", help="append the current ledger root hash to this file")
        parser.add_argument("--format", choices=["json", "html"], default="json", help="format for --principal")
        parser.add_argument(
            "-o", "--output", help="write to this file instead of stdout (required for --evidence-pack)"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        output = options["output"]
        if options["root_file"]:
            root = jobs.export_root(options["root_file"])
            self.stdout.write(f"root {root['root']} appended to {options['root_file']}")
            return
        export = get_kit().export
        if options["evidence_pack"]:
            if not output:
                raise CommandError("--evidence-pack needs --output FILE (it is a zip)")
            Path(output).write_bytes(export.evidence_pack())
            self.stdout.write(f"evidence pack written to {output}")
            return
        principal = options["principal"]
        text = (
            export.principal_html(principal)
            if options["format"] == "html"
            else json.dumps(export.principal(principal), indent=2, ensure_ascii=False)
        )
        if output:
            Path(output).write_text(text, encoding="utf-8")
            self.stdout.write(f"export written to {output}")
        else:
            self.stdout.write(text)
