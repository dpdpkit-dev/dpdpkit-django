from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(template_name="school/form.html", extra_context={"title": "Sign in"})),
    path("course/", views.course, name="course"),
    path("privacy/preferences/", views.preferences, name="preferences"),
    path("guardian/<str:token>/", views.guardian_consent, name="guardian-consent"),
    path("dpdp/", include("dpdpkit.django.urls")),
    path("admin/", admin.site.urls),
]
