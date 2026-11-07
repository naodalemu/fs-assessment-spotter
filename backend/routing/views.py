"""
API views for the routing application.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import lru_cache

from django.conf import settings
from geopy.geocoders import Nominatim
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RouteRequestSerializer
from .services.checkpoints import generate_checkpoints, get_adaptive_interval
from .services.heatmap import FORECAST_HOURS, HEATMAP_MAX_CELLS, build_heatmap, corridor_grid
from .services.recommender import compute_risk_summary, recommend_routes
from .services.risk import calculate_risk
from .services.routing import RoutingUnavailable, get_routes, simplify
from .services.weather import WeatherUnavailable, choose_cell_size, fetch_forecasts, grid_cell

logger = logging.getLogger(__name__)

geocoder = Nominatim(user_agent="weather-aware-truck-routing/1.0", timeout=10)

# The heatmap always gets at least this many forecast locations.
HEATMAP_MIN_CELLS = 60


def _forecast_grids(checkpoint_points, geometries):
    """
    Split the per-search forecast budget (settings.FORECAST_LOCATION_BUDGET).

    Checkpoints come first: they drive the risk levels and the recommendation,
    so each normally gets its own ~7 mi (0.1°) forecast. The heatmap, a visual
    overview, uses what is left. With a budget of 0 (no provider limit) both
    run at full resolution.

    Returns (checkpoint cell size, heatmap cell size, heatmap cells).
    """
    total = settings.FORECAST_LOCATION_BUDGET
    count = lambda size: len({grid_cell(lat, lng, size) for lat, lng in checkpoint_points})  # noqa: E731
    if not total:
        heat_size, heat_cells = corridor_grid(geometries, HEATMAP_MAX_CELLS)
        return 0.1, heat_size, heat_cells
    cp_size = choose_cell_size(count, total - HEATMAP_MIN_CELLS)
    heat_size, heat_cells = corridor_grid(geometries, max(HEATMAP_MIN_CELLS, total - count(cp_size)))
    return cp_size, heat_size, heat_cells


def _parse_coords(address: str) -> tuple[float, float] | None:
    """Parse 'lat, lng' if the address is a coordinate pair."""
    parts = [p.strip() for p in address.split(",")]
    if len(parts) == 2:
        try:
            lat, lng = float(parts[0]), float(parts[1])
        except ValueError:
            return None
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    return None


@lru_cache(maxsize=512)
def _geocode(address: str) -> tuple[float, float]:
    """
    Resolve an address to (lat, lng) with Nominatim. The frontend sends
    coordinates for autocomplete selections, so this mainly handles free text.

    Raises ValueError if the address cannot be resolved.
    """
    parsed = _parse_coords(address)
    if parsed:
        return parsed
    try:
        location = geocoder.geocode(address, country_codes="us")
    except Exception as exc:
        logger.warning("Geocoding failed for %r: %s", address, exc)
        raise ValueError(f"Geocoding service unavailable for '{address}'. Try again shortly.") from exc
    if location is None:
        raise ValueError(f"Could not find '{address}'. Try a city and state, e.g. 'Denver, CO'.")
    return location.latitude, location.longitude


def _error(message: str, status_code: int, fields: dict | None = None) -> Response:
    body = {"error": message}
    if fields:
        body["fields"] = fields
    return Response(body, status=status_code)


class RouteView(APIView):
    """
    POST /api/routes/

    Returns up to 3 HGV routes, each with weather checkpoints (sampled at the
    truck's ETA), risk levels, a risk-mileage summary and a recommendation,
    plus a 0–48 h corridor weather heatmap.
    """

    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            fields = {k: " ".join(str(m) for m in v) for k, v in serializer.errors.items()}
            first_field, first_message = next(iter(fields.items()))
            label = first_field.replace("_", " ").capitalize()
            return _error(f"{label}: {first_message}", status.HTTP_400_BAD_REQUEST, fields)

        data = serializer.validated_data
        departure = data["departure_datetime"]
        load_weight = data["load_weight_lbs"]
        requested_interval = data.get("interval_miles")

        try:
            origin = _geocode(data["origin"])
            destination = _geocode(data["destination"])
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)

        try:
            routes = get_routes(origin, destination)
        except RoutingUnavailable as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        if not routes:
            return _error("No route found between these locations.", status.HTTP_404_NOT_FOUND)

        # 1. Sample checkpoints along each route at the chosen interval
        sampled = []
        for route in routes:
            interval = float(requested_interval or get_adaptive_interval(route.distance_miles))
            checkpoints = generate_checkpoints(
                route.geometry, route.distance_miles, route.travel_time_hours, departure, interval
            )
            sampled.append((route, interval, checkpoints))

        # 2. Fetch forecasts for checkpoints and the heatmap corridor in parallel
        checkpoint_points = [(cp.lat, cp.lng) for _, _, cps in sampled for cp in cps]
        cp_cell_size, heat_cell_size, heat_cells = _forecast_grids(checkpoint_points, [r.geometry for r in routes])
        last_arrival = max(cps[-1].eta for _, _, cps in sampled if cps)
        window_end = max(last_arrival, departure + timedelta(hours=FORECAST_HOURS))

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                cp_future = pool.submit(fetch_forecasts, checkpoint_points, departure, window_end, cp_cell_size)
                heat_future = pool.submit(fetch_forecasts, heat_cells, departure, window_end, heat_cell_size)
                cp_forecasts, heat_forecasts = cp_future.result(), heat_future.result()
        except WeatherUnavailable as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)

        # 3. Weather + risk at each checkpoint's ETA, then per-route summaries
        results = []
        for route, interval, checkpoints in sampled:
            checkpoint_data = []
            for cp in checkpoints:
                weather = cp_forecasts.weather_at(cp.lat, cp.lng, cp.eta)
                risk = calculate_risk(weather, load_weight)
                checkpoint_data.append({
                    "lat": cp.lat,
                    "lng": cp.lng,
                    "mile_marker": cp.mile_marker,
                    "eta": cp.eta.isoformat(),
                    "weather": {
                        "description": weather.description,
                        "temperature_f": weather.temperature,
                        "wind_mph": weather.wind_speed,
                        "rain_in_hr": weather.rain_in_hr,
                        "snow_in_hr": weather.snow_in_hr,
                    },
                    "risk_level": risk.risk_level,
                    "risk_score": risk.risk_score,
                    "risk_reason": risk.reason,
                    "factor_levels": risk.factor_levels,
                })

            summary = compute_risk_summary(checkpoint_data, route.distance_miles)
            results.append({
                "name": f"Route {route.route_index + 1}",
                "route_index": route.route_index,
                "distance_miles": route.distance_miles,
                "travel_time_hours": route.travel_time_hours,
                "departure_time": departure.isoformat(),
                "arrival_time": (departure + timedelta(hours=route.travel_time_hours)).isoformat(),
                "interval_miles": interval,
                "geometry": simplify(route.geometry),
                "checkpoints": checkpoint_data,
                "risk_summary": vars(summary),
            })

        # 4. Rank routes and build the heatmap
        ranked = recommend_routes(results)
        heatmap = build_heatmap(heat_cells, heat_cell_size, heat_forecasts, departure)

        return Response({
            "routes": ranked,
            "heatmap": heatmap,
            "origin": {"query": data["origin"], "lat": origin[0], "lng": origin[1]},
            "destination": {"query": data["destination"], "lat": destination[0], "lng": destination[1]},
            "load_weight_lbs": load_weight,
            "sources": {
                "routing": routes[0].source,
                "weather": cp_forecasts.source,
            },
        })
