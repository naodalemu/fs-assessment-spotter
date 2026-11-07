"""
Tests for the risk calculator service.

Tests all boundary values for wind, rain, snow thresholds,
load modifier rules, and that the worst condition wins.
"""

import pytest

from routing.services.risk import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MODERATE,
    RISK_NO_TRAVEL,
    RISK_SEVERE,
    calculate_risk,
)
from routing.services.weather import WeatherData


def _make_weather(
    wind_speed=0.0, rain_in_hr=0.0, snow_in_hr=0.0
) -> WeatherData:
    """Helper to create WeatherData with default safe values."""
    return WeatherData(
        description="Test",
        temperature=70.0,
        wind_speed=wind_speed,
        rain_in_hr=rain_in_hr,
        snow_in_hr=snow_in_hr,
    )


# ──────────────────────────── Wind Thresholds ────────────────────────────


class TestWindRisk:
    """Test wind speed thresholds."""

    def test_wind_low_zero(self):
        result = calculate_risk(_make_weather(wind_speed=0), 10000)
        assert result.risk_level == RISK_LOW
        assert result.risk_score == 1

    def test_wind_low_24(self):
        result = calculate_risk(_make_weather(wind_speed=24.9), 10000)
        assert result.risk_level == RISK_LOW

    def test_wind_moderate_25(self):
        result = calculate_risk(_make_weather(wind_speed=25.0), 10000)
        assert result.risk_level == RISK_MODERATE

    def test_wind_moderate_34(self):
        result = calculate_risk(_make_weather(wind_speed=34.9), 10000)
        assert result.risk_level == RISK_MODERATE

    def test_wind_high_35(self):
        result = calculate_risk(_make_weather(wind_speed=35.0), 10000)
        assert result.risk_level == RISK_HIGH

    def test_wind_high_44(self):
        result = calculate_risk(_make_weather(wind_speed=44.9), 10000)
        assert result.risk_level == RISK_HIGH

    def test_wind_severe_45(self):
        result = calculate_risk(_make_weather(wind_speed=45.0), 10000)
        assert result.risk_level == RISK_SEVERE

    def test_wind_severe_54(self):
        result = calculate_risk(_make_weather(wind_speed=54.9), 10000)
        assert result.risk_level == RISK_SEVERE

    def test_wind_no_travel_55(self):
        result = calculate_risk(_make_weather(wind_speed=55.0), 10000)
        assert result.risk_level == RISK_NO_TRAVEL
        assert result.risk_score == 5

    def test_wind_no_travel_high(self):
        result = calculate_risk(_make_weather(wind_speed=70.0), 10000)
        assert result.risk_level == RISK_NO_TRAVEL


# ──────────────────────────── Rain Thresholds ────────────────────────────


class TestRainRisk:
    """Test rain intensity thresholds."""

    def test_rain_low_zero(self):
        result = calculate_risk(_make_weather(rain_in_hr=0.0), 10000)
        assert result.risk_level == RISK_LOW

    def test_rain_low_below_threshold(self):
        result = calculate_risk(_make_weather(rain_in_hr=0.09), 10000)
        assert result.risk_level == RISK_LOW

    def test_rain_moderate_010(self):
        result = calculate_risk(_make_weather(rain_in_hr=0.10), 10000)
        assert result.risk_level == RISK_MODERATE

    def test_rain_moderate_024(self):
        result = calculate_risk(_make_weather(rain_in_hr=0.24), 10000)
        assert result.risk_level == RISK_MODERATE

    def test_rain_high_025(self):
        result = calculate_risk(_make_weather(rain_in_hr=0.25), 10000)
        assert result.risk_level == RISK_HIGH

    def test_rain_high_049(self):
        result = calculate_risk(_make_weather(rain_in_hr=0.49), 10000)
        assert result.risk_level == RISK_HIGH

    def test_rain_severe_050(self):
        result = calculate_risk(_make_weather(rain_in_hr=0.50), 10000)
        assert result.risk_level == RISK_SEVERE

    def test_rain_severe_100(self):
        result = calculate_risk(_make_weather(rain_in_hr=1.00), 10000)
        assert result.risk_level == RISK_SEVERE

    def test_rain_no_travel_above_100(self):
        result = calculate_risk(_make_weather(rain_in_hr=1.01), 10000)
        assert result.risk_level == RISK_NO_TRAVEL

    def test_rain_no_travel_heavy(self):
        result = calculate_risk(_make_weather(rain_in_hr=2.5), 10000)
        assert result.risk_level == RISK_NO_TRAVEL


