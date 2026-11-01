"""Project wiring: the shared ``Kit``, the principal resolver and the admin guard, read from ``settings.DPDPKIT``.

``DPDPKIT`` keys: ``CONFIG`` (path to a dpdpkit.yaml, or a mapping) or ``POLICY``; ``OVERLAYS``, ``CONTACT``,
``TENANT_ID``, ``SIGNING_KEY``, ``DATABASE`` (alias holding the dpdpkit tables); ``PRINCIPAL_RESOLVER`` and
``ADMIN_GUARD`` (dotted paths to ``callable(request)``); ``DRF`` (``True``/``False`` to force or forbid the DRF
viewsets, default: use them when installed); ``CSRF_EXEMPT`` (exempt the plain views from CSRF checks).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import HttpRequest
from django.utils.module_loading import import_string
from dpdpkit import Kit
from dpdpkit.config import kit_from_config, load_config, sync_notice
from dpdpkit.errors import ConfigError
from dpdpkit.models import Role

from .repository import DjangoRepository

log = logging.getLogger("dpdpkit.django")

_kit: Kit | None = None


def options() -> dict[str, Any]:
    return dict(getattr(settings, "DPDPKIT", None) or {})


def set_kit(kit: Kit | None) -> None:
    """Use ``kit`` for the REST views (``None`` forgets the current one so it is rebuilt from settings)."""
    global _kit
    _kit = kit


def get_kit() -> Kit:
    global _kit
    if _kit is None:
        _kit = _build_kit(options())
    return _kit


def _build_kit(opts: dict[str, Any]) -> Kit:
    repository = DjangoRepository(opts["DATABASE"]) if "DATABASE" in opts else DjangoRepository()
    common: dict[str, Any] = {}
    if opts.get("SIGNING_KEY"):
        common["signing_key"] = opts["SIGNING_KEY"]
    if opts.get("CONFIG") is not None:
        raw = opts["CONFIG"]
        config = load_config(raw) if isinstance(raw, (str, Path)) else dict(raw)
        if opts.get("TENANT_ID"):
            common["tenant_id"] = opts["TENANT_ID"]
        kit = kit_from_config(config, repository, contact=opts.get("CONTACT"), **common)
        sync_notice(kit, config)
        return kit
    if not opts.get("POLICY"):
        raise ConfigError("set DPDPKIT['CONFIG'] (a dpdpkit.yaml) or DPDPKIT['POLICY'] in settings")
    return Kit(
        repository,
        opts["POLICY"],
        overlays=list(opts.get("OVERLAYS") or []),
        contact=opts.get("CONTACT"),
        tenant_id=opts.get("TENANT_ID", "default"),
        **common,
    )


def _hook(name: str, default: Callable[[HttpRequest], Any]) -> Callable[[HttpRequest], Any]:
    path = options().get(name)
    return import_string(path) if isinstance(path, str) else (path or default)


def default_principal(request: HttpRequest) -> str | None:
    user = getattr(request, "user", None)
    return str(user.pk) if user is not None and user.is_authenticated else None


def default_admin_guard(request: HttpRequest) -> Role | None:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    if user.is_superuser:
        return Role.ADMIN
    return Role.HANDLER if user.is_staff else None


def resolve_principal(request: HttpRequest) -> str | None:
    value = _hook("PRINCIPAL_RESOLVER", default_principal)(request)
    return str(value) if value else None


def resolve_role(request: HttpRequest) -> Role | None:
    value = _hook("ADMIN_GUARD", default_admin_guard)(request)
    if value is True:
        return Role.ADMIN
    if not value:
        return None
    try:
        return Role(value)
    except ValueError:
        log.warning("ADMIN_GUARD returned unknown role %r; treating as no access", value)
        return None
