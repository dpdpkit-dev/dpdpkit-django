from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, User
from django.core.exceptions import ImproperlyConfigured

from dpdpkit import InMemoryRepository, Kit
from dpdpkit.django.registry import Action, PersonalDataRegistry

pytestmark = pytest.mark.django_db


@pytest.fixture
def reg() -> PersonalDataRegistry:
    return PersonalDataRegistry()


def _users() -> tuple[User, User]:
    a = User.objects.create(username="a", email="a@example.com", first_name="Asha", last_name="Rao", password="x")
    b = User.objects.create(username="b", email="b@example.com", first_name="Bala", password="x")
    return a, b


def test_delete_anonymise_and_retain(reg: PersonalDataRegistry) -> None:
    a, b = _users()
    reg.register(
        User,
        principal_field="pk",
        fields={"first_name": "delete", "email": "anonymise", "last_name": Action.RETAIN_LEGAL},
        retain_reason="Income Tax Act record keeping",
    )
    (report,) = reg.erase(str(a.pk))
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.first_name == "" and a.email == f"anonymised-{a.pk}@anonymised.invalid" and a.last_name == "Rao"
    assert b.first_name == "Bala" and b.email == "b@example.com"
    assert (report.rows, report.cleared, report.anonymised, report.retained) == (
        1,
        ["first_name"],
        ["email"],
        ["last_name"],
    )
    assert report.retain_reason == "Income Tax Act record keeping"


def test_callable_anonymiser(reg: PersonalDataRegistry) -> None:
    a, _ = _users()
    reg.register(User, principal_field="username", fields={"first_name": lambda row: f"user-{row.pk}"})
    reg.erase("a")
    a.refresh_from_db()
    assert a.first_name == f"user-{a.pk}"


def test_delete_rows_and_purpose_filter(reg: PersonalDataRegistry) -> None:
    Group.objects.create(name="g")
    reg.register(Group, principal_field="name", delete_rows=True, purposes=["marketing"])
    assert reg.erase("g", ["account"]) == []
    assert Group.objects.count() == 1
    (report,) = reg.erase("g", ["marketing"])
    assert report.deleted_rows == 1 and Group.objects.count() == 0


def test_rolls_back_on_failure(reg: PersonalDataRegistry) -> None:
    a, _ = _users()

    def boom(row: User) -> str:
        raise RuntimeError("nope")

    reg.register(User, principal_field="pk", fields={"first_name": "delete", "last_name": boom})
    with pytest.raises(RuntimeError):
        reg.erase(str(a.pk))
    a.refresh_from_db()
    assert a.first_name == "Asha"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"principal_field": "pk"},
        {"principal_field": "pk", "fields": {"first_name": "delete"}, "delete_rows": True},
        {"principal_field": "nope", "fields": {"first_name": "delete"}},
        {"principal_field": "pk", "fields": {"nope": "delete"}},
        {"principal_field": "pk", "fields": {"id": "delete"}},
        {"principal_field": "pk", "fields": {"first_name": "shred"}},
        {"principal_field": "pk", "fields": {"first_name": "retain_legal"}},
        {"principal_field": "pk", "fields": {"date_joined": "anonymise"}},
    ],
)
def test_register_validates(reg: PersonalDataRegistry, kwargs: dict[str, object]) -> None:
    with pytest.raises(ImproperlyConfigured):
        reg.register(User, **kwargs)  # type: ignore[arg-type]


def test_double_registration_and_describe(reg: PersonalDataRegistry) -> None:
    reg.register(
        User, principal_field="pk", fields={"email": "anonymise", "last_name": "retain_legal"}, retain_reason="r"
    )
    with pytest.raises(ImproperlyConfigured):
        reg.register(User, principal_field="pk", fields={"email": "delete"})
    assert reg.describe() == [
        {"model": "auth.User", "field": "email", "action": "anonymise"},
        {"model": "auth.User", "field": "last_name", "action": "retain_legal", "reason": "r"},
    ]
    reg.unregister(User)
    assert reg.registrations() == []


def test_attach_registers_kit_handler(reg: PersonalDataRegistry) -> None:
    kit = Kit(InMemoryRepository(), "dpdp-rules-2025.v1")
    a, _ = _users()
    reg.register(User, principal_field="pk", fields={"first_name": "delete"})
    reg.attach(kit)
    (handler,) = kit.retention._handlers
    handler(str(a.pk), ["account"])
    a.refresh_from_db()
    assert a.first_name == ""
