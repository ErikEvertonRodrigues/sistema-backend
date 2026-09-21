"""Small, strict parsers for the process environment; no automatic file loading."""

import os

from django.core.exceptions import ImproperlyConfigured


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    raise ImproperlyConfigured(
        f"{name} must be true/false, 1/0, yes/no or on/off."
    )


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def secret_key_from_env():
    key = os.environ.get("DJANGO_SECRET_KEY", "")
    # Match Django's basic deployment checks, including in local development.
    if (
        len(key) < 50
        or len(set(key)) < 5
        or key.startswith("django-insecure-")
        or not key.strip()
    ):
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is required: generate a random key with at least "
            "50 characters and 5 distinct characters, without the django-insecure- prefix."
        )
    return key
