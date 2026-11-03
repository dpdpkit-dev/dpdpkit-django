"""``path("dpdp/", include("dpdpkit.django.urls"))``: the REST contract.

DRF viewsets are used when Django REST framework is installed, plain JSON views otherwise.
``DPDPKIT["DRF"]`` set to ``True`` or ``False`` overrides that choice.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from django.http import HttpRequest
from django.http.response import HttpResponseBase
from django.urls import URLPattern, URLResolver, path
from django.views.decorators.http import require_safe
from django.views.static import serve

from . import api  # noqa: F401  (registers the endpoints)
from .conf import options


def _use_drf() -> bool:
    forced = options().get("DRF")
    if forced is None:
        return importlib.util.find_spec("rest_framework") is not None
    return bool(forced)


def _patterns() -> list[URLPattern | URLResolver]:
    if _use_drf():
        from .drf import url_patterns
    else:
        from .views import url_patterns
    return list(url_patterns())


@require_safe
def admin_ui(request: HttpRequest, asset: str = "index.html") -> HttpResponseBase:
    """The prebuilt admin dashboard. A source checkout has a placeholder page instead."""
    return serve(request, asset, document_root=str(Path(__file__).parent / "admin_static"))


app_name = "dpdpkit"
urlpatterns = [
    path("admin/ui/", admin_ui, name="admin_ui"),
    path("admin/ui/<path:asset>", admin_ui, name="admin_ui_asset"),
    *_patterns(),
]