# ──────────────────────────── Snow Thresholds ────────────────────────────


class TestSnowRisk:
    """Test snow intensity thresholds."""

    def test_snow_low_zero(self):
        result = calculate_risk(_make_weather(snow_in_hr=0.0), 10000)
        assert result.risk_level == RISK_LOW

    def test_snow_low_below_threshold(self):
        result = calculate_risk(_make_weather(snow_in_hr=0.49), 10000)
        assert result.risk_level == RISK_LOW

    def test_snow_moderate_05(self):
        result = calculate_risk(_make_weather(snow_in_hr=0.5), 10000)
        assert result.risk_level == RISK_MODERATE

    def test_snow_moderate_09(self):
        result = calculate_risk(_make_weather(snow_in_hr=0.99), 10000)
        assert result.risk_level == RISK_MODERATE

    def test_snow_high_10(self):
        result = calculate_risk(_make_weather(snow_in_hr=1.0), 10000)
        assert result.risk_level == RISK_HIGH

    def test_snow_high_19(self):
        result = calculate_risk(_make_weather(snow_in_hr=1.9), 10000)
        assert result.risk_level == RISK_HIGH

    def test_snow_severe_20(self):
        result = calculate_risk(_make_weather(snow_in_hr=2.0), 10000)
        assert result.risk_level == RISK_SEVERE

    def test_snow_severe_30(self):
        result = calculate_risk(_make_weather(snow_in_hr=3.0), 10000)
        assert result.risk_level == RISK_SEVERE

    def test_snow_no_travel_above_30(self):
        result = calculate_risk(_make_weather(snow_in_hr=3.01), 10000)
        assert result.risk_level == RISK_NO_TRAVEL


# ────────────────────── Load Modifier Rules ──────────────────────────────


class TestLoadModifiers:
    """Test load weight modifier rules."""

    def test_wind_45_54_light_load_stays_severe(self):
        """45-54 mph wind with ≤30,000 lb load stays Severe."""
        result = calculate_risk(_make_weather(wind_speed=50.0), 30000)
        assert result.risk_level == RISK_SEVERE

    def test_wind_45_54_heavy_load_becomes_no_travel(self):
        """45-54 mph wind with >30,000 lb load → No Travel."""
        result = calculate_risk(_make_weather(wind_speed=50.0), 30001)
        assert result.risk_level == RISK_NO_TRAVEL
        assert result.risk_score == 5

    def test_wind_45_exact_heavy_load(self):
        """45 mph wind with >30,000 lb → No Travel."""
        result = calculate_risk(_make_weather(wind_speed=45.0), 35000)
        assert result.risk_level == RISK_NO_TRAVEL

    def test_wind_54_heavy_load(self):
        """54.9 mph wind with >30,000 lb → No Travel."""
        result = calculate_risk(_make_weather(wind_speed=54.9), 40000)
        assert result.risk_level == RISK_NO_TRAVEL

    def test_wind_35_44_light_load_stays_high(self):
        """35-44 mph wind with ≤40,000 lb stays High."""
        result = calculate_risk(_make_weather(wind_speed=40.0), 40000)
        assert result.risk_level == RISK_HIGH

    def test_wind_35_44_heavy_load_becomes_severe(self):
        """35-44 mph wind with >40,000 lb → Severe."""
        result = calculate_risk(_make_weather(wind_speed=40.0), 40001)
        assert result.risk_level == RISK_SEVERE
        assert result.risk_score == 4

    def test_wind_35_exact_heavy_load(self):
        """35 mph wind with >40,000 lb → Severe."""
        result = calculate_risk(_make_weather(wind_speed=35.0), 45000)
        assert result.risk_level == RISK_SEVERE

    def test_wind_44_heavy_load(self):
        """44.9 mph wind with >40,000 lb → Severe."""
        result = calculate_risk(_make_weather(wind_speed=44.9), 50000)
        assert result.risk_level == RISK_SEVERE

    def test_wind_55_any_load_no_travel(self):
        """≥55 mph wind → No Travel regardless of load (from wind threshold)."""
        result = calculate_risk(_make_weather(wind_speed=55.0), 10000)
        assert result.risk_level == RISK_NO_TRAVEL

    def test_wind_55_heavy_load_no_travel(self):
        """≥55 mph wind → No Travel even with heavy load."""
        result = calculate_risk(_make_weather(wind_speed=60.0), 50000)
        assert result.risk_level == RISK_NO_TRAVEL


