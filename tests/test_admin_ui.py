from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

pytestmark = pytest.mark.urls("tests.urls_auto")


def _body(response: Any) -> bytes:
    return b"".join(response.streaming_content)


def test_dashboard_page_is_served(client: Client) -> None:
    response = client.get("/dpdp/admin/ui/")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert b"dpdpkit admin" in _body(response)


def test_named_file_is_served(client: Client) -> None:
    response = client.get("/dpdp/admin/ui/index.html")
    assert response.status_code == 200
    assert b"dpdpkit admin" in _body(response)


@pytest.mark.parametrize("path", ["missing.js", "assets/", "../views.py", "..%2Fviews.py"])
def test_only_bundle_files_are_served(client: Client, path: str) -> None:
    assert client.get(f"/dpdp/admin/ui/{path}").status_code in (400, 404)


def test_writes_are_rejected(client: Client) -> None:
    assert client.post("/dpdp/admin/ui/").status_code == 405
