from django.contrib import admin
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .serializer import RegisterSerializer


class UserTests(TestCase):
    def test_active_user_model(self):
        self.assertEqual(get_user_model()._meta.label, "accounts.User")

    def test_create_user_hashes_password_and_authenticates_by_username(self):
        user = get_user_model().objects.create_user(
            username="alice", email="alice@example.com", password="test-password"
        )
        user.refresh_from_db()

        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertNotEqual(user.password, "test-password")
        self.assertTrue(user.check_password("test-password"))
        self.assertEqual(
            authenticate(username="alice", password="test-password"), user
        )

    def test_create_superuser_hashes_password(self):
        user = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="test-password"
        )
        user.refresh_from_db()

        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertNotEqual(user.password, "test-password")
        self.assertTrue(user.check_password("test-password"))

    def test_model_validation_requires_valid_email(self):
        for email in ("", "invalid-email"):
            with self.subTest(email=email):
                user = get_user_model()(username="alice", email=email)
                user.set_password("test-password")
                with self.assertRaises(ValidationError) as error:
                    user.full_clean()
                self.assertIn("email", error.exception.message_dict)

    def test_serializer_requires_email(self):
        for extra_data in ({}, {"email": ""}, {"email": "invalid-email"}):
            with self.subTest(extra_data=extra_data):
                serializer = RegisterSerializer(
                    data={"username": "alice", "password": "test-password", **extra_data}
                )
                self.assertFalse(serializer.is_valid())
                self.assertIn("email", serializer.errors)

    def test_token_references_custom_user(self):
        user = get_user_model().objects.create_user(
            username="alice", email="alice@example.com", password="test-password"
        )
        token = RefreshToken.for_user(user)
        decoded = RefreshToken(str(token))

        self.assertEqual(str(decoded["user_id"]), str(user.pk))
        self.assertEqual(str(token.access_token["user_id"]), str(user.pk))


