"""The child-account flow.

1. A learner signs up with a date of birth. Under 18 (the policy's ``children.age_of_majority``) they must name a
   parent or guardian, and the account is created *without any consent*.
2. The guardian gets a signed, expiring link (printed to the console here; send it by email or SMS in a real
   site). Opening it proves control of that address. Replace this step with a stronger check where your counsel
   says Rule 10 needs one (a government-issued token, for example).
3. The guardian makes the consent choices *for the child*: they are recorded under the child's principal with
   ``source="guardian"`` and the guardian's details in the metadata. Purposes that must not be aimed at children
   (``ADULT_ONLY``) are never offered, and are refused if posted anyway.
4. Until the guardian has granted ``learning``, ``@requires_consent("learning")`` keeps the child out of the course.
"""

from __future__ import annotations

import datetime as dt
import logging

from django.conf import settings
from django.core import signing
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from dpdpkit.django import conf
from dpdpkit.models import ConsentStatus

from .models import Learner

log = logging.getLogger("school.guardians")

SALT = "school.guardian-consent"

#: Purposes that track, monitor or market to the learner (DPDP Act s.9(3)); never offered for children.
ADULT_ONLY = frozenset({"product_improvement", "marketing"})


def is_child(learner: Learner, today: dt.date | None = None) -> bool:
    age = learner.age_on(today or timezone.localdate())
    return age is not None and age < conf.get_kit().policy.age_of_majority


def make_link(request: HttpRequest, learner: Learner) -> str:
    token = signing.dumps({"learner": learner.pk, "guardian": learner.guardian_email}, salt=SALT)
    return request.build_absolute_uri(reverse("guardian-consent", args=[token]))


def send_link(request: HttpRequest, learner: Learner) -> str:
    """Stand-in for emailing the guardian: log the link. Returns it so the sign-up page can show it in the demo."""
    link = make_link(request, learner)
    log.warning("guardian consent link for %s <%s>: %s", learner.guardian_name, learner.guardian_email, link)
    return link


def learner_from_token(token: str) -> Learner:
    """The learner a link was issued for. Raises ``signing.BadSignature`` if the link is forged or expired, or
    if the guardian's address was changed since it was issued."""
    data = signing.loads(token, salt=SALT, max_age=settings.GUARDIAN_LINK_MAX_AGE)
    try:
        learner = Learner.objects.select_related("user").get(pk=data["learner"])
    except Learner.DoesNotExist as exc:
        raise signing.BadSignature("unknown learner") from exc
    if learner.guardian_email != data["guardian"] or not is_child(learner):
        raise signing.BadSignature("link no longer valid")
    return learner


def offered_purposes(learner: Learner) -> list[dict[str, object]]:
    """The consent choices shown to the guardian: nothing pre-ticked, adult-only purposes left out."""
    kit = conf.get_kit()
    principal = str(learner.user_id)
    states = {s.purpose: s for s in kit.consent.state(principal)}
    notice = kit.notices.current()
    shown = {p.id for p in kit.registry.consent_purposes()} - ADULT_ONLY
    return [
        {
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "granted": p.id in states and states[p.id].status is ConsentStatus.GRANTED,
        }
        for p in notice.content.purposes
        if p.id in shown
    ]


def record_guardian_choices(request: HttpRequest, learner: Learner) -> None:
    """Record the guardian's posted choices for the child (grant ticked, withdraw un-ticked, deny the rest)."""
    kit = conf.get_kit()
    principal = str(learner.user_id)
    ticked = set(request.POST.getlist("purpose")) - ADULT_ONLY
    current = {s.purpose: s for s in kit.consent.state(principal)}
    metadata = {
        "given_by": "guardian",
        "guardian_name": learner.guardian_name,
        "guardian_email": learner.guardian_email,
        "verification": "email_link",
    }
    notice_version = request.POST.get("notice_version", "")
    decisions: dict[str, bool] = {}
    for item in offered_purposes(learner):
        purpose = str(item["id"])
        granted = purpose in current and current[purpose].status is ConsentStatus.GRANTED
        if purpose in ticked:
            if not granted:
                decisions[purpose] = True
        elif granted:
            kit.consent.withdraw(principal, purpose, source="guardian", metadata=metadata)
        elif purpose not in current:
            decisions[purpose] = False
    if decisions:
        kit.consent.record(
            principal,
            decisions,
            notice_version=int(notice_version) if notice_version.isdigit() else None,
            source="guardian",
            metadata=metadata,
        )
    if learner.guardian_verified_at is None:
        learner.guardian_verified_at = timezone.now()
        learner.save(update_fields=["guardian_verified_at"])
