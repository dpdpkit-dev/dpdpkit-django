import os

SECRET_KEY = "test"
INSTALLED_APPS = ["dpdpkit.django"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ.get("DPDPKIT_TEST_DB", ":memory:")}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
