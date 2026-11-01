from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterator

import pytest
from django.contrib.auth import get_user_model
from django.core import signing
from django.test import Client
from django.utils import timezone

from dpdpkit.django import conf
from dpdpkit.models import ConsentStatus
from school import guardians
from school.models import Learner, Progress

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def fresh_kit() -> Iterator[None]:
    conf.set_kit(None)
    yield
    conf.set_kit(None)


def signup(client: Client, username: str, born: dt.date, **extra: str) -> object:
    return client.post(
        "/signup/",
        {
            "username": username,
            "password1": "s3cret-Pass-word",
            "password2": "s3cret-Pass-word",
            "full_name": username.title(),
            "date_of_birth": born.isoformat(),
            **extra,
        },
    )


def years_ago(n: int) -> dt.date:
    today = timezone.localdate()
    return today.replace(year=today.year - n, day=1)


def guardian_link(response: object) -> str:
    match = re.search(r'href="(http://testserver/guardian/[^"]+)"', response.content.decode())  # type: ignore[attr-defined]
    assert match, "the welcome page shows the guardian link in the demo"
    return match.group(1).replace("http://testserver", "")


GUARDIAN = {"guardian_name": "Meera Rao", "guardian_email": "meera@example.in"}


def test_child_needs_guardian_details() -> None:
    response = signup(Client(), "tara", years_ago(10))
    assert response.status_code == 200  # type: ignore[attr-defined]
    assert not Learner.objects.exists()


def test_child_is_locked_out_until_guardian_consents() -> None:
    child = Client()
    link = guardian_link(signup(child, "tara", years_ago(10), **GUARDIAN))
    kit = conf.get_kit()
    user = get_user_model().objects.get(username="tara")
    assert kit.consent.state(str(user.pk)) == []  # nothing is recorded on the child's behalf

    assert child.get("/course/").status_code == 403
    assert child.get("/privacy/preferences/").status_code == 403
    assert child.post("/privacy/preferences/", {"purpose": ["learning", "marketing"]}).status_code == 403
    assert kit.consent.state(str(user.pk)) == []

    guardian = Client()
    assert guardian.get(link).status_code == 200
    assert guardian.post(link, {"purpose": ["learning", "account"]}).status_code == 302

    assert child.get("/course/").status_code == 200
    events = kit.consent.history(str(user.pk))
    assert {e.purpose for e in events} >= {"learning", "account"}
    granted = [e for e in events if e.purpose == "learning"][-1]
    assert granted.source == "guardian"
    assert granted.metadata["guardian_email"] == "meera@example.in"
    assert Learner.objects.get(user=user).guardian_verified_at is not None


def test_adult_only_purposes_are_never_taken_for_a_child() -> None:
    child = Client()
    link = guardian_link(signup(child, "tara", years_ago(10), **GUARDIAN))
    page = Client().get(link).content.decode()
    assert 'value="marketing"' not in page
    assert 'value="product_improvement"' not in page
    assert "checked" not in page  # nothing pre-ticked

    Client().post(link, {"purpose": ["learning", "marketing", "product_improvement"]})
    kit = conf.get_kit()
    states = {s.purpose: s for s in kit.consent.state(str(get_user_model().objects.get(username="tara").pk))}
    assert states["learning"].status is ConsentStatus.GRANTED
    assert "marketing" not in states
    assert "product_improvement" not in states


def test_guardian_can_withdraw_through_the_same_link() -> None:
    child = Client()
    link = guardian_link(signup(child, "tara", years_ago(10), **GUARDIAN))
    Client().post(link, {"purpose": ["learning", "parent_updates"]})
    assert child.get("/course/").status_code == 200

    Client().post(link, {"purpose": ["parent_updates"]})  # un-tick learning
    assert child.get("/course/").status_code == 403


def test_forged_expired_and_stale_links_are_refused(settings: object) -> None:
    child = Client()
    link = guardian_link(signup(child, "tara", years_ago(10), **GUARDIAN))
    assert Client().get(link[:-4] + "abc/").status_code == 400

    settings.GUARDIAN_LINK_MAX_AGE = -1  # type: ignore[attr-defined]
    assert Client().get(link).status_code == 400
    settings.GUARDIAN_LINK_MAX_AGE = 3600  # type: ignore[attr-defined]

    Learner.objects.update(guardian_email="someone-else@example.in")  # the address changed after issue
    assert Client().get(link).status_code == 400
    with pytest.raises(signing.BadSignature):
        guardians.learner_from_token("garbage")


def test_adult_consents_for_themselves() -> None:
    adult = Client()
    response = signup(adult, "arun", years_ago(30))
    assert response.status_code == 200  # type: ignore[attr-defined]
    assert adult.get("/course/").status_code == 403

    assert adult.post("/privacy/preferences/", {"purpose": ["learning", "marketing"]}).status_code == 302
    assert adult.get("/course/").status_code == 200
    kit = conf.get_kit()
    states = {s.purpose: s for s in kit.consent.state(str(get_user_model().objects.get(username="arun").pk))}
    assert states["marketing"].status is ConsentStatus.GRANTED


def test_child_turning_18_manages_their_own_choices() -> None:
    child = Client()
    signup(child, "tara", years_ago(10), **GUARDIAN)
    learner = Learner.objects.get()
    learner.date_of_birth = years_ago(19)
    learner.save()
    assert child.get("/privacy/preferences/").status_code == 200


def test_erasure_uses_the_registry() -> None:
    child = Client()
    link = guardian_link(signup(child, "tara", years_ago(10), **GUARDIAN))
    Client().post(link, {"purpose": ["learning"]})
    child.post("/course/", {"score": "7"})
    user = get_user_model().objects.get(username="tara")
    assert Progress.objects.filter(user=user).count() == 1

    from dpdpkit.django.registry import registry

    registry.erase(str(user.pk))
    learner = Learner.objects.get()
    assert learner.full_name.startswith("anonymised-")
    assert learner.guardian_email.endswith("@anonymised.invalid")
    assert learner.date_of_birth is None
    assert not Progress.objects.exists()
