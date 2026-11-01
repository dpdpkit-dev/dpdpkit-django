"""Django REST framework viewset for the REST contract; used when ``rest_framework`` is installed.

One ``ViewSet`` carries an action per endpoint. The handlers do their own authentication through the
project's principal resolver and admin guard, so DRF's permission classes stay empty.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import MethodNotAllowed as DrfMethodNotAllowed
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from django.urls import URLPattern, path
from dpdpkit.errors import DpdpkitError

from .api import ROUTES, View
from .http import error_response, render_dpdpkit_error


def _action(view: View) -> Any:
    def action(self: ViewSet, request: Request, **kwargs: str) -> Any:
        return view(request._request, **kwargs)

    action.__name__ = view.__name__
    action.__doc__ = f"``{view.__name__}``: see the dpdpkit REST contract."
    return action


class _JsonOnly(BaseContentNegotiation):
    """Always JSON: ``?format=`` belongs to the export endpoint, not to DRF's renderer override."""

    def select_parser(self, request: Request, parsers: Iterable[Any]) -> Any:
        return next(iter(parsers), None)

    def select_renderer(self, request: Request, renderers: Iterable[Any], format_suffix: str | None = None) -> Any:
        renderer = next(iter(renderers))
        return (renderer, renderer.media_type)


class _Base(ViewSet):
    content_negotiation_class = _JsonOnly
    authentication_classes = (SessionAuthentication,)  # CSRF only for session-authenticated callers
    permission_classes = ()
    renderer_classes = (JSONRenderer,)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, DpdpkitError):
            return render_dpdpkit_error(exc)  # type: ignore[return-value]
        if isinstance(exc, DrfMethodNotAllowed):
            return error_response(405, "method_not_allowed", "Method not allowed.")  # type: ignore[return-value]
        return super().handle_exception(exc)  # type: ignore[no-any-return]


DpdpkitViewSet = type(
    "DpdpkitViewSet",
    (_Base,),
    {view.__name__: _action(view) for table in ROUTES.values() for view in table.values()},
)


def url_patterns() -> list[URLPattern]:
    return [
        path(
            route,
            DpdpkitViewSet.as_view({method: view.__name__ for method, view in table.items()}),  # type: ignore[attr-defined]
            name=next(iter(table.values())).__name__,
        )
        for route, table in ROUTES.items()
    ]
