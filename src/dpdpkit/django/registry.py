"""``PersonalDataRegistry``: where your Django models hold personal data and how each field is erased.

Each field gets one strategy: ``delete`` (clear the value), ``anonymise`` (replace it with a placeholder, or the
result of your own ``callable(row)``) or ``retain_legal`` (keep it because a law requires, with a stated reason).
A registration can instead delete the whole row. ``registry.erase`` has the shape of dpdpkit-core's erasure
handler, so ``registry.attach(kit)`` is all it takes to make retention runs and erasure requests use it.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import DEFAULT_DB_ALIAS, models, transaction

if TYPE_CHECKING:
    from dpdpkit import Kit

Anonymiser = Callable[[Any], Any]
"""``fn(row)`` returns the value that replaces the field. Use ``row.pk`` to keep unique columns unique."""


class Action(str, enum.Enum):
    DELETE = "delete"
    ANONYMISE = "anonymise"
    RETAIN_LEGAL = "retain_legal"


Strategy = Action | str | Anonymiser


@dataclass
class Registration:
    model: type[models.Model]
    principal_field: str
    actions: dict[str, Action]
    anonymisers: dict[str, Anonymiser]
    purposes: frozenset[str]
    delete_rows: bool
    retain_reason: str
    using: str

    @property
    def label(self) -> str:
        return self.model._meta.label

    def applies(self, purposes: Collection[str]) -> bool:
        """Registrations without purposes apply to every erasure."""
        return not self.purposes or bool(self.purposes.intersection(purposes))


@dataclass
class ErasureReport:
    """What ``erase`` did to one model. ``retained`` lists the fields kept under ``retain_legal``."""

    model: str
    rows: int = 0
    deleted_rows: int = 0
    cleared: list[str] = field(default_factory=list)
    anonymised: list[str] = field(default_factory=list)
    retained: list[str] = field(default_factory=list)
    retain_reason: str = ""


def _clear_value(f: models.Field[Any, Any]) -> Any:
    if f.null:
        return None
    if isinstance(f, (models.CharField, models.TextField)):
        return ""
    if f.has_default():
        return f.get_default()
    raise ImproperlyConfigured(
        f"{f.model._meta.label}.{f.name} cannot be cleared (not nullable, no default): "
        "use anonymise with a callable, or retain_legal"
    )


def _default_anonymiser(f: models.Field[Any, Any]) -> Anonymiser:
    if isinstance(f, models.EmailField):
        return lambda row: f"anonymised-{row.pk}@anonymised.invalid"[: f.max_length or 254]
    if isinstance(f, (models.CharField, models.TextField)):
        limit = getattr(f, "max_length", None)
        return lambda row: f"anonymised-{row.pk}"[:limit]
    if f.null:
        return lambda row: None
    raise ImproperlyConfigured(
        f"{f.model._meta.label}.{f.name} needs an anonymiser: pass a callable(row) instead of 'anonymise'"
    )


class PersonalDataRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Registration] = {}

    def register(
        self,
        model: type[models.Model],
        *,
        principal_field: str,
        fields: Mapping[str, Strategy] | None = None,
        delete_rows: bool = False,
        purposes: Collection[str] = (),
        retain_reason: str = "",
        using: str = DEFAULT_DB_ALIAS,
    ) -> Registration:
        """Declare the personal data in ``model``.

        ``principal_field`` is the field (for example ``"pk"`` or ``"user"``) that matches the principal id.
        ``fields`` maps field names to ``"delete"``, ``"anonymise"``, ``"retain_legal"`` or a ``callable(row)``
        (anonymise with its result). ``delete_rows=True`` deletes the principal's rows instead, and cannot be
        combined with ``fields``. ``purposes`` limits the registration to erasures of those purposes.
        ``retain_reason`` (the legal basis for keeping the data) is required with ``retain_legal``.
        """
        label = model._meta.label
        if label in self._items:
            raise ImproperlyConfigured(f"{label} is already registered")
        fields = dict(fields or {})
        if delete_rows == bool(fields):
            raise ImproperlyConfigured(f"{label}: give either fields or delete_rows=True")
        if principal_field != "pk":
            try:
                model._meta.get_field(principal_field)
            except FieldDoesNotExist as exc:
                raise ImproperlyConfigured(f"{label} has no principal field {principal_field!r}") from exc

        actions: dict[str, Action] = {}
        anonymisers: dict[str, Anonymiser] = {}
        for name, strategy in fields.items():
            try:
                f = model._meta.get_field(name)
            except FieldDoesNotExist as exc:
                raise ImproperlyConfigured(f"{label} has no field {name!r}") from exc
            if not isinstance(f, models.Field) or not f.concrete or f.primary_key:
                raise ImproperlyConfigured(f"{label}.{name} is not a column that can be erased in place")
            if callable(strategy):
                actions[name], anonymisers[name] = Action.ANONYMISE, strategy
                continue
            try:
                action = Action(strategy)
            except ValueError as exc:
                raise ImproperlyConfigured(f"{label}.{name}: unknown strategy {strategy!r}") from exc
            actions[name] = action
            if action is Action.DELETE:
                _clear_value(f)  # fail now, not during an erasure
            elif action is Action.ANONYMISE:
                anonymisers[name] = _default_anonymiser(f)
        if Action.RETAIN_LEGAL in actions.values() and not retain_reason:
            raise ImproperlyConfigured(f"{label}: retain_legal needs a retain_reason")

        item = Registration(
            model, principal_field, actions, anonymisers, frozenset(purposes), delete_rows, retain_reason, using
        )
        self._items[label] = item
        return item

    def registrations(self) -> list[Registration]:
        return list(self._items.values())

    def unregister(self, model: type[models.Model]) -> None:
        self._items.pop(model._meta.label, None)

    def clear(self) -> None:
        self._items.clear()

    def describe(self) -> list[dict[str, str]]:
        """One row per registered field (or model, when its rows are deleted): the baseline for a PII scan."""
        out: list[dict[str, str]] = []
        for item in self._items.values():
            if item.delete_rows:
                out.append({"model": item.label, "field": "*", "action": "delete_rows"})
            for name, action in item.actions.items():
                row = {"model": item.label, "field": name, "action": action.value}
                if action is Action.RETAIN_LEGAL:
                    row["reason"] = item.retain_reason
                out.append(row)
        return out

    def erase(self, principal: str, purposes: Collection[str] = ()) -> list[ErasureReport]:
        """Apply every matching registration to the principal's rows. Atomic per database: a failure rolls back.

        Raises on failure, so core's retention service marks the schedule ``needs_attention``."""
        reports: list[ErasureReport] = []
        for item in self._items.values():
            if not item.applies(purposes):
                continue
            with transaction.atomic(using=item.using):
                reports.append(self._erase_one(item, principal))
        return reports

    def _erase_one(self, item: Registration, principal: str) -> ErasureReport:
        report = ErasureReport(item.label)
        qs = item.model._default_manager.using(item.using).filter(**{item.principal_field: principal})
        if item.delete_rows:
            report.rows = qs.count()
            qs.delete()
            report.deleted_rows = report.rows
            return report
        report.cleared = [n for n, a in item.actions.items() if a is Action.DELETE]
        report.anonymised = [n for n, a in item.actions.items() if a is Action.ANONYMISE]
        report.retained = [n for n, a in item.actions.items() if a is Action.RETAIN_LEGAL]
        if report.retained:
            report.retain_reason = item.retain_reason
        changing = report.cleared + report.anonymised
        meta = item.model._meta
        for row in qs:
            for name in report.cleared:
                setattr(row, name, _clear_value(meta.get_field(name)))  # type: ignore[arg-type]
            for name in report.anonymised:
                setattr(row, name, item.anonymisers[name](row))
            if changing:
                row.save(update_fields=changing, using=item.using)
            report.rows += 1
        return report

    def attach(self, kit: Kit) -> None:
        """Make the kit's retention runs and erasure requests call ``erase``."""

        def handler(principal: str, purposes: list[str]) -> None:
            self.erase(principal, purposes)

        kit.retention.register_handler(handler)


#: The project-wide registry. Register your models on it (for example in ``AppConfig.ready``).
registry = PersonalDataRegistry()
