"""
Tests for the Open-Meteo weather service (mocked HTTP) and the corridor heatmap.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import requests

from routing.services import weather
from routing.services.heatmap import build_heatmap, corridor_cells, corridor_grid
from routing.services.routing import generate_mock_routes
from routing.services.checkpoints import generate_checkpoints
from routing.views import _forecast_grids
from routing.services.weather import (
    SOURCE_LIVE,
    SOURCE_SIMULATED,
    Forecasts,
    WeatherData,
    WeatherUnavailable,
    choose_cell_size,
    fetch_forecasts,
    get_mock_weather,
    grid_cell,
    weather_intensity,
)

START = datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc)


def _hourly(hours=60, **overrides):
    base = {
        "time": [int((START + timedelta(hours=h)).timestamp()) for h in range(hours)],
        "temperature_2m": [50.0] * hours,
        "rain": [0.0] * hours,
        "showers": [0.0] * hours,
        "snowfall": [0.0] * hours,
        "wind_speed_10m": [10.0] * hours,
        "weather_code": [0] * hours,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _fresh_cache(settings):
    # Test the live provider regardless of the developer's local .env
    settings.WEATHER_PROVIDER = "open-meteo"
    weather.clear_cache()
    yield
    weather.clear_cache()


class TestForecastLookup:
    def test_reads_hour_containing_eta(self):
        rain = [0.0] * 60
        rain[3] = 0.3  # total for 10:00–11:00
        f = Forecasts(0.1, {grid_cell(35.0, -97.0, 0.1): _hourly(rain=rain, weather_code=[63] * 60)})
        w = f.weather_at(35.01, -97.02, START + timedelta(hours=2, minutes=20))
        assert w.rain_in_hr == 0.3
        assert w.description == "Rain"
        assert f.source == SOURCE_LIVE

    def test_rain_and_showers_are_summed(self):
        f = Forecasts(0.1, {grid_cell(35.0, -97.0, 0.1): _hourly(rain=[0.1] * 60, showers=[0.2] * 60)})
        assert f.weather_at(35.0, -97.0, START).rain_in_hr == pytest.approx(0.3)

    def test_simulated_mode_is_entirely_simulated(self):
        f = Forecasts(0.1, {}, simulated=True)
        assert f.weather_at(35.0, -97.0, START) == get_mock_weather(35.0, -97.0, START)
        assert f.source == SOURCE_SIMULATED

    def test_missing_cell_is_an_error_not_invented_weather(self):
        with pytest.raises(KeyError):
            Forecasts(0.1, {}).weather_at(35.0, -97.0, START)


class TestFetchForecasts:
    @patch.object(weather, "_request_batch")
    def test_batches_unique_cells_and_caches(self, mock_batch):
        mock_batch.side_effect = lambda cells, s, e: [_hourly() for _ in cells]
        points = [(35.0, -97.0), (35.01, -97.01), (36.0, -97.0)]  # first two share a cell
        f = fetch_forecasts(points, START, START + timedelta(hours=48), 0.1)
        assert mock_batch.call_count == 1
        assert len(mock_batch.call_args[0][0]) == 2
        assert f.weather_at(36.0, -97.0, START).wind_speed == 10.0

        fetch_forecasts(points, START, START + timedelta(hours=48), 0.1)
        assert mock_batch.call_count == 1  # served from cache

        # A departure 2 hours later falls in the same 6-hour cache block
        fetch_forecasts(points, START + timedelta(hours=2), START + timedelta(hours=49), 0.1)
        assert mock_batch.call_count == 1

    @patch.object(weather, "_request_batch", side_effect=ConnectionError("offline"))
    def test_provider_failure_raises(self, _):
        with pytest.raises(WeatherUnavailable, match="unavailable"):
            fetch_forecasts([(35.0, -97.0)], START, START + timedelta(hours=48), 0.1)

    @patch.object(weather, "_request_batch")
    def test_rate_limit_raises_with_neutral_retry_message(self, mock_batch):
        response = requests.Response()
        response.status_code = 429
        mock_batch.side_effect = requests.HTTPError(response=response)
        with pytest.raises(WeatherUnavailable, match="temporarily unavailable. Please try again in a minute"):
            fetch_forecasts([(35.0, -97.0)], START, START + timedelta(hours=48), 0.1)

    @patch.object(weather, "_request_batch")
    def test_partial_failure_raises_instead_of_mixing(self, mock_batch):
        calls = []

        def respond(cells, s, e):
            calls.append(cells)
            if len(calls) == 2:
                raise ConnectionError("dropped")
            return [_hourly() for _ in cells]

        mock_batch.side_effect = respond
        points = [(30 + i * 0.1, -97.0) for i in range(150)]  # 2 batches
        with pytest.raises(WeatherUnavailable):
            fetch_forecasts(points, START, START + timedelta(hours=48), 0.1)

    @patch.object(weather, "_request_batch")
    def test_simulated_provider_setting_skips_network(self, mock_batch, settings):
        settings.WEATHER_PROVIDER = "simulated"
        f = fetch_forecasts([(35.0, -97.0)], START, START + timedelta(hours=48), 0.1)
        f.weather_at(35.0, -97.0, START)
        mock_batch.assert_not_called()
        assert f.source == SOURCE_SIMULATED


class TestLocationBudget:
    def test_picks_finest_grid_within_budget(self):
        counts = {0.1: 900, 0.2: 400, 0.25: 240, 0.5: 80}
        assert choose_cell_size(lambda s: counts.get(s, 10_000), 250) == 0.25

    def test_cross_country_heatmap_fits_budget(self):
        la_to_jacksonville = [[34.05, -118.24], [32.2, -110.9], [31.8, -106.4], [32.8, -96.8],
                              [32.3, -90.2], [30.7, -88.0], [30.3, -81.7]]
        size, cells = corridor_grid([la_to_jacksonville], 250)
        assert len(cells) <= 250
        assert size > 0.1

    def test_short_trip_heatmap_keeps_fine_grid(self):
        size, _ = corridor_grid([[[32.78, -96.8], [30.27, -97.74]]], 250)
        assert size == 0.1


class TestBudgetSplit:
    @staticmethod
    def _trip(origin, destination, interval):
        routes = generate_mock_routes(origin, destination)
        points = [
            (c.lat, c.lng)
            for r in routes
            for c in generate_checkpoints(r.geometry, r.distance_miles, r.travel_time_hours, START, interval)
        ]
        return points, [r.geometry for r in routes]

    @staticmethod
    def _used(points, cp_size, heat_cells):
        return len({grid_cell(a, b, cp_size) for a, b in points}) + len(heat_cells)

    def test_checkpoints_keep_full_resolution_and_heatmap_gets_the_rest(self, settings):
        settings.FORECAST_LOCATION_BUDGET = 250
        points, geometries = self._trip((41.88, -87.63), (39.74, -104.99), 50)  # Chicago -> Denver
        cp_size, heat_size, heat_cells = _forecast_grids(points, geometries)
        assert cp_size == 0.1
        assert self._used(points, cp_size, heat_cells) <= 250

    def test_budget_holds_on_coast_to_coast_trips(self, settings):
        settings.FORECAST_LOCATION_BUDGET = 250
        points, geometries = self._trip((34.05, -118.24), (30.33, -81.66), 10)  # LA -> Jacksonville
        cp_size, _, heat_cells = _forecast_grids(points, geometries)
        assert cp_size > 0.1
        assert len(heat_cells) >= 1
        assert len({grid_cell(a, b, cp_size) for a, b in points}) <= 250

    def test_zero_budget_means_full_resolution(self, settings):
        settings.FORECAST_LOCATION_BUDGET = 0
        points, geometries = self._trip((34.05, -118.24), (30.33, -81.66), 10)
        cp_size, _, _ = _forecast_grids(points, geometries)
        assert cp_size == 0.1


class TestIntensity:
    @pytest.mark.parametrize(
        "wind, rain, snow, expected",
        [
            (0, 0, 0, 0.0),
            (25, 0, 0, 0.2),   # Moderate threshold
            (35, 0, 0, 0.4),   # High
            (45, 0, 0, 0.6),   # Severe
            (55, 0, 0, 0.8),   # No Travel
            (5, 0.25, 0, 0.4),
            (5, 0, 2.0, 0.6),
            (30, 0.6, 0, 0.64),  # worst variable wins (rain 0.6 in/hr)
        ],
    )
    def test_thresholds_align_with_risk_bands(self, wind, rain, snow, expected):
        assert weather_intensity(WeatherData("", 50, wind, rain, snow)) == pytest.approx(expected, abs=0.001)


class TestHeatmap:
    def test_corridor_cells_cover_route_with_neighbours(self):
        cells = corridor_cells([[[35.0, -97.0], [35.0, -96.0]]], 0.1)
        lats = {c[0] for c in cells}
        assert lats == {34.9, 35.0, 35.1}
        assert (35.0, -96.5) in cells

    def test_build_heatmap_has_49_hourly_values_per_cell(self):
        cells = [(35.0, -97.0)]
        wind = [10.0] * 60
        wind[5] = 40.0
        f = Forecasts(0.1, {(35.0, -97.0): _hourly(wind_speed_10m=wind)})
        heatmap = build_heatmap(cells, 0.1, f, START + timedelta(minutes=30))
        assert heatmap["start_time"] == START.isoformat()
        assert heatmap["hours"] == 48
        values = heatmap["cells"][0]["values"]
        assert len(values) == 49
        assert values[5] == pytest.approx(0.5)
        assert values[0] == pytest.approx(0.08)
