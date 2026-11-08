"""
Routing service — OpenRouteService `driving-hgv` (heavy goods vehicle) routes.

ORS only computes `alternative_routes` for trips under 100 km, so for longer
trips the alternatives are real HGV routes forced through a via-point offset
to either side of the direct corridor. All candidate requests run in parallel,
near-duplicate routes are discarded, and the best three distinct routes are
returned.

When no ORS key is configured, or ORS is unreachable, simulated routes are
generated instead and flagged with `source="simulated"`.
"""

import copy
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import polyline as polyline_codec
import requests
from django.conf import settings

from .checkpoints import _haversine, polyline_length_miles

logger = logging.getLogger(__name__)

# api.openrouteservice.org is deprecated (quota-restricted, then shut off) in
# favour of HeiGIT's unified API host; same keys and request format.
ORS_DIRECTIONS_URL = "https://api.heigit.org/openrouteservice/v2/directions/driving-hgv"
# (connect, read) — fail fast on a dead connection, allow slow route computation
ORS_TIMEOUT_SECONDS = (6, 20)
ORS_ATTEMPTS = 2

METERS_TO_MILES = 0.000621371
SECONDS_TO_HOURS = 1 / 3600

SOURCE_ORS = "openrouteservice"
SOURCE_SIMULATED = "simulated"

ROUTE_COUNT = 3
# ORS rejects alternative_routes above 100 km of road distance; the straight-line
# distance is used as a conservative proxy.
ORS_ALTERNATIVES_LIMIT_MILES = 50
# Snap radii (metres): endpoints may be a city centre off the road network,
# via-points only steer the route so they may snap further away.
ENDPOINT_SNAP_RADIUS_M = 5000
VIA_SNAP_RADIUS_M = 25000
# Via-point offsets as a fraction of the origin→destination distance.
# The second round is only requested if the first does not yield 3 distinct routes.
VIA_OFFSET_ROUNDS = [(0.18, -0.18), (0.35, -0.35)]
# Discard detours that are absurdly longer than the fastest route.
MAX_DETOUR_RATIO = 1.5
# Routes sharing more than this fraction of their path are considered duplicates.
DUPLICATE_OVERLAP = 0.85
# Real ORS results are reused by every user searching the same trip.
ROUTE_CACHE_TTL_SECONDS = 24 * 60 * 60  # road networks rarely change
_route_cache: dict[tuple, tuple[float, list]] = {}

# Polyline simplification tolerance for the response (degrees, ~50 m).
SIMPLIFY_TOLERANCE_DEG = 0.0005


class RoutingUnavailable(Exception):
    """OpenRouteService is configured but could not provide a route."""


@dataclass
class Route:
    """A single driving route."""

    geometry: list[list[float]]  # [lat, lng] pairs
    distance_miles: float
    travel_time_hours: float
    route_index: int = 0
    source: str = SOURCE_ORS


