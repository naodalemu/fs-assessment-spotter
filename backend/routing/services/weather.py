"""
Weather service — hourly forecasts from Open-Meteo for route checkpoints and
the corridor heatmap.

Open-Meteo is used because it needs no API key, returns *hourly* data, and can
report rain/snowfall directly in inches and wind in mph — the exact units of
the risk thresholds — so no unit conversion or 3-hour averaging is involved.

Forecasts are fetched once per request for every unique grid cell (batched,
in parallel) and cached for a short time. If the provider fails, the request
fails with a clear message — real and invented weather are never mixed.
A deterministic simulated weather field is available as an explicit demo mode
(WEATHER_PROVIDER=simulated).
"""

import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES = "temperature_2m,rain,showers,snowfall,wind_speed_10m,weather_code"

# Locations per Open-Meteo request (multi-location queries are comma separated).
BATCH_SIZE = 100
MAX_PARALLEL_REQUESTS = 4
REQUEST_TIMEOUT_SECONDS = 15
CACHE_TTL_SECONDS = 60 * 60  # Open-Meteo updates hourly
CACHE_BLOCK_HOURS = 6

SOURCE_LIVE = "open-meteo"
SOURCE_SIMULATED = "simulated"

# WMO weather interpretation codes -> short description
WMO_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Freezing fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Freezing drizzle",
    57: "Heavy freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Heavy freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Severe thunderstorm with hail",
}


@dataclass
class WeatherData:
    """Weather information at a specific point and time."""

    description: str
    temperature: float  # °F
    wind_speed: float  # mph
    rain_in_hr: float  # inches per hour
    snow_in_hr: float  # inches per hour


