"""
Integration tests for POST /api/routes/. External services are mocked.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from routing.services.routing import Route, RoutingUnavailable
from routing.services.weather import Forecasts, WeatherData, WeatherUnavailable

CHICAGO = (41.8781, -87.6298)
DENVER = (39.7392, -104.9903)


def _departure(hours_ahead=2):
    return (timezone.now() + timedelta(hours=hours_ahead)).isoformat()


def _payload(**overrides):
    body = {
        "origin": "Chicago, IL",
        "destination": "Denver, CO",
        "departure_datetime": _departure(),
        "load_weight_lbs": 35000,
    }
    body.update(overrides)
    return body


class FixedForecasts(Forecasts):
    """Same weather everywhere, except a windy band west of -100° longitude."""

    def __init__(self, cell_size, *_):
        super().__init__(cell_size, {})

    def weather_at(self, lat, lng, when):
        wind = 40.0 if lng < -100 else 10.0
        return WeatherData("Clear sky", 60.0, wind, 0.0, 0.0)


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def mocked_services():
    routes = [
        Route([[*CHICAGO], [40.5, -96.0], [*DENVER]], 1000.0, 15.0, 0),
        Route([[*CHICAGO], [42.5, -95.0], [*DENVER]], 1050.0, 16.0, 1),
    ]
    with patch("routing.views._geocode", side_effect=lambda a: CHICAGO if "Chicago" in a else DENVER), \
         patch("routing.views.get_routes", return_value=routes), \
         patch("routing.views.fetch_forecasts", side_effect=lambda pts, s, e, size: FixedForecasts(size)):
        yield routes


@pytest.mark.django_db
class TestValidation:
    def test_missing_fields(self, client):
        response = client.post("/api/routes/", {}, format="json")
        assert response.status_code == 400
        assert response.data["error"].startswith("Origin:")
        assert set(response.data["fields"]) >= {"origin", "destination", "departure_datetime", "load_weight_lbs"}

    def test_negative_load_weight(self, client):
        response = client.post("/api/routes/", _payload(load_weight_lbs=-500), format="json")
        assert response.status_code == 400
        assert "load_weight_lbs" in response.data["fields"]

    @pytest.mark.parametrize("interval", [5, 30, 100])
    def test_interval_must_be_10_25_or_50(self, client, interval):
        response = client.post("/api/routes/", _payload(interval_miles=interval), format="json")
        assert response.status_code == 400

    def test_departure_in_the_past(self, client):
        response = client.post("/api/routes/", _payload(departure_datetime=_departure(-24)), format="json")
        assert response.status_code == 400
        assert "past" in response.data["error"]

    def test_departure_beyond_forecast_range(self, client):
        response = client.post("/api/routes/", _payload(departure_datetime=_departure(24 * 8)), format="json")
        assert response.status_code == 400

    def test_unknown_place(self, client):
        with patch("routing.views._geocode", side_effect=ValueError("Could not find 'Nowhere'.")):
            response = client.post("/api/routes/", _payload(origin="Nowhere"), format="json")
        assert response.status_code == 400
        assert response.data["error"] == "Could not find 'Nowhere'."


@pytest.mark.django_db
class TestRouteResponse:
    def test_full_response(self, client, mocked_services):
        response = client.post("/api/routes/", _payload(), format="json")
        assert response.status_code == 200
        data = response.data

        assert data["sources"] == {"routing": "openrouteservice", "weather": "open-meteo"}
        assert [r["rank"] for r in data["routes"]] == [1, 2]
        assert sum(r["is_recommended"] for r in data["routes"]) == 1
        assert data["routes"][0]["recommendation_reason"]

        route = data["routes"][0]
        assert route["interval_miles"] == 50.0  # auto for a 1000-mile trip
        assert route["checkpoints"][0]["mile_marker"] == 0.0
        assert route["checkpoints"][-1]["mile_marker"] == route["distance_miles"]
        cp = route["checkpoints"][1]
        assert set(cp) == {"lat", "lng", "mile_marker", "eta", "weather", "risk_level", "risk_score", "risk_reason", "factor_levels"}
        assert set(cp["weather"]) == {"description", "temperature_f", "wind_mph", "rain_in_hr", "snow_in_hr"}

        heatmap = data["heatmap"]
        assert heatmap["hours"] == 48
        assert heatmap["cells"] and all(len(c["values"]) == 49 for c in heatmap["cells"])

    def test_load_weight_changes_risk(self, client, mocked_services):
        """40 mph wind is High for a light load but Severe above 40,000 lb."""
        light = client.post("/api/routes/", _payload(load_weight_lbs=20000), format="json").data
        heavy = client.post("/api/routes/", _payload(load_weight_lbs=45000), format="json").data
        assert light["routes"][0]["risk_summary"]["severe_miles"] == 0
        assert light["routes"][0]["risk_summary"]["high_miles"] > 0
        assert heavy["routes"][0]["risk_summary"]["severe_miles"] > 0
        assert heavy["routes"][0]["risk_summary"]["high_miles"] == 0

    @pytest.mark.parametrize("interval, expected", [(10, 101), (25, 41), (50, 21)])
    def test_requested_interval_controls_sampling(self, client, mocked_services, interval, expected):
        data = client.post("/api/routes/", _payload(interval_miles=interval), format="json").data
        route = next(r for r in data["routes"] if r["distance_miles"] == 1000.0)
        assert route["interval_miles"] == interval
        assert len(route["checkpoints"]) == expected

    def test_checkpoint_etas_follow_travel_time(self, client, mocked_services):
        data = client.post("/api/routes/", _payload(interval_miles=50), format="json").data
        route = next(r for r in data["routes"] if r["distance_miles"] == 1000.0)
        assert route["checkpoints"][-1]["eta"] == route["arrival_time"]

    def test_routing_outage_returns_503_instead_of_fake_routes(self, client):
        with patch("routing.views._geocode", side_effect=lambda a: CHICAGO if "Chicago" in a else DENVER),              patch("routing.views.get_routes", side_effect=RoutingUnavailable("quota is used up")):
            response = client.post("/api/routes/", _payload(), format="json")
        assert response.status_code == 503
        assert response.data == {"error": "quota is used up"}

    def test_weather_outage_returns_503_instead_of_fake_weather(self, client, mocked_services):
        with patch("routing.views.fetch_forecasts", side_effect=WeatherUnavailable("try again in a minute")):
            response = client.post("/api/routes/", _payload(), format="json")
        assert response.status_code == 503
        assert response.data == {"error": "try again in a minute"}

    def test_coordinates_are_accepted_as_places(self, client):
        with patch("routing.views.get_routes", return_value=[Route([[32.7, -96.8], [41.9, -87.6]], 900.0, 14.0)]), \
             patch("routing.views.fetch_forecasts", side_effect=lambda pts, s, e, size: FixedForecasts(size)):
            data = client.post(
                "/api/routes/",
                _payload(origin="32.7, -96.8", destination="41.9,-87.6"),
                format="json",
            ).data
        assert (data["origin"]["lat"], data["origin"]["lng"]) == (32.7, -96.8)
        assert (data["destination"]["lat"], data["destination"]["lng"]) == (41.9, -87.6)
