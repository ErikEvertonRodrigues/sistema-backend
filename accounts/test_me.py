import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken


class CurrentUserTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = "SenhaDeTesteMe123!"
        cls.user = get_user_model().objects.create_user(
            username="alice", email="alice@example.com", password=cls.password,
            first_name="Alice", last_name="Silva",
        )
        cls.other_user = get_user_model().objects.create_user(
            username="bob", email="bob@example.com", password=cls.password,
            first_name="Bob", last_name="Souza",
        )

    def setUp(self):
        self.url = reverse("current_user")
        self.tokens = self.login(self.user)

    def login(self, user):
        response = self.client.post(reverse("login"), {
            "username": user.username, "password": self.password,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        return response.data

    def assert_public_user(self, response, user):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            "id": user.pk,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        })

    def test_authenticated_user_receives_only_public_fields(self):
        response = self.client.get(
            self.url, HTTP_AUTHORIZATION=f"Bearer {self.tokens['access']}"
        )
        self.assert_public_user(response, self.user)
        for field in (
            "password", "is_staff", "is_superuser", "groups", "user_permissions",
            "last_login", "date_joined", "is_active",
        ):
            self.assertNotIn(field, response.data)

    def test_missing_access_is_rejected(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_invalid_access_is_rejected(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION="Bearer invalid-token")
        self.assertEqual(response.status_code, 401)

    def test_expired_access_is_rejected(self):
        access = AccessToken(self.tokens["access"])
        access.set_exp(lifetime=timedelta(seconds=-1))
        response = self.client.get(self.url, HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(response.status_code, 401)

    def test_refresh_cannot_be_used_as_bearer(self):
        response = self.client.get(
            self.url, HTTP_AUTHORIZATION=f"Bearer {self.tokens['refresh']}"
        )
        self.assertEqual(response.status_code, 401)

    def test_switching_access_token_switches_only_current_user(self):
        other_tokens = self.login(self.other_user)
        for user, tokens in ((self.user, self.tokens), (self.other_user, other_tokens)):
            with self.subTest(username=user.username):
                response = self.client.get(
                    self.url, HTTP_AUTHORIZATION=f"Bearer {tokens['access']}"
                )
                self.assert_public_user(response, user)

    def test_query_parameters_cannot_select_another_user(self):
        response = self.client.get(
            self.url, {"user_id": self.other_user.pk},
            HTTP_AUTHORIZATION=f"Bearer {self.tokens['access']}",
        )
        self.assert_public_user(response, self.user)

    def test_get_payload_cannot_select_another_user(self):
        response = self.client.generic(
            "GET", self.url, data=json.dumps({"user_id": self.other_user.pk}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.tokens['access']}",
        )
        self.assert_public_user(response, self.user)

    def test_previously_issued_access_is_rejected_for_inactive_user(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.get(
            self.url, HTTP_AUTHORIZATION=f"Bearer {self.tokens['access']}"
        )
        self.assertEqual(response.status_code, 401)

    def test_write_methods_are_not_allowed_and_do_not_change_user(self):
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    self.url, {"username": "changed", "first_name": "Changed"},
                    format="json", HTTP_AUTHORIZATION=f"Bearer {self.tokens['access']}",
                )
                self.assertEqual(response.status_code, 405)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "alice")
        self.assertEqual(self.user.first_name, "Alice")
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
