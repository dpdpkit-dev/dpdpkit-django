"""``path("dpdp/", include("dpdpkit.django.urls"))``: the REST contract.

DRF viewsets are used when Django REST framework is installed, plain JSON views otherwise.
``DPDPKIT["DRF"]`` set to ``True`` or ``False`` overrides that choice.
"""

from __future__ import annotations

import importlib.util

from django.urls import URLPattern, URLResolver

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


app_name = "dpdpkit"
urlpatterns = _patterns()
