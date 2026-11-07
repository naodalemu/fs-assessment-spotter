"""
Tests for route recommender and risk summary calculation.
"""

import pytest

from routing.services.recommender import compute_risk_summary, recommend_routes
from routing.services.risk import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MODERATE,
    RISK_NO_TRAVEL,
    RISK_SEVERE,
)


class TestComputeRiskSummary:
    def test_empty_checkpoints(self):
        summary = compute_risk_summary([], 100.0)
        assert summary.low_miles == 0.0
        assert summary.average_risk_score == 0.0

    def test_single_risk_level(self):
        checkpoints = [
            {"mile_marker": 0.0, "risk_level": RISK_LOW, "risk_score": 1},
            {"mile_marker": 50.0, "risk_level": RISK_LOW, "risk_score": 1},
            {"mile_marker": 100.0, "risk_level": RISK_LOW, "risk_score": 1},
        ]
        summary = compute_risk_summary(checkpoints, 100.0)
        assert summary.low_miles == 100.0
        assert summary.average_risk_score == 1.0
        assert summary.max_risk_score == 1

    def test_each_checkpoint_covers_road_up_to_midpoints(self):
        checkpoints = [
            {"mile_marker": 0.0, "risk_level": RISK_LOW, "risk_score": 1},       # 0–25
            {"mile_marker": 50.0, "risk_level": RISK_MODERATE, "risk_score": 2},  # 25–65
            {"mile_marker": 80.0, "risk_level": RISK_HIGH, "risk_score": 3},      # 65–90
            {"mile_marker": 100.0, "risk_level": RISK_SEVERE, "risk_score": 4},   # 90–100
        ]
        summary = compute_risk_summary(checkpoints, 100.0)
        assert summary.low_miles == 25.0
        assert summary.moderate_miles == 40.0
        assert summary.high_miles == 25.0
        assert summary.severe_miles == 10.0
        # (25*1 + 40*2 + 25*3 + 10*4) / 100
        assert summary.average_risk_score == 2.2
        assert summary.max_risk_score == 4

    def test_mileage_sums_to_route_distance(self):
        checkpoints = [
            {"mile_marker": m, "risk_level": RISK_NO_TRAVEL if m == 75 else RISK_LOW,
             "risk_score": 5 if m == 75 else 1}
            for m in (0.0, 25.0, 50.0, 75.0, 100.0, 113.4)
        ]
        s = compute_risk_summary(checkpoints, 113.4)
        total = s.low_miles + s.moderate_miles + s.high_miles + s.severe_miles + s.no_travel_miles
        assert total == pytest.approx(113.4, abs=0.1)
        assert s.no_travel_miles == 25.0


