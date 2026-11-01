from django.urls import include, path

from dpdpkit.django import api  # noqa: F401
from dpdpkit.django.drf import url_patterns

urlpatterns = [path("dpdp/", include((url_patterns(), "dpdpkit")))]
