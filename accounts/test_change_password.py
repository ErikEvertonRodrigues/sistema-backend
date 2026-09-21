from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import AccessToken


class ChangePasswordTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = "SenhaAtualSegura123!"
        cls.new_password = "OutraSenhaValida456!"
        cls.user = get_user_model().objects.create_user(
            username="alice", email="alice@example.com", password=cls.password,
            first_name="Alice", last_name="Silva",
        )
        cls.other_user = get_user_model().objects.create_user(
            username="bob", email="bob@example.com", password=cls.password,
        )

    def setUp(self):
        self.url = reverse("change_password")
        response = self.login(self.password)
        self.assertEqual(response.status_code, 200)
        self.tokens = response.data
        self.payload = {
            "current_password": self.password,
            "new_password": self.new_password,
            "new_password_confirm": self.new_password,
        }
        self.initial_hash = self.user.password

    def login(self, password):
        return self.client.post(reverse("login"), {
            "username": self.user.username, "password": password,
        }, format="json")

    def change_password(self, payload=None, access=None, url=None):
        return self.client.post(
            url or self.url, self.payload if payload is None else payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.tokens['access'] if access is None else access}",
        )

    def assert_password_unchanged(self):
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, self.initial_hash)

    def assert_invalid_payload(self, payload, field=None):
        response = self.change_password(payload)
        self.assertEqual(response.status_code, 400)
        if field:
            self.assertIn(field, response.data)
        for secret in (self.password, self.new_password):
            self.assertNotIn(secret, response.content.decode())
        self.assert_password_unchanged()

    def test_success_returns_empty_204_and_persists_password_hash(self):
        response = self.change_password()
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertFalse(self.user.check_password(self.password))
        self.assertNotEqual(self.user.password, self.new_password)
        self.assertNotEqual(self.user.password, self.initial_hash)
        self.assertEqual(self.user.username, "alice")
        self.assertEqual(self.user.email, "alice@example.com")
        self.assertEqual(self.user.first_name, "Alice")
        self.assertEqual(self.user.last_name, "Silva")
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.other_user.refresh_from_db()
        self.assertTrue(self.other_user.check_password(self.password))

    def test_old_login_fails_and_new_login_works(self):
        self.assertEqual(self.change_password().status_code, 204)
        old_login = self.login(self.password)
        self.assertEqual(old_login.status_code, 401)
        self.assertNotIn("access", old_login.data)
        new_login = self.login(self.new_password)
        self.assertEqual(new_login.status_code, 200)
        self.assertEqual(set(new_login.data), {"access", "refresh"})
        self.assert_tokens_work(new_login.data, self.user)

    def assert_tokens_work(self, tokens, user):
        me = self.client.get(
            reverse("current_user"), HTTP_AUTHORIZATION=f"Bearer {tokens['access']}"
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["id"], user.pk)
        refreshed = self.client.post(
            reverse("token_refresh"), {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(refreshed.status_code, 200)
        me = self.client.get(
            reverse("current_user"),
            HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}",
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["id"], user.pk)

    def test_wrong_current_password_is_rejected(self):
        self.assert_invalid_payload(
            {**self.payload, "current_password": "incorrect"}, "current_password"
        )

    def test_password_confirmation_must_match(self):
        self.assert_invalid_payload(
            {**self.payload, "new_password_confirm": "DifferentPassword789!"},
            "new_password_confirm",
        )

    def test_current_password_cannot_be_reused(self):
        self.assert_invalid_payload({
            **self.payload, "new_password": self.password,
            "new_password_confirm": self.password,
        }, "new_password")

    def test_weak_and_similar_passwords_are_rejected(self):
        for password in ("123", "password", self.user.username, self.user.email):
            with self.subTest(password=password):
                self.assert_invalid_payload({
                    **self.payload, "new_password": password,
                    "new_password_confirm": password,
                }, "new_password")

    def test_each_password_validator_receives_current_user(self):
        cases = (
            ("UserAttributeSimilarityValidator", self.user.username),
            ("UserAttributeSimilarityValidator", self.user.email),
            ("UserAttributeSimilarityValidator", self.user.first_name),
            ("UserAttributeSimilarityValidator", self.user.last_name),
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
                    self.assert_invalid_payload({
                        **self.payload, "new_password": password,
                        "new_password_confirm": password,
                    }, "new_password")

    @override_settings(AUTH_PASSWORD_VALIDATORS=[{
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 40},
    }])
    def test_password_validator_options_are_respected(self):
        self.assert_invalid_payload(self.payload, "new_password")

    def test_missing_authentication_is_rejected(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 401)
        self.assert_password_unchanged()

    def test_invalid_access_is_rejected(self):
        self.assertEqual(self.change_password(access="invalid-token").status_code, 401)
        self.assert_password_unchanged()

    def test_expired_access_is_rejected(self):
        token = AccessToken(self.tokens["access"])
        token.set_exp(lifetime=timedelta(seconds=-1))
        self.assertEqual(self.change_password(access=str(token)).status_code, 401)
        self.assert_password_unchanged()

    def test_refresh_cannot_authenticate_password_change(self):
        self.assertEqual(
            self.change_password(access=self.tokens["refresh"]).status_code, 401
        )
        self.assert_password_unchanged()

    def test_missing_fields_are_rejected_individually(self):
        for field in self.payload:
            with self.subTest(field=field):
                payload = self.payload.copy()
                del payload[field]
                self.assert_invalid_payload(payload, field)

    def test_empty_null_and_structured_fields_are_rejected(self):
        for field in self.payload:
            for value in ("", None, [], {}):
                with self.subTest(field=field, value=value):
                    self.assert_invalid_payload({**self.payload, field: value}, field)

    def test_extra_fields_cannot_select_user_or_modify_privileges(self):
        fields = {
            "user_id": self.other_user.pk,
            "username": self.other_user.username,
            "email": self.other_user.email,
            "is_staff": True,
            "unexpected": "value",
        }
        original_other_hash = self.other_user.password
        for field, value in fields.items():
            with self.subTest(field=field):
                self.assert_invalid_payload({**self.payload, field: value}, field)
                self.other_user.refresh_from_db()
                self.assertEqual(self.other_user.password, original_other_hash)

    def test_query_parameters_cannot_select_another_user(self):
        original_other_hash = self.other_user.password
        response = self.change_password(url=f"{self.url}?user_id={self.other_user.pk}")
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.other_user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertEqual(self.other_user.password, original_other_hash)

    def test_non_object_json_is_rejected(self):
        for payload in ([], [self.payload], "invalid", 123):
            with self.subTest(payload=payload):
                self.assert_invalid_payload(payload)

    def test_password_whitespace_is_preserved(self):
        current_password = " " + self.password + " "
        new_password = " " + self.new_password + " "
        self.user.set_password(current_password)
        self.user.save(update_fields=["password"])
        self.tokens = self.login(current_password).data
        response = self.change_password({
            "current_password": current_password,
            "new_password": new_password,
            "new_password_confirm": new_password,
        })
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertFalse(self.user.check_password(new_password.strip()))

    def test_existing_access_is_rejected_after_password_change(self):
        self.assertEqual(self.change_password().status_code, 204)
        response = self.client.get(
            reverse("current_user"),
            HTTP_AUTHORIZATION=f"Bearer {self.tokens['access']}",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "password_changed")

    def test_existing_refresh_is_rejected_after_password_change(self):
        self.assertEqual(self.change_password().status_code, 204)
        response = self.client.post(
            reverse("token_refresh"), {"refresh": self.tokens["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "password_changed")
        self.assertNotIn("access", response.data)
        self.assertFalse(BlacklistedToken.objects.exists())

    def test_old_access_cannot_logout_after_password_change(self):
        self.assertEqual(self.change_password().status_code, 204)
        response = self.client.post(
            reverse("logout"), {"refresh": self.tokens["refresh"]}, format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.tokens['access']}",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "password_changed")
        self.assertFalse(BlacklistedToken.objects.exists())

    def test_password_change_does_not_invalidate_other_users_tokens(self):
        other_login = self.client.post(reverse("login"), {
            "username": self.other_user.username, "password": self.password,
        }, format="json")
        self.assertEqual(other_login.status_code, 200)
        self.assertEqual(self.change_password().status_code, 204)
        self.assert_tokens_work(other_login.data, self.other_user)

    def test_tokens_work_when_password_change_is_rejected(self):
        self.assert_invalid_payload({**self.payload, "current_password": "incorrect"})
        self.assert_tokens_work(self.tokens, self.user)

    def test_direct_password_change_also_invalidates_existing_tokens(self):
        self.user.set_password(self.new_password)
        self.user.save(update_fields=["password"])
        me = self.client.get(
            reverse("current_user"),
            HTTP_AUTHORIZATION=f"Bearer {self.tokens['access']}",
        )
        self.assertEqual(me.status_code, 401)
        refresh = self.client.post(
            reverse("token_refresh"), {"refresh": self.tokens["refresh"]}, format="json"
        )
        self.assertEqual(refresh.status_code, 401)
        self.assertNotIn("access", refresh.data)