class TestRecommendRoutes:
    def test_prefers_fewest_severe_and_no_travel_miles(self):
        r1 = {
            "name": "Route 1",
            "travel_time_hours": 10.0,
            "risk_summary": {
                "severe_miles": 10.0,
                "no_travel_miles": 0.0,
                "high_miles": 0.0,
                "average_risk_score": 2.0,
            },
        }
        r2 = {
            "name": "Route 2",
            "travel_time_hours": 12.0,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 0.0,
                "high_miles": 20.0,
                "average_risk_score": 2.5,
            },
        }
        ranked = recommend_routes([r1, r2])
        # r2 has 0 severe miles vs r1's 10 severe miles
        assert ranked[0]["name"] == "Route 2"
        assert ranked[0]["is_recommended"] is True
        assert ranked[1]["is_recommended"] is False

    def test_tiebreak_fewest_high_miles(self):
        r1 = {
            "name": "Route 1",
            "travel_time_hours": 10.0,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 0.0,
                "high_miles": 15.0,
                "average_risk_score": 2.0,
            },
        }
        r2 = {
            "name": "Route 2",
            "travel_time_hours": 10.0,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 0.0,
                "high_miles": 5.0,
                "average_risk_score": 2.0,
            },
        }
        ranked = recommend_routes([r1, r2])
        assert ranked[0]["name"] == "Route 2"

    def test_tiebreak_lowest_avg_risk(self):
        r1 = {
            "name": "Route 1",
            "travel_time_hours": 10.0,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 0.0,
                "high_miles": 5.0,
                "average_risk_score": 2.2,
            },
        }
        r2 = {
            "name": "Route 2",
            "travel_time_hours": 10.0,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 0.0,
                "high_miles": 5.0,
                "average_risk_score": 1.8,
            },
        }
        ranked = recommend_routes([r1, r2])
        assert ranked[0]["name"] == "Route 2"

    def test_tiebreak_shortest_travel_time(self):
        r1 = {
            "name": "Route 1",
            "travel_time_hours": 12.0,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 0.0,
                "high_miles": 5.0,
                "average_risk_score": 2.0,
            },
        }
        r2 = {
            "name": "Route 2",
            "travel_time_hours": 9.5,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 0.0,
                "high_miles": 5.0,
                "average_risk_score": 2.0,
            },
        }
        ranked = recommend_routes([r1, r2])
        assert ranked[0]["name"] == "Route 2"

    def test_four_step_hierarchy_complete(self):
        """
        Verify the ranking hierarchy:
        1. Fewest No Travel, then Severe miles
        2. Fewest High miles
        3. Lowest average risk score
        4. Shortest travel time
        """
        # Worst: has severe miles
        r_severe = {
            "name": "R_Severe",
            "travel_time_hours": 4.0,
            "risk_summary": {
                "severe_miles": 5.0,
                "no_travel_miles": 0.0,
                "high_miles": 0.0,
                "average_risk_score": 1.2,
            },
        }
        # Next worst: 0 severe, but high miles = 20
        r_high = {
            "name": "R_High",
            "travel_time_hours": 5.0,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 0.0,
                "high_miles": 20.0,
                "average_risk_score": 1.5,
            },
        }
        # Next: 0 severe, 5 high miles, but higher avg risk
        r_avg = {
            "name": "R_AvgRisk",
            "travel_time_hours": 6.0,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 0.0,
                "high_miles": 5.0,
                "average_risk_score": 2.8,
            },
        }
        # Next: 0 severe, 5 high miles, lower avg risk, longer time
        r_slow = {
            "name": "R_Slow",
            "travel_time_hours": 10.0,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 0.0,
                "high_miles": 5.0,
                "average_risk_score": 2.1,
            },
        }
        # Best: 0 severe, 5 high miles, lower avg risk, shorter time
        r_best = {
            "name": "R_Best",
            "travel_time_hours": 7.5,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 0.0,
                "high_miles": 5.0,
                "average_risk_score": 2.1,
            },
        }

        routes = [r_severe, r_high, r_avg, r_slow, r_best]
        ranked = recommend_routes(routes)

        assert [r["name"] for r in ranked] == [
            "R_Best",
            "R_Slow",
            "R_AvgRisk",
            "R_High",
            "R_Severe",
        ]
        assert ranked[0]["is_recommended"] is True
        assert all(not r["is_recommended"] for r in ranked[1:])

    def test_no_travel_beats_any_amount_of_severe(self):
        """No Travel (road not drivable) is stricter than Severe."""
        r_no_travel = {
            "name": "R_NoTravel",
            "travel_time_hours": 5.0,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 5.0,
                "high_miles": 0.0,
                "average_risk_score": 1.1,
            },
        }
        r_severe = {
            "name": "R_Severe",
            "travel_time_hours": 6.0,
            "risk_summary": {
                "severe_miles": 80.0,
                "no_travel_miles": 0.0,
                "high_miles": 0.0,
                "average_risk_score": 2.0,
            },
        }
        ranked = recommend_routes([r_no_travel, r_severe])
        assert ranked[0]["name"] == "R_Severe"

    def test_reason_explains_deciding_criterion(self):
        safe = {"name": "Route 2", "travel_time_hours": 9.0, "risk_summary": {
            "severe_miles": 0.0, "no_travel_miles": 0.0, "high_miles": 12.0, "average_risk_score": 1.4}}
        risky = {"name": "Route 1", "travel_time_hours": 8.0, "risk_summary": {
            "severe_miles": 30.0, "no_travel_miles": 0.0, "high_miles": 0.0, "average_risk_score": 1.6}}
        ranked = recommend_routes([risky, safe])
        assert ranked[0]["recommendation_reason"] == "Fewer Severe miles than Route 1 (0 vs 30)"
        assert ranked[1]["recommendation_reason"] is None
        assert [r["rank"] for r in ranked] == [1, 2]

    def test_reason_warns_when_best_route_has_no_travel_miles(self):
        ranked = recommend_routes([
            {"name": "Route 1", "travel_time_hours": 8.0, "risk_summary": {
                "severe_miles": 0.0, "no_travel_miles": 40.0, "high_miles": 0.0, "average_risk_score": 1.5}},
            {"name": "Route 2", "travel_time_hours": 9.0, "risk_summary": {
                "severe_miles": 0.0, "no_travel_miles": 15.0, "high_miles": 0.0, "average_risk_score": 1.5}},
        ])
        assert ranked[0]["name"] == "Route 2"
        assert ranked[0]["recommendation_reason"] == (
            "Every route crosses No Travel conditions (15 mi here). Try a later departure."
        )

    def test_reason_falls_back_to_travel_time(self):
        rs = {"severe_miles": 0.0, "no_travel_miles": 0.0, "high_miles": 0.0, "average_risk_score": 1.0}
        ranked = recommend_routes([
            {"name": "Route 2", "travel_time_hours": 11.0, "risk_summary": dict(rs)},
            {"name": "Route 1", "travel_time_hours": 10.0, "risk_summary": dict(rs)},
        ])
        assert ranked[0]["name"] == "Route 1"
        assert ranked[0]["recommendation_reason"] == "Same risk, fastest route."

    def test_no_travel_ranked_before_clean_route(self):
        """A route with any No Travel miles loses to a route without."""
        r_no_travel = {
            "name": "R_NoTravel",
            "travel_time_hours": 5.0,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 2.0,
                "high_miles": 0.0,
                "average_risk_score": 1.5,
            },
        }
        r_clean = {
            "name": "R_Clean",
            "travel_time_hours": 8.0,
            "risk_summary": {
                "severe_miles": 0.0,
                "no_travel_miles": 0.0,
                "high_miles": 10.0,
                "average_risk_score": 2.5,
            },
        }
        ranked = recommend_routes([r_no_travel, r_clean])
        assert ranked[0]["name"] == "R_Clean"

