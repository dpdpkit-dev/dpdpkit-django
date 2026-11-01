"""Error types and rendering for the contract's ``{"error": {code, message, details}}`` body."""

from __future__ import annotations

from typing import Any

from django.http import JsonResponse
from dpdpkit.errors import DpdpkitError


class Unauthenticated(DpdpkitError):
    code = "unauthenticated"
    http_status = 401


class Forbidden(DpdpkitError):
    code = "forbidden"
    http_status = 403


class NotImplementedYet(DpdpkitError):
    code = "not_implemented"
    http_status = 501


class MethodNotAllowed(DpdpkitError):
    code = "method_not_allowed"
    http_status = 405


def error_response(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message, "details": details or {}}}, status=status)


def render_dpdpkit_error(exc: DpdpkitError) -> JsonResponse:
    status = exc.http_status if exc.http_status != 500 else 400
    return error_response(status, exc.code, exc.message, exc.details)
