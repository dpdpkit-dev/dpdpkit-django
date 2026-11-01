from typing import Any

from django.apps import AppConfig
from django.core.signals import request_started


class SchoolConfig(AppConfig):
    name = "school"

    def ready(self) -> None:
        from dpdpkit.django.registry import registry

        from .models import Learner, Progress

        registry.register(
            Learner,
            principal_field="user",
            fields={
                "full_name": "anonymise",
                "date_of_birth": "delete",
                "school_grade": "delete",
                "guardian_name": "anonymise",
                "guardian_email": "anonymise",
            },
        )
        registry.register(Progress, principal_field="user", delete_rows=True)
        # Building the kit writes the notice to the database, so wait for the first request (the tables exist by
        # then) before pointing erasure requests and retention runs at the registry.
        request_started.connect(self._attach_registry, dispatch_uid="school.attach_registry")

    @staticmethod
    def _attach_registry(**kwargs: Any) -> None:
        from dpdpkit.django import conf
        from dpdpkit.django.registry import registry

        request_started.disconnect(dispatch_uid="school.attach_registry")
        registry.attach(conf.get_kit())