def floor_to_hour(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def grid_cell(lat: float, lng: float, size_deg: float) -> tuple[float, float]:
    """Snap a coordinate to the centre of its grid cell."""
    return (
        round(round(lat / size_deg) * size_deg, 4),
        round(round(lng / size_deg) * size_deg, 4),
    )


# ---------------------------------------------------------------------------
# Simulated weather (offline / provider-failure fallback)
# ---------------------------------------------------------------------------


def get_mock_weather(lat: float, lng: float, eta: datetime) -> WeatherData:
    """
    Deterministic synthetic weather for (lat, lng, eta).

    Models weather fronts drifting east/north-east over time so that different
    routes, checkpoints and forecast hours see different conditions.
    """
    ts = eta.timestamp() if isinstance(eta, datetime) else 0.0
    hours = ts / 3600.0
    hour_of_day = hours % 24.0

    u = 0.08 * lat + 0.06 * lng - 0.03 * hours
    v = 0.05 * lat - 0.07 * lng + 0.02 * hours
    storm = 0.55 * math.sin(u * 2.0 * math.pi) + 0.45 * math.cos(v * 2.0 * math.pi)
    s = (storm + 1.0) / 2.0  # 0..1

    base_temp = 75.0 - (lat - 28.0) * 1.1
    diurnal = 6.0 * math.sin((hour_of_day - 9.0) / 24.0 * 2.0 * math.pi)
    temp = round(max(-10.0, min(105.0, base_temp + diurnal - 8.0 * s)), 1)
    freezing = temp <= 32.0

    rain = snow = 0.0
    if s < 0.40:
        wind = 8.0 + 10.0 * (s / 0.40)
        description = "Clear sky" if s < 0.20 else "Partly cloudy"
    elif s < 0.65:
        f = (s - 0.40) / 0.25
        wind = 25.0 + 8.0 * f
        if freezing:
            snow, description = 0.50 + 0.40 * f, "Snow"
        else:
            rain, description = 0.10 + 0.12 * f, "Rain"
    elif s < 0.85:
        f = (s - 0.65) / 0.20
        wind = 36.0 + 7.5 * f
        if freezing:
            snow, description = 1.10 + 0.70 * f, "Heavy snow"
        else:
            rain, description = 0.26 + 0.20 * f, "Heavy rain"
    else:
        f = (s - 0.85) / 0.15
        wind = 46.0 + 7.5 * f
        if freezing:
            snow, description = 2.10 + 0.75 * f, "Blizzard"
        else:
            rain, description = 0.52 + 0.38 * f, "Severe thunderstorm"

    return WeatherData(
        description=description,
        temperature=temp,
        wind_speed=round(wind, 1),
        rain_in_hr=round(rain, 3),
        snow_in_hr=round(snow, 3),
    )


# ---------------------------------------------------------------------------
# Open-Meteo fetching + cache
# ---------------------------------------------------------------------------

# (cell, start_ts, end_ts) -> (fetched_at, hourly dict)
_cache: dict[tuple, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def clear_cache():
    with _cache_lock:
        _cache.clear()


def _request_batch(cells: list[tuple[float, float]], start: datetime, end: datetime) -> list[dict]:
    """Fetch hourly forecasts for a batch of cells. Returns one 'hourly' dict per cell."""
    response = requests.get(
        OPEN_METEO_URL,
        params={
            "latitude": ",".join(str(c[0]) for c in cells),
            "longitude": ",".join(str(c[1]) for c in cells),
            "hourly": HOURLY_VARIABLES,
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "temperature_unit": "fahrenheit",
            "timezone": "GMT",
            "timeformat": "unixtime",
            "start_hour": start.strftime("%Y-%m-%dT%H:%M"),
            "end_hour": end.strftime("%Y-%m-%dT%H:%M"),
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):  # single-location responses are not wrapped in a list
        data = [data]
    return [entry["hourly"] for entry in data]


class WeatherUnavailable(Exception):
    """The forecast provider could not supply every requested location."""


class Forecasts:
    """
    Hourly forecasts for a set of grid cells over a fixed time window.

    Either every lookup is a real forecast, or (WEATHER_PROVIDER=simulated)
    every lookup is simulated — the two are never mixed.
    """

    def __init__(self, cell_size_deg: float, hourly_by_cell: dict, simulated: bool = False):
        self.cell_size_deg = cell_size_deg
        self._hourly = hourly_by_cell
        self.simulated = simulated

    @property
    def source(self) -> str:
        return SOURCE_SIMULATED if self.simulated else SOURCE_LIVE

    def weather_at(self, lat: float, lng: float, when: datetime) -> WeatherData:
        """
        Weather at a point for the forecast hour containing `when`.

        Open-Meteo's hourly rain/snowfall values are totals for the preceding
        hour, so the value stamped at the *next* full hour describes conditions
        at `when` — that is the in/hr rate compared against the thresholds.
        """
        if self.simulated:
            return get_mock_weather(lat, lng, when)

        hourly = self._hourly[grid_cell(lat, lng, self.cell_size_deg)]
        times = hourly["time"]
        target = math.ceil(when.timestamp() / 3600.0) * 3600
        idx = min(max(int((target - times[0]) // 3600), 0), len(times) - 1)

        def value(key: str) -> float:
            v = hourly.get(key, [None] * len(times))[idx]
            return float(v) if v is not None else 0.0

        code = int(value("weather_code"))
        return WeatherData(
            description=WMO_DESCRIPTIONS.get(code, "Unknown"),
            temperature=round(value("temperature_2m"), 1),
            wind_speed=round(value("wind_speed_10m"), 1),
            rain_in_hr=round(value("rain") + value("showers"), 3),
            snow_in_hr=round(value("snowfall"), 3),
        )


# Open-Meteo's free tier allows 600 locations per minute; each search stays
# well under that by coarsening the grid on long trips.
CELL_SIZES_DEG = (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0)


def choose_cell_size(count_cells, budget: int) -> float:
    """Smallest grid size whose number of cells (`count_cells(size)`) fits the budget."""
    for size in CELL_SIZES_DEG:
        if count_cells(size) <= budget:
            return size
    return CELL_SIZES_DEG[-1]


def fetch_forecasts(
    points: list[tuple[float, float]],
    start: datetime,
    end: datetime,
    cell_size_deg: float,
) -> Forecasts:
    """
    Fetch hourly forecasts covering [start, end] for every grid cell touched
    by `points`.

    Raises WeatherUnavailable if any location cannot be fetched — results are
    never padded with invented weather.
    """
    if getattr(settings, "WEATHER_PROVIDER", "open-meteo") == SOURCE_SIMULATED:
        return Forecasts(cell_size_deg, {}, simulated=True)

    # Align the window to 6-hour blocks so searches with nearby departure times
    # (from any user) hit the same cache entries.
    start = floor_to_hour(start)
    start -= timedelta(hours=start.hour % CACHE_BLOCK_HOURS)
    end = floor_to_hour(end)
    end += timedelta(hours=CACHE_BLOCK_HOURS - end.hour % CACHE_BLOCK_HOURS)
    window = (int(start.timestamp()), int(end.timestamp()))

    cells = sorted({grid_cell(lat, lng, cell_size_deg) for lat, lng in points})
    hourly_by_cell: dict = {}
    missing = []
    now = time.time()
    with _cache_lock:
        for cell in cells:
            cached = _cache.get((cell, *window))
            if cached and now - cached[0] < CACHE_TTL_SECONDS:
                hourly_by_cell[cell] = cached[1]
            else:
                missing.append(cell)

    batches = [missing[i:i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]

    def run(batch):
        try:
            return batch, _request_batch(batch, start, end), None
        except requests.HTTPError as exc:  # don't log the (very long) request URL
            return batch, None, exc.response.status_code if exc.response is not None else None
        except Exception as exc:  # network error, bad JSON
            logger.warning("Open-Meteo request failed: %s", type(exc).__name__)
            return batch, None, None

    failures = []
    if batches:
        with ThreadPoolExecutor(max_workers=min(len(batches), MAX_PARALLEL_REQUESTS)) as pool:
            for batch, results, status in pool.map(run, batches):
                if results is None or len(results) != len(batch):
                    failures.append(status)
                    continue
                with _cache_lock:
                    for cell, hourly in zip(batch, results):
                        hourly_by_cell[cell] = hourly
                        _cache[(cell, *window)] = (now, hourly)

    if failures:
        logger.warning("Open-Meteo failed for %d of %d batches (HTTP %s)", len(failures), len(batches), failures)
        if 429 in failures:
            logger.error("Open-Meteo rate limit reached (HTTP 429).")
        raise WeatherUnavailable("Weather forecasts are temporarily unavailable. Please try again in a minute.")

    return Forecasts(cell_size_deg, hourly_by_cell)


# ---------------------------------------------------------------------------
# Heatmap intensity
# ---------------------------------------------------------------------------

# Breakpoints mapping each variable onto a 0..1 hazard scale. The risk-level
# thresholds land on 0.2 / 0.4 / 0.6 / 0.8, so the heatmap colour bands line up
# exactly with Low / Moderate / High / Severe / No Travel.
_INTENSITY_BREAKPOINTS = {
    "wind": [(0, 0.0), (25, 0.2), (35, 0.4), (45, 0.6), (55, 0.8), (70, 1.0)],
    "rain": [(0, 0.0), (0.10, 0.2), (0.25, 0.4), (0.50, 0.6), (1.00, 0.8), (2.0, 1.0)],
    "snow": [(0, 0.0), (0.5, 0.2), (1.0, 0.4), (2.0, 0.6), (3.0, 0.8), (4.0, 1.0)],
}


def _interpolate(value: float, breakpoints: list[tuple[float, float]]) -> float:
    if value <= breakpoints[0][0]:
        return breakpoints[0][1]
    for (x0, y0), (x1, y1) in zip(breakpoints, breakpoints[1:]):
        if value <= x1:
            return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
    return breakpoints[-1][1]


def weather_intensity(weather: WeatherData) -> float:
    """Normalised 0..1 hazard intensity: the worst of wind, rain and snow."""
    return round(
        max(
            _interpolate(weather.wind_speed, _INTENSITY_BREAKPOINTS["wind"]),
            _interpolate(weather.rain_in_hr, _INTENSITY_BREAKPOINTS["rain"]),
            _interpolate(weather.snow_in_hr, _INTENSITY_BREAKPOINTS["snow"]),
        ),
        3,
    )
