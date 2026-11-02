from django.db import connection
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.serializers import HealthSerializer


# DRF's SessionAuthentication enforces CSRF on unsafe methods, and Django only
# sets the csrftoken cookie for views that ask for it. The frontend calls this
# endpoint on startup, so seeding the cookie here means later POST/PATCH/DELETE
# requests have a token to send back.
@extend_schema(
    tags=["system"],
    summary="Health check",
    description=(
        "Reports whether the API is up and can reach its database. Used by "
        "deploys and uptime monitoring, and by the frontend on startup to "
        "obtain a CSRF token."
    ),
    responses={
        200: OpenApiResponse(
            response=HealthSerializer,
            description="The API and its database are both healthy.",
            examples=[
                OpenApiExample(
                    "Healthy",
                    value={"status": "ok", "database": "ok"},
                    response_only=True,
                )
            ],
        ),
        503: OpenApiResponse(
            response=HealthSerializer,
            description="The API is up but the database is unreachable.",
            examples=[
                OpenApiExample(
                    "Database down",
                    value={"status": "error", "database": "unavailable"},
                    response_only=True,
                )
            ],
        ),
    },
)
@ensure_csrf_cookie
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Liveness and database check, used by deploys and uptime monitoring."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return Response(
            {"status": "error", "database": "unavailable"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"status": "ok", "database": "ok"})
