from django.test import Client, SimpleTestCase, override_settings


class HealthTests(SimpleTestCase):
    def test_public_health_returns_only_status_without_authentication_or_database(self):
        response = self.client.get('/health/', HTTP_AUTHORIZATION='Bearer invalid-test-token')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_health_supports_head(self):
        response = self.client.head('/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'')

    def test_health_rejects_write_methods(self):
        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)('/health/').status_code, 405)


@override_settings(
    DEBUG=False,
    ALLOWED_HOSTS=['example.onrender.com'],
    SECURE_SSL_REDIRECT=True,
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
    CSRF_COOKIE_SECURE=True,
    CSRF_TRUSTED_ORIGINS=[],
)
class ProxyHTTPTests(SimpleTestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST='example.onrender.com', HTTP_X_FORWARDED_PROTO='https')

    def test_forwarded_https_does_not_redirect(self):
        response = self.client.get('/health/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Location', response)

    def test_forwarded_http_redirects_to_https(self):
        response = self.client.get('/health/', HTTP_X_FORWARDED_PROTO='http')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], 'https://example.onrender.com/health/')

    @override_settings(SECURE_PROXY_SSL_HEADER=None)
    def test_forwarded_header_is_ignored_without_proxy_trust(self):
        self.assertEqual(self.client.get('/health/').status_code, 301)

    def test_admin_csrf_accepts_same_origin_https_and_rejects_foreign_origin(self):
        client = Client(
            enforce_csrf_checks=True, HTTP_HOST='example.onrender.com',
            HTTP_X_FORWARDED_PROTO='https',
        )
        response = client.get('/admin/login/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cookies['csrftoken']['secure'])
        payload = {'csrfmiddlewaretoken': client.cookies['csrftoken'].value}
        # Empty credentials redisplay the form without querying any user.
        self.assertEqual(client.post(
            '/admin/login/', payload, HTTP_ORIGIN='https://example.onrender.com',
        ).status_code, 200)
        self.assertEqual(client.post(
            '/admin/login/', payload, HTTP_ORIGIN='https://foreign.example.test',
        ).status_code, 403)

    def test_production_not_found_response_has_no_debug_details(self):
        response = self.client.get('/missing-test-path/')
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b'DJANGO_SETTINGS_MODULE', response.content)
        self.assertNotIn(b'URLconf', response.content)
