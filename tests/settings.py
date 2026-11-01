import os
from urllib.parse import unquote, urlparse

SECRET_KEY = "test"
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.admin",
    "rest_framework",
    "dpdpkit.django",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
_url = urlparse(os.environ.get("DPDPKIT_TEST_DATABASE_URL", ""))
if _url.scheme in ("postgres", "postgresql", "mysql"):  # the CI database matrix
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends." + ("mysql" if _url.scheme == "mysql" else "postgresql"),
            "NAME": _url.path.lstrip("/"),
            "USER": unquote(_url.username or ""),
            "PASSWORD": unquote(_url.password or ""),
            "HOST": _url.hostname or "",
            "PORT": str(_url.port or ""),
        }
    }
else:
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ.get("DPDPKIT_TEST_DB", ":memory:")}
    }
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
ROOT_URLCONF = "tests.urls_plain"
ALLOWED_HOSTS = ["testserver"]
DPDPKIT = {
    "PRINCIPAL_RESOLVER": "tests.hooks.principal",
    "ADMIN_GUARD": "tests.hooks.admin_guard",
}
