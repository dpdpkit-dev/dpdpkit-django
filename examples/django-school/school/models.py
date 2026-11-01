from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.db import models


class Learner(models.Model):
    """A learner's profile. The learner's principal id in dpdpkit is ``str(user.pk)``."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="learner")
    full_name = models.CharField(max_length=120)
    date_of_birth = models.DateField(null=True)  # null once erased
    school_grade = models.CharField(max_length=20, blank=True)
    guardian_name = models.CharField(max_length=120, blank=True)
    guardian_email = models.EmailField(blank=True)
    guardian_verified_at = models.DateTimeField(null=True, blank=True)

    def age_on(self, today: dt.date) -> int | None:
        born = self.date_of_birth
        if born is None:
            return None
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


class Progress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="progress")
    course = models.CharField(max_length=80)
    score = models.IntegerField(default=0)