class UserAdminTests(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="test-password"
        )
        self.client.force_login(self.superuser)

    def test_admin_pages_use_custom_user(self):
        self.assertIn(get_user_model(), admin.site._registry)
        for name, args in (
            ("admin:accounts_user_changelist", []),
            ("admin:accounts_user_add", []),
            ("admin:accounts_user_change", [self.superuser.pk]),
        ):
            with self.subTest(name=name):
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 200)
                if name != "admin:accounts_user_changelist":
                    form = response.context["adminform"].form
                    self.assertTrue(form.fields["email"].required)

    def test_admin_requires_email_when_creating_user(self):
        response = self.client.post(
            reverse("admin:accounts_user_add"),
            {"username": "alice", "usable_password": "false"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["adminform"].form.errors)
        self.assertFalse(get_user_model().objects.filter(username="alice").exists())

    def test_admin_creates_user_with_hashed_password(self):
        response = self.client.post(
            reverse("admin:accounts_user_add"),
            {
                "username": "alice",
                "email": "alice@example.com",
                "usable_password": "true",
                "password1": "Admin-test-password-7842",
                "password2": "Admin-test-password-7842",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username="alice")
        self.assertTrue(user.check_password("Admin-test-password-7842"))


class RegistrationTests(APITestCase):
    def setUp(self):
        self.url = reverse("register")
        self.payload = {
            "username": "new-user",
            "email": "new-user@example.com",
            "password": "UmaSenhaValida123!",
        }

    def assert_invalid_registration(self, payload, field=None):
        count_before = get_user_model().objects.count()
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(get_user_model().objects.count(), count_before)
        if field:
            self.assertIn(field, response.data)
        return response

    def test_registration_creates_custom_user_and_returns_only_public_fields(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(get_user_model()._meta.label, "accounts.User")
        user = get_user_model().objects.get(username=self.payload["username"])
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(response.data, {
            "id": user.pk,
            "username": self.payload["username"],
            "email": self.payload["email"],
        })
        self.assertTrue(user.check_password(self.payload["password"]))
        self.assertNotEqual(user.password, self.payload["password"])
        self.assertNotIn("password", response.data)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.groups.exists())
        self.assertFalse(user.user_permissions.exists())

    def test_password_is_hashed_before_first_save(self):
        saved_passwords = []

        def capture_password(sender, instance, **kwargs):
            saved_passwords.append(instance.password)

        pre_save.connect(capture_password, sender=get_user_model())
        try:
            response = self.client.post(self.url, self.payload, format="json")
        finally:
            pre_save.disconnect(capture_password, sender=get_user_model())

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(saved_passwords), 1)
        self.assertNotEqual(saved_passwords[0], self.payload["password"])
        self.assertTrue(check_password(self.payload["password"], saved_passwords[0]))

    def test_administrative_privileges_are_rejected(self):
        self.assert_invalid_registration({
            **self.payload, "is_superuser": True, "is_staff": True,
        }, "is_superuser")

    def test_each_internal_field_is_rejected(self):
        group = Group.objects.create(name="restricted")
        permission = Permission.objects.get(
            content_type__app_label="accounts", codename="change_user"
        )
        internal_fields = {
            "is_staff": True,
            "is_superuser": True,
            "is_active": False,
            "groups": [group.pk],
            "user_permissions": [permission.pk],
            "date_joined": "2020-01-01T00:00:00Z",
            "last_login": "2020-01-01T00:00:00Z",
            "id": 123,
        }
        for field, value in internal_fields.items():
            with self.subTest(field=field):
                self.assert_invalid_registration({**self.payload, field: value}, field)

    def test_unknown_fields_are_rejected(self):
        for field in ("first_name", "unexpected"):
            with self.subTest(field=field):
                self.assert_invalid_registration({**self.payload, field: "value"}, field)

    def test_required_fields_cannot_be_omitted(self):
        for field in self.payload:
            with self.subTest(field=field):
                payload = self.payload.copy()
                del payload[field]
                self.assert_invalid_registration(payload, field)

    def test_required_fields_reject_blank_null_and_structured_values(self):
        for field in self.payload:
            for value in ("", None, [], {}):
                with self.subTest(field=field, value=value):
                    self.assert_invalid_registration({**self.payload, field: value}, field)

    def test_invalid_username_is_rejected(self):
        for username in ("invalid username", "a" * 151):
            with self.subTest(username=username):
                self.assert_invalid_registration(
                    {**self.payload, "username": username}, "username"
                )

    def test_invalid_email_is_rejected(self):
        self.assert_invalid_registration(
            {**self.payload, "email": "invalid-email"}, "email"
        )

    def test_duplicate_username_is_rejected(self):
        existing = get_user_model().objects.create_user(**self.payload)
        self.assert_invalid_registration(self.payload, "username")
        existing.refresh_from_db()
        self.assertTrue(existing.check_password(self.payload["password"]))

    def test_weak_password_is_rejected(self):
        self.assert_invalid_registration({**self.payload, "password": "123"}, "password")

    def test_each_configured_password_validator_is_applied(self):
        cases = (
            ("UserAttributeSimilarityValidator", self.payload["username"]),
            ("UserAttributeSimilarityValidator", self.payload["email"]),
            ("MinimumLengthValidator", "Az9!"),
            ("CommonPasswordValidator", "password"),
            ("NumericPasswordValidator", "938174629583"),
        )
        for validator, password in cases:
            with self.subTest(validator=validator, password=password):
                validators = [{
                    "NAME": "django.contrib.auth.password_validation." + validator,
                }]
                with override_settings(AUTH_PASSWORD_VALIDATORS=validators):
                    self.assert_invalid_registration(
                        {**self.payload, "password": password}, "password"
                    )

    @override_settings(AUTH_PASSWORD_VALIDATORS=[{
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 40},
    }])
    def test_password_validator_options_are_respected(self):
        self.assert_invalid_registration(self.payload, "password")

    def test_password_whitespace_is_preserved(self):
        password = " " + self.payload["password"] + " "
        response = self.client.post(
            self.url, {**self.payload, "password": password}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(username=self.payload["username"])
        self.assertTrue(user.check_password(password))
        self.assertFalse(user.check_password(password.strip()))

    def test_non_object_json_is_rejected(self):
        for payload in ([], [self.payload], "invalid", 123):
            with self.subTest(payload=payload):
                self.assert_invalid_registration(payload)