def is_placeholder_key(key: str | None) -> bool:
    """Return True if the API key is not configured or contains placeholder text."""
    if not key or not str(key).strip():
        return True
    key_lower = str(key).strip().lower()
    return (
        "your_" in key_lower
        or "api_key_here" in key_lower
        or "placeholder" in key_lower
        or key_lower in ("none", "null", "changeme", "change_me")
    )


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def remove_loops(geometry: list[list[float]], tolerance_miles: float = 0.04,
                 min_loop_miles: float = 0.5) -> list[list[float]]:
    """
    Cut out-and-back spurs and loops from a polyline.

    A via-point that snaps to a side road makes the router drive down that
    road and back. Whenever the path returns within `tolerance_miles` of a
    point it passed at least `min_loop_miles` earlier, everything in between
    is dropped.
    """
    cell = tolerance_miles / 69.0  # degrees of latitude
    buckets: dict[tuple[int, int], list[int]] = {}
    out: list[list[float]] = []
    dist: list[float] = []  # cumulative distance of each point in `out`

    def key(pt):
        return int(pt[0] // cell), int(pt[1] // cell)

    for pt in geometry:
        travelled = dist[-1] + _haversine(*out[-1], *pt) if out else 0.0
        kx, ky = key(pt)
        loop_start = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for i in buckets.get((kx + dx, ky + dy), ()):
                    if (
                        i < len(out)
                        and travelled - dist[i] >= min_loop_miles
                        and _haversine(*out[i], *pt) <= tolerance_miles
                        and (loop_start is None or i < loop_start)
                    ):
                        loop_start = i
        if loop_start is not None:
            for p in out[loop_start + 1:]:
                bucket = buckets.get(key(p))
                if bucket:
                    bucket[:] = [i for i in bucket if i <= loop_start]
            del out[loop_start + 1:]
            del dist[loop_start + 1:]
            travelled = dist[-1] + _haversine(*out[-1], *pt)
        buckets.setdefault((kx, ky), []).append(len(out))
        out.append(pt)
        dist.append(travelled)
    return out


def simplify(geometry: list[list[float]], tolerance: float = SIMPLIFY_TOLERANCE_DEG) -> list[list[float]]:
    """Ramer–Douglas–Peucker simplification (iterative) to keep responses small."""
    n = len(geometry)
    if n < 3:
        return geometry
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        (ay, ax), (by, bx) = geometry[start], geometry[end]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        max_d, max_i = 0.0, -1
        for i in range(start + 1, end):
            py, px = geometry[i]
            if norm == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
            if d > max_d:
                max_d, max_i = d, i
        if max_d > tolerance:
            keep[max_i] = True
            stack.append((start, max_i))
            stack.append((max_i, end))
    return [pt for pt, k in zip(geometry, keep) if k]


def _sample_along(geometry: list[list[float]], count: int) -> list[list[float]]:
    step = max(1, len(geometry) // count)
    return geometry[::step]


def _overlap(a: list[list[float]], b: list[list[float]], tolerance_miles: float = 2.0) -> float:
    """Fraction of route `a` that runs within `tolerance_miles` of route `b`."""
    samples = _sample_along(a, 40)
    reference = _sample_along(b, 400)
    near = sum(
        1 for p in samples
        if any(_haversine(p[0], p[1], q[0], q[1]) <= tolerance_miles for q in reference)
    )
    return near / len(samples)


# ---------------------------------------------------------------------------
# OpenRouteService
# ---------------------------------------------------------------------------


def _via_point(origin, destination, offset_fraction):
    """Point beside the corridor midpoint, offset perpendicular to the trip direction."""
    lat1, lng1 = origin
    lat2, lng2 = destination
    mid_lat = (lat1 + lat2) / 2
    k = math.cos(math.radians(mid_lat))  # make the offset geometrically perpendicular
    dx, dy = (lng2 - lng1) * k, lat2 - lat1
    length = math.hypot(dx, dy) or 1e-9
    nx, ny = -dy / length, dx / length
    chord = length * offset_fraction
    return mid_lat + ny * chord, (lng1 + lng2) / 2 + nx * chord / k


def _ors_request(api_key: str, coordinates: list[tuple[float, float]], alternatives: bool) -> list[Route]:
    """POST a directions request. `coordinates` are (lat, lng) tuples."""
    radiuses = [ENDPOINT_SNAP_RADIUS_M] + [VIA_SNAP_RADIUS_M] * (len(coordinates) - 2) + [ENDPOINT_SNAP_RADIUS_M]
    body = {
        "coordinates": [[lng, lat] for lat, lng in coordinates],
        "radiuses": radiuses,
        "instructions": False,
    }
    if alternatives:
        body["alternative_routes"] = {"target_count": ROUTE_COUNT, "share_factor": 0.6, "weight_factor": 1.6}

    response = requests.post(
        ORS_DIRECTIONS_URL,
        json=body,
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        timeout=ORS_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    routes = []
    for data in response.json().get("routes", []):
        raw = [[lat, lng] for lat, lng in polyline_codec.decode(data["geometry"])]
        geometry = remove_loops(raw) if len(coordinates) > 2 else raw
        summary = data.get("summary", {})
        distance = summary.get("distance", 0) * METERS_TO_MILES
        duration = summary.get("duration", 0) * SECONDS_TO_HOURS
        # Shrink distance/time proportionally to any spur that was cut out
        raw_length = polyline_length_miles(raw)
        ratio = polyline_length_miles(geometry) / raw_length if raw_length else 1.0
        if distance > 0 and duration > 0:
            routes.append(Route(geometry, round(distance * ratio, 1), round(duration * ratio, 2)))
    return routes


def _fetch_ors_routes(api_key: str, origin, destination) -> list[Route]:
    direct_miles = _haversine(*origin, *destination)
    use_alternatives = direct_miles <= ORS_ALTERNATIVES_LIMIT_MILES

    failures: list[int | None] = []  # HTTP status per failed request (None = network)
    unroutable: set[str] = set()  # "origin" / "destination" with no road nearby

    def request(coords, alternatives=False):
        for attempt in range(1, ORS_ATTEMPTS + 1):
            try:
                return _ors_request(api_key, coords, alternatives)
            except (requests.ConnectionError, requests.Timeout) as exc:
                logger.warning("ORS request attempt %d failed: %s", attempt, exc)
            except requests.HTTPError as exc:  # e.g. no road near a point, quota exceeded
                code = exc.response.status_code if exc.response is not None else None
                logger.warning("ORS request failed: HTTP %s", code)
                failures.append(code)
                endpoint = _unroutable_endpoint(exc.response, len(coords))
                if endpoint:
                    unroutable.add(endpoint)
                return None
            except Exception as exc:  # malformed payload
                logger.warning("ORS request failed: %s", exc)
                failures.append(None)
                return None
        failures.append(None)
        return None

    candidates: list[Route] = []
    for round_index, offsets in enumerate(VIA_OFFSET_ROUNDS):
        jobs = [[origin, _via_point(origin, destination, f), destination] for f in offsets]
        if round_index == 0:
            jobs.insert(0, [origin, destination])
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            results = list(pool.map(
                lambda c: request(c, alternatives=use_alternatives and len(c) == 2), jobs
            ))
        if all(r is None for r in results):
            break  # service unreachable — don't keep trying
        for routes in results:
            candidates.extend(routes or [])

        distinct = _select_distinct(candidates)
        if len(distinct) >= ROUTE_COUNT:
            break

    if not candidates:
        raise RoutingUnavailable(_failure_message(failures, unroutable))
    return _select_distinct(candidates)


ROUTING_UNAVAILABLE_MESSAGE = "Routing is temporarily unavailable. Please try again in a minute."


# ORS error code for "Could not find routable point within a radius of ... of
# specified coordinate N"
ORS_NO_ROUTABLE_POINT = 2010


def _unroutable_endpoint(response, coordinate_count: int) -> str | None:
    """'origin' or 'destination' if ORS says that point has no road nearby."""
    try:
        error = response.json()["error"]
        if error.get("code") != ORS_NO_ROUTABLE_POINT:
            return None
        index = int(error["message"].split("specified coordinate")[1].split(":")[0])
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None
    if index == 0:
        return "origin"
    if index == coordinate_count - 1:
        return "destination"
    return None  # a via-point, which only steers alternatives


def _failure_message(statuses: list[int | None], unroutable: set[str] = frozenset()) -> str:
    """
    User-facing message. Quota, key and provider problems are operational
    details: they are logged for the operator, and the user only sees that
    routing is temporarily unavailable. A point far from any road is the
    user's input, so that case says which one.
    """
    if unroutable:
        which = " and ".join(p for p in ("origin", "destination") if p in unroutable)
        verb = "are" if len(unroutable) > 1 else "is"
        return f"No truck route: the {which} {verb} not near a drivable road. Choose a point on or near a road."
    if statuses and all(s == 404 for s in statuses):
        return "No truck route found: the origin or destination is not near a drivable road."
    if 401 in statuses:
        logger.error("OpenRouteService rejected ORS_API_KEY (HTTP 401).")
    elif 403 in statuses or 429 in statuses:
        logger.error("OpenRouteService quota or rate limit reached (HTTP %s).", statuses)
    return ROUTING_UNAVAILABLE_MESSAGE


def _select_distinct(candidates: list[Route]) -> list[Route]:
    """Fastest-first, dropping near-duplicates and unreasonable detours."""
    ordered = sorted(candidates, key=lambda r: r.travel_time_hours)
    fastest = ordered[0].travel_time_hours
    selected: list[Route] = []
    for route in ordered:
        if route.travel_time_hours > fastest * MAX_DETOUR_RATIO:
            continue
        if any(_overlap(route.geometry, s.geometry) >= DUPLICATE_OVERLAP for s in selected):
            continue
        selected.append(route)
        if len(selected) == ROUTE_COUNT:
            break
    return selected


def get_routes(
    origin_coords: tuple[float, float],
    destination_coords: tuple[float, float],
) -> list[Route]:
    """
    Return up to 3 distinct HGV routes, fastest first.

    Without an ORS key the app runs in demo mode with simulated routes (flagged
    in the response). With a key, an ORS failure raises RoutingUnavailable:
    invented routes are never passed off as real roads.
    """
    api_key = getattr(settings, "ORS_API_KEY", None)
    if is_placeholder_key(api_key):
        logger.info("ORS_API_KEY not configured: using simulated demo routes.")
        routes = generate_mock_routes(origin_coords, destination_coords)
    else:
        cache_key = tuple(round(c, 4) for c in (*origin_coords, *destination_coords))
        cached = _route_cache.get(cache_key)
        if cached and time.time() - cached[0] < ROUTE_CACHE_TTL_SECONDS:
            routes = copy.deepcopy(cached[1])
        else:
            routes = _fetch_ors_routes(api_key, origin_coords, destination_coords)
            _route_cache[cache_key] = (time.time(), copy.deepcopy(routes))

    for index, route in enumerate(routes):
        route.route_index = index
    return routes


# ---------------------------------------------------------------------------
# Simulated routes (demo mode: no ORS key configured)
# ---------------------------------------------------------------------------


def generate_mock_routes(
    origin_coords: tuple[float, float],
    destination_coords: tuple[float, float],
) -> list[Route]:
    """
    Three smooth synthetic corridors between origin and destination: a direct
    one and two bowed alternatives on either side. Used only for offline demos.
    """
    lat1, lng1 = origin_coords
    lat2, lng2 = destination_coords
    direct_dist = max(_haversine(lat1, lng1, lat2, lng2), 10.0)

    dlat, dlng = lat2 - lat1, lng2 - lng1
    chord = math.hypot(dlat, dlng)
    if chord < 1e-6:
        dlat, dlng = 0.1, 0.1
        chord = math.hypot(dlat, dlng)
    nlat, nlng = -dlng / chord, dlat / chord

    num_points = max(30, min(int(direct_dist / 8.0), 120))
    # (average speed mph, main bow, s-bend)
    configs = [(58.0, 0.05, 0.015), (55.0, 0.18, 0.030), (52.0, -0.16, -0.025)]

    routes = []
    for idx, (speed, bow, wiggle) in enumerate(configs):
        geometry = []
        for i in range(num_points):
            t = i / (num_points - 1)
            disp = bow * chord * math.sin(math.pi * t) + wiggle * chord * math.sin(
                (3.0 if idx == 0 else 2.0) * math.pi * t
            )
            geometry.append([round(lat1 + t * dlat + disp * nlat, 6), round(lng1 + t * dlng + disp * nlng, 6)])
        geometry[0] = [round(lat1, 6), round(lng1, 6)]
        geometry[-1] = [round(lat2, 6), round(lng2, 6)]

        # Roads are ~15–20% longer than the drawn curve
        distance = round(polyline_length_miles(geometry) * 1.18, 1)
        routes.append(Route(geometry, distance, round(distance / speed, 2), idx, SOURCE_SIMULATED))
    return routes
