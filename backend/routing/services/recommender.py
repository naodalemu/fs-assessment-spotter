"""
Route recommender — aggregates checkpoint risk into per-route mileage and
ranks routes.
"""

from dataclasses import dataclass

from .risk import RISK_HIGH, RISK_LOW, RISK_MODERATE, RISK_NO_TRAVEL, RISK_SEVERE

_MILES_FIELD = {
    RISK_LOW: "low_miles",
    RISK_MODERATE: "moderate_miles",
    RISK_HIGH: "high_miles",
    RISK_SEVERE: "severe_miles",
    RISK_NO_TRAVEL: "no_travel_miles",
}


@dataclass
class RiskSummary:
    """Aggregated risk statistics for a route."""

    low_miles: float = 0.0
    moderate_miles: float = 0.0
    high_miles: float = 0.0
    severe_miles: float = 0.0
    no_travel_miles: float = 0.0
    average_risk_score: float = 0.0
    max_risk_score: int = 0


def compute_risk_summary(checkpoints: list[dict], total_distance_miles: float) -> RiskSummary:
    """
    Attribute route mileage to risk levels.

    Each checkpoint represents the stretch of road closest to it: from the
    midpoint with the previous checkpoint to the midpoint with the next one
    (the first starts at mile 0, the last ends at the destination). The
    average risk score is weighted by those miles.
    """
    summary = RiskSummary()
    if not checkpoints:
        return summary

    markers = [cp["mile_marker"] for cp in checkpoints]
    weighted_score = 0.0
    scored_miles = 0.0

    for i, cp in enumerate(checkpoints):
        start = 0.0 if i == 0 else (markers[i - 1] + markers[i]) / 2
        end = total_distance_miles if i == len(checkpoints) - 1 else (markers[i] + markers[i + 1]) / 2
        miles = max(0.0, end - start)

        field = _MILES_FIELD.get(cp["risk_level"])
        if field:
            setattr(summary, field, getattr(summary, field) + miles)
        weighted_score += cp["risk_score"] * miles
        scored_miles += miles
        summary.max_risk_score = max(summary.max_risk_score, cp["risk_score"])

    for field in _MILES_FIELD.values():
        setattr(summary, field, round(getattr(summary, field), 1))
    summary.average_risk_score = round(weighted_score / scored_miles, 2) if scored_miles else 0.0
    return summary


def _ranking_key(route: dict) -> tuple:
    """
    Lower is better:
      1. fewest No Travel miles (stricter than Severe — the road is not drivable)
      2. fewest Severe miles
      3. fewest High miles
      4. lowest mile-weighted average risk
      5. shortest travel time
    """
    rs = route["risk_summary"]
    return (
        rs["no_travel_miles"],
        rs["severe_miles"],
        rs["high_miles"],
        rs["average_risk_score"],
        route["travel_time_hours"],
    )


_CRITERIA = [
    ("no_travel_miles", "Fewer No Travel miles than {other} ({b:.0f} vs {o:.0f})"),
    ("severe_miles", "Fewer Severe miles than {other} ({b:.0f} vs {o:.0f})"),
    ("high_miles", "Fewer High-risk miles than {other} ({b:.0f} vs {o:.0f})"),
    ("average_risk_score", "Lower overall risk than {other}"),
]


def _recommendation_reason(best: dict, runner_up: dict | None) -> str:
    no_travel = best["risk_summary"]["no_travel_miles"]
    if no_travel > 0:
        # "No Travel" means the truck should not drive there at that time, so the
        # least-bad route is still not a safe plan.
        return f"Every route crosses No Travel conditions ({no_travel:.0f} mi here). Try a later departure."
    if runner_up is None:
        return "Only route found."
    for field, template in _CRITERIA:
        b, o = best["risk_summary"][field], runner_up["risk_summary"][field]
        if b < o:
            return template.format(b=b, o=o, other=runner_up["name"])
    if best["travel_time_hours"] < runner_up["travel_time_hours"]:
        return "Same risk, fastest route."
    return "Same risk and travel time."


def recommend_routes(routes: list[dict]) -> list[dict]:
    """
    Sort routes best-first, mark the first as recommended, and explain why it
    beat the runner-up. Routes keep their names (Route 1–3 in fastest-first
    order) so the map and the list refer to the same route.
    """
    ranked = sorted(routes, key=_ranking_key)
    for rank, route in enumerate(ranked):
        route["rank"] = rank + 1
        route["is_recommended"] = rank == 0
        route["recommendation_reason"] = None
    if ranked:
        ranked[0]["recommendation_reason"] = _recommendation_reason(
            ranked[0], ranked[1] if len(ranked) > 1 else None
        )
    return ranked
