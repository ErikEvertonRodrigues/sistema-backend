import os
import runpy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured

from .environment import env_bool, env_list, secret_key_from_env


SYNTHETIC_KEY = "synthetic-configuration-test-only-" * 3


class EnvironmentParsingTests(TestCase):
    def test_boolean_true_values(self):
        for value in ("true", "1", "yes", "on", " TRUE "):
            with self.subTest(value=value), patch.dict(os.environ, {"FLAG": value}):
                self.assertIs(env_bool("FLAG"), True)

    def test_boolean_false_values(self):
        for value in ("false", "0", "no", "off", " False "):
            with self.subTest(value=value), patch.dict(os.environ, {"FLAG": value}):
                self.assertIs(env_bool("FLAG", default=True), False)

    def test_missing_boolean_uses_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIs(env_bool("FLAG"), False)
            self.assertIs(env_bool("FLAG", default=True), True)

    def test_invalid_boolean_fails_clearly(self):
        for value in ("", " ", "tru", "2"):
            with self.subTest(value=value), patch.dict(os.environ, {"FLAG": value}):
                with self.assertRaisesRegex(ImproperlyConfigured, "FLAG must be"):
                    env_bool("FLAG")

    def test_hosts_are_split_trimmed_and_empty_entries_omitted(self):
        with patch.dict(os.environ, {"HOSTS": " localhost, 127.0.0.1, ,192.168.0.10, "}):
            self.assertEqual(env_list("HOSTS"), ["localhost", "127.0.0.1", "192.168.0.10"])

    def test_missing_and_empty_lists(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(env_list("HOSTS"), [])
            self.assertEqual(env_list("HOSTS", default="localhost"), ["localhost"])
        with patch.dict(os.environ, {"HOSTS": " , "}):
            self.assertEqual(env_list("HOSTS", default="localhost"), [])

    def test_secret_is_read_from_environment(self):
        with patch.dict(os.environ, {"DJANGO_SECRET_KEY": SYNTHETIC_KEY}):
            self.assertEqual(secret_key_from_env(), SYNTHETIC_KEY)

    def test_missing_secret_fails(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ImproperlyConfigured, "DJANGO_SECRET_KEY is required"):
                secret_key_from_env()

    def test_insecure_secrets_fail_without_echoing_the_secret(self):
        for key in ("", " " * 50, "change-me", "x" * 50, SYNTHETIC_KEY[:49],
                    "django-insecure-" + SYNTHETIC_KEY):
            with self.subTest(key=key), patch.dict(os.environ, {"DJANGO_SECRET_KEY": key}):
                with self.assertRaises(ImproperlyConfigured) as error:
                    secret_key_from_env()
                self.assertIn("DJANGO_SECRET_KEY", str(error.exception))
                if key:
                    self.assertNotIn(key, str(error.exception))


class SettingsEnvironmentTests(TestCase):
    def load_settings(self, **overrides):
        environment = {
            "DJANGO_SECRET_KEY": SYNTHETIC_KEY,
            "DJANGO_ALLOWED_HOSTS": "api.example.test",
            **overrides,
        }
        with patch.dict(os.environ, environment, clear=True):
            return runpy.run_path(
                str(Path(__file__).with_name("settings.py")),
                run_name="mysite.settings_under_test",
            )

    def test_production_defaults_disable_debug_and_enable_https_flags(self):
        config = self.load_settings()
        self.assertIs(config["DEBUG"], False)
        self.assertEqual(config["SECRET_KEY"], SYNTHETIC_KEY)
        self.assertEqual(config["ALLOWED_HOSTS"], ["api.example.test"])
        for name in ("SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT"):
            self.assertIs(config[name], True)

    def test_explicit_development_supports_local_http(self):
        config = self.load_settings(
            DJANGO_DEBUG="true", DJANGO_ALLOWED_HOSTS="localhost, 127.0.0.1"
        )
        self.assertIs(config["DEBUG"], True)
        self.assertEqual(config["ALLOWED_HOSTS"], ["localhost", "127.0.0.1"])
        for name in ("SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT"):
            self.assertIs(config[name], False)

    def test_https_flags_can_be_overridden_explicitly(self):
        for debug, secure in (("true", "true"), ("false", "false")):
            with self.subTest(debug=debug):
                config = self.load_settings(
                    DJANGO_DEBUG=debug, DJANGO_SESSION_COOKIE_SECURE=secure,
                    DJANGO_CSRF_COOKIE_SECURE=secure, DJANGO_SECURE_SSL_REDIRECT=secure,
                )
                for name in ("SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT"):
                    self.assertIs(config[name], secure == "true")

    def test_production_requires_hosts(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "DJANGO_ALLOWED_HOSTS is required"):
            self.load_settings(DJANGO_DEBUG="false", DJANGO_ALLOWED_HOSTS=" , ")

    def test_invalid_secret_prevents_startup_in_any_environment(self):
        for debug in ("true", "false"):
            with self.subTest(debug=debug):
                with self.assertRaisesRegex(ImproperlyConfigured, "DJANGO_SECRET_KEY is required"):
                    self.load_settings(DJANGO_DEBUG=debug, DJANGO_SECRET_KEY="change-me")

    def test_sqlite_stays_in_project_directory(self):
        config = self.load_settings()
        database = config["DATABASES"]["default"]
        self.assertEqual(database["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(database["NAME"], config["BASE_DIR"] / "db.sqlite3")
