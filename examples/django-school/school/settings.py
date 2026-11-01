"""django-school settings: a small ed-tech site wired to dpdpkit-django. Demo only; not production settings."""

import os
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-secret-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.admin",
    "dpdpkit.django",
    "school",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "school.urls"
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
CONFORMANCE = os.environ.get("DPDPKIT_CONFORMANCE") == "1"


def _database() -> dict[str, object]:
    """``DATABASE_URL`` (postgres://, mysql://, sqlite://) if set, else a SQLite file (``DATABASE_NAME``)."""
    url = urlparse(os.environ.get("DATABASE_URL", ""))
    engines = {
        "postgres": "django.db.backends.postgresql",
        "postgresql": "django.db.backends.postgresql",
        "mysql": "django.db.backends.mysql",
    }
    if url.scheme in engines:
        return {
            "ENGINE": engines[url.scheme],
            "NAME": url.path.lstrip("/"),
            "USER": unquote(url.username or ""),
            "PASSWORD": unquote(url.password or ""),
            "HOST": url.hostname or "",
            "PORT": str(url.port or ""),
        }
    # Conformance runs the app in threads, so give it a file rather than a per-connection :memory: database.
    default = str(Path(tempfile.gettempdir()) / "dpdpkit-school-conformance.db") if CONFORMANCE else "school.db"
    return {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ.get("DATABASE_NAME", str(BASE_DIR / default))}


DATABASES = {"default": _database()}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
LOGIN_URL = "/login/"

DPDPKIT = {
    "CONFIG": BASE_DIR / "dpdpkit.yaml",
    "SIGNING_KEY": os.environ.get("DPDPKIT_SIGNING_KEY", "dev-only-signing-key"),
    "DRF": False,
    # The signed-in user's id is the principal; staff are admins (the defaults).
}
if CONFORMANCE:  # test-only convention from dpdpkit-spec: identity comes from headers. Never enable in production.
    DPDPKIT |= {
        "PRINCIPAL_RESOLVER": "school.conformance.principal",
        "ADMIN_GUARD": "school.conformance.admin_guard",
        "CSRF_EXEMPT": True,
    }

# How long a guardian's verification link works, in seconds.
GUARDIAN_LINK_MAX_AGE = 7 * 24 * 3600