# ────────────────────── Worst Condition Wins ─────────────────────────────


class TestWorstConditionWins:
    """Test that the worst (highest) risk across all conditions wins."""

    def test_rain_worse_than_wind(self):
        """Heavy rain should dominate over light wind."""
        weather = _make_weather(wind_speed=10.0, rain_in_hr=1.5)
        result = calculate_risk(weather, 10000)
        assert result.risk_level == RISK_NO_TRAVEL

    def test_snow_worse_than_rain(self):
        """Heavy snow should dominate over moderate rain."""
        weather = _make_weather(rain_in_hr=0.15, snow_in_hr=2.5)
        result = calculate_risk(weather, 10000)
        assert result.risk_level == RISK_SEVERE

    def test_wind_worse_than_others(self):
        """Strong wind should dominate when it's the worst."""
        weather = _make_weather(wind_speed=50.0, rain_in_hr=0.05, snow_in_hr=0.1)
        result = calculate_risk(weather, 10000)
        assert result.risk_level == RISK_SEVERE

    def test_all_conditions_low(self):
        """When all conditions are low, result is low."""
        weather = _make_weather(wind_speed=5.0, rain_in_hr=0.01, snow_in_hr=0.0)
        result = calculate_risk(weather, 10000)
        assert result.risk_level == RISK_LOW

    def test_multiple_severe_still_severe(self):
        """Multiple severe conditions still result in severe (not higher)."""
        weather = _make_weather(wind_speed=50.0, rain_in_hr=0.60, snow_in_hr=2.5)
        result = calculate_risk(weather, 10000)
        assert result.risk_level == RISK_SEVERE

    def test_combined_with_load_modifier(self):
        """Load modifier can push above worst weather risk."""
        # Wind is 40 mph (High), Rain is 0.3 (High), load is 45000
        # Load modifier: 35-44 mph + >40000 → Severe
        weather = _make_weather(wind_speed=40.0, rain_in_hr=0.3)
        result = calculate_risk(weather, 45000)
        assert result.risk_level == RISK_SEVERE


# ────────────────────── Exact Boundary Compliance ─────────────────────────


