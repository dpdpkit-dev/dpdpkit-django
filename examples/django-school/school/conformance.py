"""Test-only auth for the dpdpkit conformance suite (``DPDPKIT_CONFORMANCE=1``); never enable in production."""

from django.http import HttpRequest


def principal(request: HttpRequest) -> str | None:
    return request.headers.get("X-DPDP-Test-Principal")


def admin_guard(request: HttpRequest) -> str | None:
    return request.headers.get("X-DPDP-Test-Role")
