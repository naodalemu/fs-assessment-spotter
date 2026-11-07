"""
Risk calculator — evaluates weather risk at each checkpoint
based on wind, rain, snow thresholds and load weight modifiers.
"""

from dataclasses import dataclass

from .weather import WeatherData


# Risk level constants
RISK_LOW = "Low"
RISK_MODERATE = "Moderate"
RISK_HIGH = "High"
RISK_SEVERE = "Severe"
RISK_NO_TRAVEL = "No Travel"

# Numeric risk scores
RISK_SCORES = {
    RISK_LOW: 1,
    RISK_MODERATE: 2,
    RISK_HIGH: 3,
    RISK_SEVERE: 4,
    RISK_NO_TRAVEL: 5,
}


@dataclass
class RiskAssessment:
    """Risk assessment for a single checkpoint."""

    risk_level: str
    risk_score: int
    reason: str = ""
    # Level of each weather factor on its own, before load rules
    factor_levels: dict | None = None


def _wind_risk(wind_speed: float) -> str:
    """
    Determine risk level from wind speed (mph).

    | Condition | Low    | Moderate | High   | Severe  | No Travel |
    |-----------|--------|----------|--------|---------|-----------|
    | Wind      | <25    | 25–34    | 35–44  | 45–54   | ≥55       |
    """
    if wind_speed >= 55:
        return RISK_NO_TRAVEL
    elif wind_speed >= 45:
        return RISK_SEVERE
    elif wind_speed >= 35:
        return RISK_HIGH
    elif wind_speed >= 25:
        return RISK_MODERATE
    else:
        return RISK_LOW


def _rain_risk(rain_in_hr: float) -> str:
    """
    Determine risk level from rain intensity (inches/hr).

    | Condition | Low    | Moderate  | High      | Severe     | No Travel |
    |-----------|--------|-----------|-----------|------------|-----------|
    | Rain      | <0.10  | 0.10–0.25 | 0.25–0.50 | 0.50–1.00  | >1.00     |
    """
    if rain_in_hr > 1.00:
        return RISK_NO_TRAVEL
    elif rain_in_hr >= 0.50:
        return RISK_SEVERE
    elif rain_in_hr >= 0.25:
        return RISK_HIGH
    elif rain_in_hr >= 0.10:
        return RISK_MODERATE
    else:
        return RISK_LOW


def _snow_risk(snow_in_hr: float) -> str:
    """
    Determine risk level from snow intensity (inches/hr).

    | Condition | Low  | Moderate | High   | Severe  | No Travel |
    |-----------|------|----------|--------|---------|-----------|
    | Snow      | <0.5 | 0.5–1.0  | 1.0–2.0| 2.0–3.0 | >3.0      |
    """
    if snow_in_hr > 3.0:
        return RISK_NO_TRAVEL
    elif snow_in_hr >= 2.0:
        return RISK_SEVERE
    elif snow_in_hr >= 1.0:
        return RISK_HIGH
    elif snow_in_hr >= 0.5:
        return RISK_MODERATE
    else:
        return RISK_LOW


def _worst_risk(*risk_levels: str) -> str:
    """Return the highest (worst) risk level among the given levels."""
    worst_score = 0
    worst_level = RISK_LOW
    for level in risk_levels:
        score = RISK_SCORES.get(level, 1)
        if score > worst_score:
            worst_score = score
            worst_level = level
    return worst_level


def calculate_risk(
    weather: WeatherData, load_weight_lbs: float
) -> RiskAssessment:
    """
    Calculate the risk level for a checkpoint based on weather conditions
    and load weight.

    The risk is the WORST (highest) across all weather conditions,
    then load modifiers may upgrade it further:

    Load modifier rules:
    - ≥55 mph wind → No Travel (any load) — already covered by wind threshold
    - 45–54 mph wind + >30,000 lb load → No Travel
    - 35–44 mph wind + >40,000 lb load → Severe

    Args:
        weather: Weather data at the checkpoint.
        load_weight_lbs: Load weight in pounds.

    Returns:
        RiskAssessment with risk level and numeric score.
    """
    # Determine base risk from weather thresholds
    factors = [
        (_wind_risk(weather.wind_speed), f"wind {weather.wind_speed:.0f} mph"),
        (_rain_risk(weather.rain_in_hr), f"rain {weather.rain_in_hr:.2f} in/hr"),
        (_snow_risk(weather.snow_in_hr), f"snow {weather.snow_in_hr:.2f} in/hr"),
    ]

    # Take the worst weather risk
    risk_level = _worst_risk(*(level for level, _ in factors))

    # Apply load modifier rules (can only increase risk, never decrease)
    load_rule = None
    if 45 <= weather.wind_speed < 55 and load_weight_lbs > 30000:
        load_rule = (RISK_NO_TRAVEL, "load over 30,000 lb")
    elif 35 <= weather.wind_speed < 45 and load_weight_lbs > 40000:
        load_rule = (RISK_SEVERE, "load over 40,000 lb")

    if load_rule and RISK_SCORES[load_rule[0]] > RISK_SCORES[risk_level]:
        risk_level = load_rule[0]
        reason = f"Wind {weather.wind_speed:.0f} mph with {load_rule[1]}"
    elif risk_level == RISK_LOW:
        reason = "All conditions below Moderate thresholds"
    else:
        drivers = [text for level, text in factors if level == risk_level]
        reason = " and ".join(drivers).capitalize()

    return RiskAssessment(
        risk_level=risk_level,
        risk_score=RISK_SCORES[risk_level],
        reason=reason,
        factor_levels={
            "wind": factors[0][0],
            "rain": factors[1][0],
            "snow": factors[2][0],
        },
    )
