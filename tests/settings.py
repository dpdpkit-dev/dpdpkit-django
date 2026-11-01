import os

SECRET_KEY = "test"
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "rest_framework",
    "dpdpkit.django",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ.get("DPDPKIT_TEST_DB", ":memory:")}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
ROOT_URLCONF = "tests.urls_plain"
ALLOWED_HOSTS = ["testserver"]
DPDPKIT = {
    "PRINCIPAL_RESOLVER": "tests.hooks.principal",
    "ADMIN_GUARD": "tests.hooks.admin_guard",
}
