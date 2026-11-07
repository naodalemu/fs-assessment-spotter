"""
Checkpoint sampler — walks a route polyline and samples checkpoints
at regular distance intervals with estimated arrival times.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Checkpoint:
    """A sampled point along a route."""

    lat: float
    lng: float
    mile_marker: float
    eta: datetime


EARTH_RADIUS_MILES = 3958.8

SAMPLING_INTERVALS_MILES = (10.0, 25.0, 50.0)


def get_adaptive_interval(distance_miles: float) -> float:
    """
    'Auto' sampling: pick 10 / 25 / 50 miles based on trip length so short
    trips get dense sampling and long trips stay fast to compute and render.
    """
    if distance_miles > 600:
        return 50.0
    if distance_miles > 200:
        return 25.0
    return 10.0


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in miles."""
    lat1_r, lng1_r = math.radians(lat1), math.radians(lng1)
    lat2_r, lng2_r = math.radians(lat2), math.radians(lng2)
    dlat = lat2_r - lat1_r
    dlng = lng2_r - lng1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return EARTH_RADIUS_MILES * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def polyline_length_miles(geometry: list[list[float]]) -> float:
    return sum(
        _haversine(a[0], a[1], b[0], b[1]) for a, b in zip(geometry, geometry[1:])
    )


def generate_checkpoints(
    geometry: list[list[float]],
    total_distance_miles: float,
    travel_time_hours: float,
    departure_time: datetime,
    interval_miles: float = 25.0,
) -> list[Checkpoint]:
    """
    Sample a checkpoint every `interval_miles` of driving distance, plus the
    origin and the destination.

    The polyline's straight-segment length is slightly shorter than the road
    distance reported by the routing engine, so polyline distances are scaled
    to the reported road distance — mile markers therefore match the route
    summary and the final checkpoint lands exactly on the destination.

    ETAs assume the route's average speed (total distance / total time).
    """
    if not geometry or len(geometry) < 2 or total_distance_miles <= 0:
        return []

    geometric_length = polyline_length_miles(geometry)
    scale = total_distance_miles / geometric_length if geometric_length > 0 else 1.0
    hours_per_mile = travel_time_hours / total_distance_miles

    def make(lat: float, lng: float, mile: float) -> Checkpoint:
        return Checkpoint(
            lat=round(lat, 6),
            lng=round(lng, 6),
            mile_marker=round(mile, 1),
            eta=departure_time + timedelta(hours=mile * hours_per_mile),
        )

    checkpoints = [make(geometry[0][0], geometry[0][1], 0.0)]
    next_mile = interval_miles
    travelled = 0.0

    for (lat1, lng1), (lat2, lng2) in zip(geometry, geometry[1:]):
        segment = _haversine(lat1, lng1, lat2, lng2) * scale
        while segment > 0 and travelled + segment >= next_mile and next_mile < total_distance_miles:
            f = (next_mile - travelled) / segment
            checkpoints.append(make(lat1 + f * (lat2 - lat1), lng1 + f * (lng2 - lng1), next_mile))
            next_mile += interval_miles
        travelled += segment

    # Always finish on the destination; drop a sample sitting practically on top of it
    if len(checkpoints) > 1 and total_distance_miles - checkpoints[-1].mile_marker < interval_miles * 0.1:
        checkpoints.pop()
    checkpoints.append(make(geometry[-1][0], geometry[-1][1], total_distance_miles))

    return checkpoints
