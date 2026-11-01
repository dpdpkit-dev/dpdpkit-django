"""``manage.py dpdp_verify_ledger``: check the consent and audit hash chains; exits non-zero when one is broken."""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from dpdpkit.django import jobs


class Command(BaseCommand):
    help = "Verify the consent and audit ledgers. Exits with status 1 when a row was altered or removed."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--json", action="store_true", help="print the report as JSON")

    def handle(self, *args: Any, **options: Any) -> None:
        report = jobs.verify_ledger()
        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2))
        elif report["ok"]:
            self.stdout.write(self.style.SUCCESS(f"ledger OK ({report['checked']} rows checked)"))
        if not report["ok"]:
            raise CommandError(
                f"ledger verification FAILED: {report['chain']} row {report['failed_row']}: {report['reason']}"
            )
