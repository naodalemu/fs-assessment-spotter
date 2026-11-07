"""
Corridor heatmap — weather hazard intensity on a grid of cells covering all
route options, for every hour from departure to departure + 48 h.

The payload is compact: each cell is sent once with an array of 49 hourly
values, so the frontend can scrub the forecast slider without re-requesting.
"""

from datetime import datetime, timedelta

from .checkpoints import _haversine
from .weather import Forecasts, choose_cell_size, floor_to_hour, grid_cell, weather_intensity

FORECAST_HOURS = 48


# Upper bound on heatmap cells regardless of forecast budget: beyond this the
# payload grows without a visible gain at the zoom levels a whole trip is viewed at.
HEATMAP_MAX_CELLS = 400


def corridor_grid(geometries: list[list[list[float]]], budget: int) -> tuple[float, list[tuple[float, float]]]:
    """
    Finest grid (0.1° ≈ 7 mi, up to 1.5° on coast-to-coast trips) whose corridor
    fits `budget` forecast locations. Returns (cell size, cells).
    """
    budget = min(budget, HEATMAP_MAX_CELLS)
    size = choose_cell_size(lambda s: len(corridor_cells(geometries, s)), budget)
    return size, corridor_cells(geometries, size)


def corridor_cells(geometries: list[list[list[float]]], cell_size: float) -> list[tuple[float, float]]:
    """
    Cells along every route plus their 8 neighbours, so the heatmap covers a
    corridor about three cells wide instead of a thin line. Cells of 0.75°
    (~50 mi) or more already make a wide corridor, so there only the cells the
    routes pass through are used.
    """
    ring = (-1, 0, 1) if cell_size < 0.75 else (0,)
    step_miles = cell_size * 69 / 2
    cells: set[tuple[float, float]] = set()
    for geometry in geometries:
        travelled, next_sample = 0.0, 0.0
        for (lat1, lng1), (lat2, lng2) in zip(geometry, geometry[1:]):
            segment = _haversine(lat1, lng1, lat2, lng2)
            while segment > 0 and travelled + segment >= next_sample:
                f = (next_sample - travelled) / segment
                lat, lng = grid_cell(lat1 + f * (lat2 - lat1), lng1 + f * (lng2 - lng1), cell_size)
                for dy in ring:
                    for dx in ring:
                        cells.add((round(lat + dy * cell_size, 4), round(lng + dx * cell_size, 4)))
                next_sample += step_miles
            travelled += segment
    return sorted(cells)


def build_heatmap(
    cells: list[tuple[float, float]],
    cell_size: float,
    forecasts: Forecasts,
    departure_time: datetime,
) -> dict:
    start = floor_to_hour(departure_time)
    hours = range(FORECAST_HOURS + 1)
    return {
        "start_time": start.isoformat(),
        "hours": FORECAST_HOURS,
        "cell_size_deg": cell_size,
        "cells": [
            {
                "lat": lat,
                "lng": lng,
                "values": [
                    weather_intensity(forecasts.weather_at(lat, lng, start + timedelta(hours=h)))
                    for h in hours
                ],
            }
            for lat, lng in cells
        ],
    }
