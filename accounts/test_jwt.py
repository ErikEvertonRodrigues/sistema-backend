from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, APITestCase
from rest_framework.views import APIView
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken


class ProtectedTestView(APIView):
    """Exercise the configured DRF authentication without adding a public URL."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"id": request.user.pk})


class JWTAuthenticationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = "SenhaDeTesteJWT123!"
        cls.user = get_user_model().objects.create_user(
            username="jwt-user", email="jwt@example.com", password=cls.password
        )

    def login(self, **overrides):
        return self.client.post(reverse("login"), {
            "username": self.user.username,
            "password": self.password,
            **overrides,
        }, format="json")

    def refresh(self, token):
        return self.client.post(
            reverse("token_refresh"), {"refresh": token}, format="json"
        )

    def protected_request(self, token=None, scheme="Bearer"):
        headers = {} if token is None else {"HTTP_AUTHORIZATION": f"{scheme} {token}"}
        request = APIRequestFactory().get("/test-only/", **headers)
        return ProtectedTestView.as_view()(request)

    def assert_authentication_failed(self, response):
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_login_returns_only_access_and_refresh(self):
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"access", "refresh"})
        self.assertTrue(response.data["access"])
        self.assertTrue(response.data["refresh"])
        access = AccessToken(response.data["access"])
        refresh = RefreshToken(response.data["refresh"])
        self.assertEqual(str(access["user_id"]), str(self.user.pk))
        self.assertEqual(str(refresh["user_id"]), str(self.user.pk))
        for token in (access, refresh):
            self.assertFalse({
                "password", "is_staff", "is_superuser", "groups", "user_permissions"
            }.intersection(token.payload))

    def test_access_token_authenticates_real_custom_user(self):
        token = self.login().data["access"]
        response = self.protected_request(token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"id": self.user.pk})
        self.assertEqual(response.renderer_context["request"].user, self.user)
        self.assertIsInstance(response.renderer_context["request"].user, get_user_model())

    def test_repeated_login_succeeds(self):
        first = self.login()
        second = self.login()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first.data["access"], second.data["access"])
        self.assertNotEqual(first.data["refresh"], second.data["refresh"])
        for response in (first, second):
            self.assertEqual(self.protected_request(response.data["access"]).status_code, 200)

    def test_registered_password_with_whitespace_can_login(self):
        password = " " + self.password + " "
        registration = self.client.post(reverse("register"), {
            "username": "whitespace-user",
            "email": "whitespace@example.com",
            "password": password,
        }, format="json")

        self.assertEqual(registration.status_code, 201)
        response = self.login(username="whitespace-user", password=password)
        self.assertEqual(response.status_code, 200)
        self.assert_authentication_failed(
            self.login(username="whitespace-user", password=password.strip())
        )

    def test_wrong_password_and_unknown_username_return_same_error(self):
        wrong_password = self.login(password="incorrect")
        unknown_username = self.login(username="nonexistent")

        self.assert_authentication_failed(wrong_password)
        self.assert_authentication_failed(unknown_username)
        self.assertEqual(wrong_password.data, unknown_username.data)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assert_authentication_failed(self.login())

    def test_missing_login_fields_return_400(self):
        payload = {"username": self.user.username, "password": self.password}
        for field in payload:
            with self.subTest(field=field):
                response = self.client.post(
                    reverse("login"),
                    {key: value for key, value in payload.items() if key != field},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)

    def test_login_rejects_extra_fields(self):
        response = self.login(is_staff=True)
        self.assertEqual(response.status_code, 400)
        self.assertIn("is_staff", response.data)
        self.assertNotIn("access", response.data)

    def test_refresh_rejects_extra_and_read_only_fields(self):
        tokens = self.login().data
        for field in ("user_id", "access"):
            with self.subTest(field=field):
                response = self.client.post(reverse("token_refresh"), {
                    "refresh": tokens["refresh"], field: "unexpected",
                }, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
        self.assertEqual(self.refresh(tokens["refresh"]).status_code, 200)

    def test_tokens_without_revocation_claim_require_new_login(self):
        tokens = self.login().data
        access = AccessToken(tokens["access"])
        refresh = RefreshToken(tokens["refresh"])
        # Simulate tokens issued before CHECK_REVOKE_TOKEN was enabled.
        del access[jwt_settings.REVOKE_TOKEN_CLAIM]
        del refresh[jwt_settings.REVOKE_TOKEN_CLAIM]
        self.assert_authentication_failed(self.protected_request(str(access)))
        self.assert_authentication_failed(self.refresh(str(refresh)))

    def test_blank_null_and_structured_login_fields_return_400(self):
        for field in ("username", "password"):
            for value in ("", None, [], {}):
                with self.subTest(field=field, value=value):
                    response = self.login(**{field: value})
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(field, response.data)

    def test_refresh_returns_new_access_without_rotating_refresh(self):
        tokens = self.login().data
        for _ in range(2):
            response = self.refresh(tokens["refresh"])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.data), {"access"})
            self.assertNotEqual(response.data["access"], tokens["access"])
            self.assertEqual(self.protected_request(response.data["access"]).status_code, 200)

    def test_invalid_refresh_is_rejected(self):
        self.assert_authentication_failed(self.refresh("invalid-token"))

    def test_expired_refresh_is_rejected(self):
        token = RefreshToken.for_user(self.user)
        token.set_exp(lifetime=timedelta(seconds=-1))
        self.assert_authentication_failed(self.refresh(str(token)))

    def test_access_cannot_be_used_as_refresh(self):
        self.assert_authentication_failed(self.refresh(self.login().data["access"]))

    def test_missing_or_invalid_refresh_field_returns_400(self):
        for payload in ({}, {"refresh": ""}, {"refresh": None}, {"refresh": []}):
            with self.subTest(payload=payload):
                response = self.client.post(reverse("token_refresh"), payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn("refresh", response.data)

    def test_refresh_for_inactive_user_is_rejected(self):
        token = self.login().data["refresh"]
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assert_authentication_failed(self.refresh(token))

    def test_refresh_for_deleted_user_is_rejected(self):
        token = self.login().data["refresh"]
        self.user.delete()
        self.assert_authentication_failed(self.refresh(token))

    def test_invalid_access_is_rejected(self):
        response = self.protected_request("invalid-token")
        self.assert_authentication_failed(response)
        self.assertTrue(response["WWW-Authenticate"].startswith("Bearer"))

    def test_expired_access_is_rejected(self):
        token = AccessToken.for_user(self.user)
        token.set_exp(lifetime=timedelta(seconds=-1))
        self.assert_authentication_failed(self.protected_request(str(token)))

    def test_missing_access_is_rejected(self):
        response = self.protected_request()
        self.assert_authentication_failed(response)
        self.assertFalse(response.renderer_context["request"].user.is_authenticated)

    def test_refresh_cannot_authenticate_protected_view(self):
        self.assert_authentication_failed(
            self.protected_request(self.login().data["refresh"])
        )

    def test_old_token_header_is_not_accepted(self):
        self.assert_authentication_failed(
            self.protected_request(self.login().data["access"], scheme="Token")
        )

    def test_access_for_now_inactive_user_is_rejected(self):
        token = self.login().data["access"]
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assert_authentication_failed(self.protected_request(token))

    def test_logout_requires_authentication(self):
        self.assertEqual(self.client.post(reverse("logout"), {}, format="json").status_code, 401)

    def test_mutating_endpoints_only_accept_post(self):
        tokens = self.login().data
        for path in (
            "/accounts/register/", "/accounts/login/", "/accounts/token/refresh/",
            "/accounts/logout/", "/accounts/change-password/",
        ):
            for method in ("get", "put", "patch", "delete"):
                with self.subTest(path=path, method=method):
                    response = getattr(self.client, method)(
                        path, HTTP_AUTHORIZATION=f"Bearer {tokens['access']}"
                    )
                    self.assertEqual(response.status_code, 405)

    def test_django_session_cannot_authenticate_private_api_endpoints(self):
        tokens = self.login().data
        self.client.force_login(self.user)
        requests = (
            ("get", "/accounts/me/", {}),
            ("post", "/accounts/logout/", {"refresh": tokens["refresh"]}),
            ("post", "/accounts/change-password/", {
                "current_password": self.password,
                "new_password": "OutraSenhaValida456!",
                "new_password_confirm": "OutraSenhaValida456!",
            }),
        )
        for method, path, payload in requests:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, payload, format="json")
                self.assertEqual(response.status_code, 401)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))
        self.assertFalse(BlacklistedToken.objects.exists())


class JWTLogoutTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = "SenhaDeTesteLogout123!"
        cls.user = get_user_model().objects.create_user(
            username="logout-user", email="logout@example.com", password=cls.password
        )
        cls.other_user = get_user_model().objects.create_user(
            username="other-user", email="other@example.com", password=cls.password
        )

    def setUp(self):
        self.tokens = self.login(self.user)
        self.refresh_jti = RefreshToken(self.tokens["refresh"])["jti"]

    def login(self, user):
        response = self.client.post(reverse("login"), {
            "username": user.username, "password": self.password,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        return response.data

    def logout(self, payload=None, access=None):
        return self.client.post(
            reverse("logout"),
            {"refresh": self.tokens["refresh"]} if payload is None else payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.tokens['access'] if access is None else access}",
        )

    def refresh(self, token):
        return self.client.post(reverse("token_refresh"), {"refresh": token}, format="json")

    def assert_refresh_not_revoked(self):
        self.assertFalse(BlacklistedToken.objects.exists())
        self.assertEqual(self.refresh(self.tokens["refresh"]).status_code, 200)

    def test_valid_logout_blacklists_refresh_and_returns_empty_204(self):
        response = self.logout()

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        outstanding = OutstandingToken.objects.get(jti=self.refresh_jti)
        self.assertEqual(outstanding.user, self.user)
        self.assertTrue(BlacklistedToken.objects.filter(token=outstanding).exists())

    def test_blacklisted_refresh_cannot_issue_access(self):
        self.assertEqual(self.logout().status_code, 204)
        response = self.refresh(self.tokens["refresh"])
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("access", response.data)

    def test_access_intentionally_remains_valid_after_logout(self):
        self.assertEqual(self.logout().status_code, 204)
        request = APIRequestFactory().get(
            "/test-only/", HTTP_AUTHORIZATION=f"Bearer {self.tokens['access']}"
        )
        response = ProtectedTestView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.renderer_context["request"].user, self.user)

    def test_logout_without_access_is_rejected(self):
        response = self.client.post(
            reverse("logout"), {"refresh": self.tokens["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, 401)
        self.assert_refresh_not_revoked()

    def test_invalid_access_is_rejected(self):
        self.assertEqual(self.logout(access="invalid-token").status_code, 401)
        self.assert_refresh_not_revoked()

    def test_expired_access_is_rejected(self):
        token = AccessToken(self.tokens["access"])
        token.set_exp(lifetime=timedelta(seconds=-1))
        self.assertEqual(self.logout(access=str(token)).status_code, 401)
        self.assert_refresh_not_revoked()

    def test_refresh_cannot_authenticate_logout(self):
        self.assertEqual(self.logout(access=self.tokens["refresh"]).status_code, 401)
        self.assert_refresh_not_revoked()

    def test_missing_refresh_returns_400(self):
        response = self.logout(payload={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("refresh", response.data)
        self.assert_refresh_not_revoked()

    def test_empty_null_or_structured_refresh_returns_400(self):
        for value in ("", None, [], {}):
            with self.subTest(value=value):
                response = self.logout(payload={"refresh": value})
                self.assertEqual(response.status_code, 400)
                self.assertIn("refresh", response.data)
                self.assert_refresh_not_revoked()

    def test_invalid_refresh_is_rejected(self):
        self.assertEqual(self.logout(payload={"refresh": "invalid-token"}).status_code, 401)
        self.assert_refresh_not_revoked()

    def test_expired_refresh_is_rejected(self):
        token = RefreshToken(self.tokens["refresh"])
        token.set_exp(lifetime=timedelta(seconds=-1))
        self.assertEqual(self.logout(payload={"refresh": str(token)}).status_code, 401)
        self.assert_refresh_not_revoked()

    def test_access_in_refresh_field_is_rejected(self):
        response = self.logout(payload={"refresh": self.tokens["access"]})
        self.assertEqual(response.status_code, 401)
        self.assert_refresh_not_revoked()

    def test_second_logout_returns_401_without_duplicate_blacklist(self):
        self.assertEqual(self.logout().status_code, 204)
        self.assertEqual(self.logout().status_code, 401)
        self.assertEqual(BlacklistedToken.objects.count(), 1)

    def test_other_users_refresh_cannot_be_revoked_even_with_forged_user_id(self):
        other_tokens = self.login(self.other_user)
        for extra_fields, expected_status in (({}, 403), ({"user_id": self.user.pk}, 400)):
            with self.subTest(extra_fields=extra_fields):
                response = self.logout(payload={
                    "refresh": other_tokens["refresh"], **extra_fields,
                })
                self.assertEqual(response.status_code, expected_status)
                self.assertFalse(BlacklistedToken.objects.exists())
                self.assertEqual(self.refresh(other_tokens["refresh"]).status_code, 200)
                self.assert_refresh_not_revoked()

    def test_logout_rejects_extra_fields_without_blacklisting_refresh(self):
        response = self.logout(payload={"refresh": self.tokens["refresh"], "is_staff": True})
        self.assertEqual(response.status_code, 400)
        self.assertIn("is_staff", response.data)
        self.assert_refresh_not_revoked()

    def test_login_after_logout_issues_working_tokens(self):
        self.assertEqual(self.logout().status_code, 204)
        new_tokens = self.login(self.user)
        self.assertNotEqual(new_tokens["refresh"], self.tokens["refresh"])
        self.assertEqual(self.refresh(self.tokens["refresh"]).status_code, 401)
        self.assertEqual(self.refresh(new_tokens["refresh"]).status_code, 200)
        self.assertEqual(self.logout(
            payload={"refresh": new_tokens["refresh"]}, access=new_tokens["access"]
        ).status_code, 204)

    def test_logout_revokes_only_selected_session(self):
        tablet_tokens = self.login(self.user)
        self.assertEqual(self.logout().status_code, 204)
        self.assertEqual(self.refresh(self.tokens["refresh"]).status_code, 401)
        self.assertEqual(self.refresh(tablet_tokens["refresh"]).status_code, 200)
        self.assertEqual(BlacklistedToken.objects.count(), 1)

    def test_preexisting_refresh_without_outstanding_record_can_be_revoked(self):
        # Refresh tokens issued before enabling the blacklist have no DB record.
        OutstandingToken.objects.filter(jti=self.refresh_jti).delete()
        self.assertEqual(self.logout().status_code, 204)
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=self.refresh_jti).exists())
        self.assertEqual(self.refresh(self.tokens["refresh"]).status_code, 401)
