"""Plain JSON views for the REST contract; used when Django REST framework is not installed."""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.urls import URLPattern, path
from django.views.decorators.csrf import csrf_exempt

from .api import ROUTES, method_not_allowed
from .conf import options


def _dispatcher(table: dict[str, Callable[..., HttpResponse]]) -> Callable[..., HttpResponse]:
    def view(request: HttpRequest, **kwargs: str) -> HttpResponse:
        handler = table.get((request.method or "").lower())
        if handler is None:
            return method_not_allowed(list(table))
        return handler(request, **kwargs)

    return view


def url_patterns() -> list[URLPattern]:
    exempt = bool(options().get("CSRF_EXEMPT"))
    patterns = []
    for route, table in ROUTES.items():
        view = _dispatcher(table)
        patterns.append(path(route, csrf_exempt(view) if exempt else view, name=_name(table)))
    return patterns


def _name(table: dict[str, Callable[..., HttpResponse]]) -> str:
    return next(iter(table.values())).__name__
