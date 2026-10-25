"""
Test settings — overrides the database to SQLite in-memory so tests run
without a live Postgres server. All other settings are inherited unchanged.
"""
from .settings import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Keep test output quiet — suppress whatsmeow-style log noise if any
LOGGING_CONFIG = None

# Use a predictable secret in CI
SECRET_KEY = "test-secret-key-not-for-production"
