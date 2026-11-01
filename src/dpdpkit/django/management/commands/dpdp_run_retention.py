"""``manage.py dpdp_run_retention``: send due erasure warnings and perform due erasures (run it from cron)."""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from dpdpkit.django import jobs


class Command(BaseCommand):
    help = "Send due erasure warnings and perform due erasures. Safe to run as often as you like."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--json", action="store_true", help="print the run as JSON")

    def handle(self, *args: Any, **options: Any) -> None:
        run = jobs.run_retention()
        if options["json"]:
            self.stdout.write(json.dumps(run, indent=2))
            return
        counts = ", ".join(
            f"{k} {run[k]}" for k in ("warned", "warning_pending", "erased", "held", "needs_attention", "cancelled")
        )
        self.stdout.write(f"retention run {run['id']}: {counts}")
