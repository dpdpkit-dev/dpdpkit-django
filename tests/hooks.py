from __future__ import annotations

from django.http import HttpRequest


def principal(request: HttpRequest) -> str | None:
    return request.headers.get("X-Principal")


def admin_guard(request: HttpRequest) -> str | None:
    return request.headers.get("X-Role")
