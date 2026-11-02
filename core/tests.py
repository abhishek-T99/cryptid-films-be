from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.views import SpectacularAPIView
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.test import APIClient, APITestCase


class HealthEndpointTests(APITestCase):
    def test_health_reports_ok(self):
        response = self.client.get(reverse("api:core:health"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_health_seeds_the_csrf_cookie(self):
        """The frontend relies on this to obtain a token for unsafe methods.

        Django only sets the csrftoken cookie for views that ask for it, so
        dropping @ensure_csrf_cookie from the view would silently break every
        write the React app makes.
        """
        response = self.client.get(reverse("api:core:health"))

        self.assertIn("csrftoken", response.cookies)
        self.assertTrue(response.cookies["csrftoken"].value)


class CorsConfigurationTests(APITestCase):
    def test_allowed_origin_receives_cors_headers(self):
        response = self.client.get(
            reverse("api:core:health"), headers={"origin": "http://localhost:5173"}
        )

        self.assertEqual(
            response["Access-Control-Allow-Origin"], "http://localhost:5173"
        )

    def test_unlisted_origin_receives_no_cors_headers(self):
        response = self.client.get(
            reverse("api:core:health"), headers={"origin": "http://evil.example"}
        )

        self.assertNotIn("Access-Control-Allow-Origin", response)


class ApiDocsTests(APITestCase):
    def test_schema_is_served(self):
        response = self.client.get(reverse("schema"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("openapi", response.headers["Content-Type"])

    def test_swagger_ui_is_served(self):
        response = self.client.get(reverse("swagger-ui"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_redoc_is_served(self):
        response = self.client.get(reverse("redoc"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_schema_generates_without_warnings(self):
        """A warning here means an endpoint the docs describe incorrectly."""
        from drf_spectacular.validation import validate_schema

        generator = SchemaGenerator()
        schema = generator.get_schema(request=None, public=True)

        validate_schema(schema)
        self.assertIn("/api/health/", schema["paths"])

    def test_health_endpoint_is_documented(self):
        response = self.client.get(reverse("schema"), {"format": "json"})

        paths = response.json()["paths"]
        self.assertIn("/api/health/", paths)
        self.assertIn("200", paths["/api/health/"]["get"]["responses"])
        self.assertIn("503", paths["/api/health/"]["get"]["responses"])


class ApiDocsPermissionTests(APITestCase):
    """With DEBUG off the docs must not be publicly readable.

    `SpectacularAPIView.permission_classes` is a class attribute resolved from
    SPECTACULAR_SETTINGS when the module is imported, so `override_settings`
    cannot change it after the fact — these tests patch the attribute directly,
    which is what the DEBUG=False branch in settings.py ends up producing.
    """

    @patch.object(SpectacularAPIView, "permission_classes", [IsAdminUser])
    def test_anonymous_user_cannot_read_the_schema(self):
        response = self.client.get(reverse("schema"))

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    @patch.object(SpectacularAPIView, "permission_classes", [IsAdminUser])
    def test_staff_user_can_read_the_schema(self):
        staff = get_user_model().objects.create_user(
            username="staff", password="not-a-real-password", is_staff=True
        )
        self.client.force_authenticate(user=staff)

        response = self.client.get(reverse("schema"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch.object(SpectacularAPIView, "permission_classes", [IsAdminUser])
    def test_non_staff_user_cannot_read_the_schema(self):
        user = get_user_model().objects.create_user(
            username="viewer", password="not-a-real-password"
        )
        self.client.force_authenticate(user=user)

        response = self.client.get(reverse("schema"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SessionAuthCsrfTests(APITestCase):
    """Pins the contract `src/lib/api.js` on the frontend is written against."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="editor", password="not-a-real-password"
        )
        # The default APIClient bypasses CSRF; this one does not, which is how
        # a real browser request behaves.
        self.client = APIClient(enforce_csrf_checks=True)

    def test_unsafe_request_without_csrf_token_is_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("api:core:health"), {})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unsafe_request_with_csrf_token_passes_the_csrf_check(self):
        self.client.force_login(self.user)
        token = self.client.get(reverse("api:core:health")).cookies["csrftoken"].value

        response = self.client.post(
            reverse("api:core:health"), {}, headers={"x-csrftoken": token}
        )

        # 405: the request got past CSRF and authentication, and was turned
        # away only because health is GET-only. That is the check passing.
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
