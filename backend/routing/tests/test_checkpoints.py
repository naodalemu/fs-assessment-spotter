"""
Tests for checkpoint sampling and ETA calculation.
"""

from datetime import datetime, timezone

import pytest

from routing.services.checkpoints import (
    _haversine,
    generate_checkpoints,
    get_adaptive_interval,
    polyline_length_miles,
)

NOW = datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc)
# ~100 miles due north (1° latitude ≈ 69 mi)
STRAIGHT_100 = [[40.0, -80.0], [41.4473, -80.0]]


class TestHaversine:
    def test_same_point(self):
        assert _haversine(40.0, -74.0, 40.0, -74.0) == 0.0

    def test_approximate_known_distance(self):
        # NYC to Philadelphia ~ 80 miles
        assert 75 <= _haversine(40.7128, -74.0060, 39.9526, -75.1652) <= 85


class TestAdaptiveInterval:
    @pytest.mark.parametrize("miles, expected", [(50, 10), (200, 10), (201, 25), (600, 25), (601, 50), (2500, 50)])
    def test_interval_by_trip_length(self, miles, expected):
        assert get_adaptive_interval(miles) == expected


class TestGenerateCheckpoints:
    def test_empty_or_single_point(self):
        assert generate_checkpoints([], 100.0, 2.0, NOW) == []
        assert generate_checkpoints([[40.0, -74.0]], 100.0, 2.0, NOW) == []

    def test_spacing_and_etas(self):
        cps = generate_checkpoints(STRAIGHT_100, 100.0, 2.0, NOW, interval_miles=25.0)
        assert [cp.mile_marker for cp in cps] == [0.0, 25.0, 50.0, 75.0, 100.0]
        assert cps[0].eta == NOW
        assert (cps[1].eta - NOW).total_seconds() == pytest.approx(1800, rel=0.001)
        assert (cps[-1].eta - NOW).total_seconds() == pytest.approx(7200, rel=0.001)

    @pytest.mark.parametrize("interval, count", [(10.0, 11), (25.0, 5), (50.0, 3)])
    def test_interval_controls_count(self, interval, count):
        assert len(generate_checkpoints(STRAIGHT_100, 100.0, 2.0, NOW, interval)) == count

    def test_last_checkpoint_is_destination(self):
        cps = generate_checkpoints(STRAIGHT_100, 103.0, 2.0, NOW, interval_miles=50.0)
        assert cps[-1].mile_marker == 103.0
        assert [cps[-1].lat, cps[-1].lng] == STRAIGHT_100[-1]
        # The 100-mile sample was too close to the destination and was replaced
        assert [cp.mile_marker for cp in cps] == [0.0, 50.0, 103.0]

    def test_mile_markers_scaled_to_road_distance(self):
        """Road distance (130 mi) > polyline length (~100 mi): samples spread over the whole line."""
        cps = generate_checkpoints(STRAIGHT_100, 130.0, 2.6, NOW, interval_miles=65.0)
        mid = cps[1]
        assert mid.mile_marker == 65.0
        # Half the road distance should be half way along the polyline
        assert mid.lat == pytest.approx((STRAIGHT_100[0][0] + STRAIGHT_100[1][0]) / 2, abs=0.01)

    def test_polyline_length(self):
        assert polyline_length_miles(STRAIGHT_100) == pytest.approx(100.0, abs=0.5)