class TestExactBoundaryCompliance:
    """Comprehensive boundary tests to guarantee strict spec conformance."""

    @pytest.mark.parametrize(
        "wind_speed,expected_level,expected_score",
        [
            (0.0, RISK_LOW, 1),
            (24.99, RISK_LOW, 1),
            (25.0, RISK_MODERATE, 2),
            (34.99, RISK_MODERATE, 2),
            (35.0, RISK_HIGH, 3),
            (44.99, RISK_HIGH, 3),
            (45.0, RISK_SEVERE, 4),
            (54.99, RISK_SEVERE, 4),
            (55.0, RISK_NO_TRAVEL, 5),
            (55.01, RISK_NO_TRAVEL, 5),
            (100.0, RISK_NO_TRAVEL, 5),
        ],
    )
    def test_wind_boundaries(self, wind_speed, expected_level, expected_score):
        res = calculate_risk(_make_weather(wind_speed=wind_speed), load_weight_lbs=10000)
        assert res.risk_level == expected_level
        assert res.risk_score == expected_score

    @pytest.mark.parametrize(
        "rain_in_hr,expected_level,expected_score",
        [
            (0.0, RISK_LOW, 1),
            (0.099, RISK_LOW, 1),
            (0.10, RISK_MODERATE, 2),
            (0.249, RISK_MODERATE, 2),
            (0.25, RISK_HIGH, 3),
            (0.499, RISK_HIGH, 3),
            (0.50, RISK_SEVERE, 4),
            (1.00, RISK_SEVERE, 4),
            (1.001, RISK_NO_TRAVEL, 5),
            (2.5, RISK_NO_TRAVEL, 5),
        ],
    )
    def test_rain_boundaries(self, rain_in_hr, expected_level, expected_score):
        res = calculate_risk(_make_weather(rain_in_hr=rain_in_hr), load_weight_lbs=10000)
        assert res.risk_level == expected_level
        assert res.risk_score == expected_score

    @pytest.mark.parametrize(
        "snow_in_hr,expected_level,expected_score",
        [
            (0.0, RISK_LOW, 1),
            (0.499, RISK_LOW, 1),
            (0.50, RISK_MODERATE, 2),
            (0.999, RISK_MODERATE, 2),
            (1.0, RISK_HIGH, 3),
            (1.999, RISK_HIGH, 3),
            (2.0, RISK_SEVERE, 4),
            (3.0, RISK_SEVERE, 4),
            (3.001, RISK_NO_TRAVEL, 5),
            (5.0, RISK_NO_TRAVEL, 5),
        ],
    )
    def test_snow_boundaries(self, snow_in_hr, expected_level, expected_score):
        res = calculate_risk(_make_weather(snow_in_hr=snow_in_hr), load_weight_lbs=10000)
        assert res.risk_level == expected_level
        assert res.risk_score == expected_score

    @pytest.mark.parametrize(
        "wind_speed,load_weight,expected_level",
        [
            # >= 55 mph wind -> No Travel for any load
            (55.0, 0, RISK_NO_TRAVEL),
            (55.0, 10000, RISK_NO_TRAVEL),
            (55.0, 30000, RISK_NO_TRAVEL),
            (55.0, 80000, RISK_NO_TRAVEL),
            (60.0, 0, RISK_NO_TRAVEL),
            # 45–54 mph wind + > 30,000 lb -> No Travel; <= 30,000 lb -> Severe
            (45.0, 30000, RISK_SEVERE),
            (45.0, 30001, RISK_NO_TRAVEL),
            (50.0, 30000, RISK_SEVERE),
            (50.0, 30001, RISK_NO_TRAVEL),
            (54.99, 30000, RISK_SEVERE),
            (54.99, 30001, RISK_NO_TRAVEL),
            # 35–44 mph wind + > 40,000 lb -> Severe; <= 40,000 lb -> High
            (35.0, 40000, RISK_HIGH),
            (35.0, 40001, RISK_SEVERE),
            (40.0, 40000, RISK_HIGH),
            (40.0, 40001, RISK_SEVERE),
            (44.99, 40000, RISK_HIGH),
            (44.99, 40001, RISK_SEVERE),
            # Sub-threshold wind should not trigger load upgrade
            (34.99, 50000, RISK_MODERATE),
            (24.99, 80000, RISK_LOW),
        ],
    )
    def test_load_weight_boundaries(self, wind_speed, load_weight, expected_level):
        res = calculate_risk(_make_weather(wind_speed=wind_speed), load_weight_lbs=load_weight)
        assert res.risk_level == expected_level



class TestRiskReason:
    def test_low(self):
        assert calculate_risk(WeatherData("Clear", 60, 10, 0, 0), 20000).reason == (
            "All conditions below Moderate thresholds"
        )

    def test_weather_driver(self):
        assert calculate_risk(WeatherData("Rain", 60, 10, 0.3, 0), 20000).reason == "Rain 0.30 in/hr"

    def test_multiple_drivers(self):
        r = calculate_risk(WeatherData("Storm", 60, 38, 0.3, 0), 20000)
        assert r.risk_level == "High"
        assert r.reason == "Wind 38 mph and rain 0.30 in/hr"

    def test_factor_levels_ignore_load_rules(self):
        r = calculate_risk(WeatherData("Windy", 60, 38, 0.12, 0), 45000)
        assert r.factor_levels == {"wind": "High", "rain": "Moderate", "snow": "Low"}

    def test_load_rule_driver(self):
        r = calculate_risk(WeatherData("Windy", 60, 38, 0, 0), 45000)
        assert r.risk_level == "Severe"
        assert r.reason == "Wind 38 mph with load over 40,000 lb"
