"""
Request validation for the routing API.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .services.checkpoints import SAMPLING_INTERVALS_MILES

# Forecast data is available for roughly two weeks; the trip plus the 48 h
# heatmap window must fit inside it.
MAX_DEPARTURE_AHEAD = timedelta(days=7)
MAX_DEPARTURE_PAST = timedelta(hours=12)


class RouteRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=500, help_text="Place name or 'lat,lng'")
    destination = serializers.CharField(max_length=500, help_text="Place name or 'lat,lng'")
    departure_datetime = serializers.DateTimeField(help_text="ISO 8601 departure time")
    load_weight_lbs = serializers.FloatField(min_value=0, max_value=100000)
    interval_miles = serializers.ChoiceField(
        choices=[int(m) for m in SAMPLING_INTERVALS_MILES],
        required=False,
        allow_null=True,
        default=None,
        help_text="Checkpoint spacing: 10, 25 or 50 miles. Omit/null for automatic.",
    )

    def validate_origin(self, value):
        if not value.strip():
            raise serializers.ValidationError("Origin cannot be empty.")
        return value.strip()

    def validate_destination(self, value):
        if not value.strip():
            raise serializers.ValidationError("Destination cannot be empty.")
        return value.strip()

    def validate_departure_datetime(self, value):
        now = timezone.now()
        if value < now - MAX_DEPARTURE_PAST:
            raise serializers.ValidationError("Departure time is in the past.")
        if value > now + MAX_DEPARTURE_AHEAD:
            raise serializers.ValidationError(
                "Departure must be within the next 7 days (forecast range)."
            )
        return value
