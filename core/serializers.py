from rest_framework import serializers


class HealthSerializer(serializers.Serializer):
    """Shape of the /api/health/ response.

    Declared so the generated OpenAPI schema describes the endpoint properly;
    the view builds its payload directly rather than going through this.
    """

    status = serializers.ChoiceField(choices=["ok", "error"])
    database = serializers.ChoiceField(choices=["ok", "unavailable"])
