# Weather-Aware Truck Routing

A web app that helps a truck driver choose the safest route. Enter an origin,
a destination, a departure time and the load weight; the app finds three truck
routes, checks the weather forecast along each one at the time the truck will
actually be there, rates the risk using wind, rain, snow and load-weight
rules, and recommends the best route.

**Live demo:** https://weather-truck-routing-24aj.onrender.com
(hosted on a free plan: if it has been idle, the first search takes about a
minute while the server wakes up)

Built with React (Vite, MUI, Leaflet) and Django REST Framework.

---

## Features

- **Trip input**: origin and destination by typing (with suggestions) or by
  clicking the map, departure date and time, and load weight.
- **Three truck routes** from a heavy-goods-vehicle routing engine.
- **Weather checkpoints** every 10, 25 or 50 miles (or automatic), each using
  the forecast for the hour the truck reaches it.
- **Risk levels** per checkpoint (Low, Moderate, High, Severe, No Travel), with
  the reason for each rating.
- **Recommendation** of the safest route, with the deciding factor explained.
- **Map** with all routes, color-coded checkpoints, ETAs and details on click.
- **Corridor weather heatmap** with a 0–48 hour forecast slider. Playing it
  moves a truck marker along the selected route.
- Light and dark map, and a full-screen map mode.

---

## Getting started

### Prerequisites

- Python 3.11+
- Node.js 20.19+ or 22.12+
- A free [OpenRouteService](https://openrouteservice.org/dev/#/signup) API key
  (optional: without one the app runs in demo mode with simulated routes)

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # Windows: copy .env.example .env
# edit .env and set ORS_API_KEY
python manage.py runserver 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The development server forwards `/api` requests
to the backend on port 8000.

### Configuration

Backend settings are read from `backend/.env`:

| Variable | Default | Description |
| --- | --- | --- |
| `ORS_API_KEY` | (none) | OpenRouteService key. If empty, routes are simulated (demo mode). |
| `WEATHER_PROVIDER` | `open-meteo` | `open-meteo` for live forecasts, or `simulated` for generated storm fronts (useful for demonstrating risk levels when real weather is calm). |
| `FORECAST_LOCATION_BUDGET` | `300` | Maximum forecast locations fetched per search (see [Free API limits](#free-api-limits)). `0` means no limit. |
| `DJANGO_SECRET_KEY` | (dev key) | Django secret key. Set a random value in production. |
| `DEBUG` | `False` | Django debug mode. |
| `ALLOWED_HOSTS` | `*` | Comma-separated host names. |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated frontend URLs allowed to call the API. |

Frontend: when the API is on a different domain, set `VITE_API_BASE_URL`
(for example `https://my-api.example.com`) before building.

---

## How it works

For each search the backend runs these steps:

1. **Geocode** the origin and destination (Nominatim), unless coordinates were
   given.
2. **Route.** Request truck routes from OpenRouteService (`driving-hgv`
   profile). OpenRouteService only computes alternative routes for trips under
   100 km, so for longer trips the two alternatives are real truck routes
   forced through a point on either side of the direct route. Detours that
   double back are trimmed, near-duplicate routes are dropped, and up to three
   distinct routes are kept.
3. **Place checkpoints** along each route every 10, 25 or 50 miles, plus the
   origin and destination. Automatic spacing uses 10 miles for trips up to
   200 miles, 25 miles up to 600 miles, and 50 miles beyond. Each checkpoint's
   ETA is the departure time plus its share of the route's drive time.
4. **Fetch weather** from [Open-Meteo](https://open-meteo.com/) (hourly
   forecasts, no API key) and read each checkpoint's conditions for the hour
   it is reached: wind in mph, rain and snowfall in inches per hour.
5. **Rate the risk** of each checkpoint (rules below).
6. **Rank the routes** and mark the recommended one.
7. **Build the heatmap**: forecast hazard for a grid of cells covering all
   routes, for every hour from departure to 48 hours later.

### Risk rules

Each checkpoint takes the worst level among wind, rain and snow:

| Condition | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 mph |
| Rain | < 0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

A value on a shared boundary (for example 0.25 in/hr) belongs to the higher
level, except where the table says ">".

Load weight can then raise the level:

- wind ≥ 55 mph: No Travel for any load
- wind 45–54 mph and load > 30,000 lb: No Travel
- wind 35–44 mph and load > 40,000 lb: Severe

**No Travel** means conditions at that point and time are beyond safe limits:
the truck should not drive through.

### Risk miles and recommendation

Each checkpoint represents the stretch of road halfway to its neighbors, so
every mile of a route is counted under exactly one risk level. The average
risk score weights each level by its miles (Low = 1 up to No Travel = 5).

Routes are ranked by:

1. fewest No Travel miles
2. fewest Severe miles
3. fewest High miles
4. lowest average risk score
5. shortest travel time

No Travel is ranked before Severe because it means the road should not be
driven at all. If even the best route crosses No Travel conditions, the app
says so and suggests a later departure.

### Heatmap

The heatmap grid is finer for short trips (about 7 miles per cell) and coarser
for long ones (up to about 140 miles). Its colors use the same scale as the
risk legend. All 49 hourly frames are sent with the search result, so moving
the slider needs no further requests.

### Free API limits

The app is configured for the free plans of its data providers:

- **Open-Meteo** allows 600 locations per minute and 10,000 per day. Each
  search requests at most `FORECAST_LOCATION_BUDGET` locations (300 by
  default). Checkpoints are served first, normally one forecast location per
  checkpoint; the heatmap uses the rest. On very long trips with 10-mile
  spacing, neighboring checkpoints can share a forecast location (each still
  uses its own ETA). Forecasts are cached for one hour and shared between
  searches.
- **OpenRouteService** has a daily request quota. A search uses 3 to 5
  requests, and routes are cached for 24 hours (route geometry and drive
  times do not depend on the time of day).

If a provider is unavailable, the API responds with `503` and a message
asking the user to try again; the cause is written to the server log. With a
paid plan, set `FORECAST_LOCATION_BUDGET=0` for full forecast resolution
everywhere.

### Assumptions and limitations

- ETAs use the routing engine's average speeds and do not include rest breaks
  or traffic.
- Departures must be within the next 7 days (forecast range).
- Wind risk uses sustained wind speed, not gusts.
- Place search suggests United States locations; points picked on the map can
  be anywhere OpenRouteService has road data.

---

## API

### `POST /api/routes/`

Request:

```json
{
  "origin": "Oklahoma City, OK",
  "destination": "Casper, WY",
  "departure_datetime": "2026-11-08T14:00:00Z",
  "load_weight_lbs": 45000,
  "interval_miles": 25
}
```

- `origin` and `destination`: a place name or `"lat,lng"`.
- `interval_miles`: `10`, `25` or `50`; omit or `null` for automatic.
- `load_weight_lbs`: 0 to 100,000.

Response (abridged):

```json
{
  "routes": [
    {
      "name": "Route 1",
      "is_recommended": true,
      "recommendation_reason": "Fewer Severe miles than Route 2 (0 vs 30)",
      "distance_miles": 946.3,
      "travel_time_hours": 18.1,
      "arrival_time": "2026-11-09T08:06:00+00:00",
      "geometry": [[35.47, -97.52], "..."],
      "risk_summary": {
        "low_miles": 916.3, "moderate_miles": 30.0, "high_miles": 0.0,
        "severe_miles": 0.0, "no_travel_miles": 0.0, "average_risk_score": 1.03
      },
      "checkpoints": [
        {
          "mile_marker": 50.0,
          "eta": "2026-11-08T14:57:00+00:00",
          "lat": 36.12, "lng": -97.34,
          "weather": {
            "description": "Light rain", "temperature_f": 54.0,
            "wind_mph": 12.0, "rain_in_hr": 0.04, "snow_in_hr": 0.0
          },
          "risk_level": "Low",
          "risk_reason": "All conditions below Moderate thresholds"
        }
      ]
    }
  ],
  "heatmap": { "start_time": "...", "cell_size_deg": 0.5, "cells": [{ "lat": 36.0, "lng": -97.5, "values": ["...49 hourly values"] }] },
  "sources": { "routing": "openrouteservice", "weather": "open-meteo" }
}
```

Routes are returned safest first. Errors have the form
`{"error": "message", "fields": {...}}`: status `400` for invalid input or an
unknown place, and `503` when no route can be computed (for example, a point
far from any road) or a data provider is unavailable. The message says which.

---

## Project structure

```
backend/
  config/                 Django settings and URLs
  routing/
    views.py              POST /api/routes/
    serializers.py        request validation
    services/
      routing.py          OpenRouteService routes and alternatives
      checkpoints.py      checkpoint placement and ETAs
      weather.py          Open-Meteo forecasts and caching
      risk.py             risk rules and load-weight rules
      recommender.py      risk miles, ranking and explanation
      heatmap.py          corridor grid and hourly frames
    tests/
frontend/
  src/
    App.jsx               page layout and app state
    components/
      RouteForm.jsx       trip form, place search, map picking
      RouteSummary.jsx    route cards and checkpoint list
      MapView.jsx         map, routes, checkpoints, popups, truck marker
      WeatherHeatmap.jsx  heatmap layer
      ForecastSlider.jsx  0–48 h slider and playback
    api/routes.js         API and geocoding calls
    __tests__/
render.yaml               Render deployment (both services)
```

---

## Tests

```bash
cd backend
python -m pytest           # 200 tests

cd frontend
npx vitest run             # 53 tests
```

Backend tests cover the risk thresholds and load rules (including boundary
values), checkpoint placement and ETAs, ranking, routing and forecast handling
with the providers mocked, and the API. Frontend tests cover the form, map
picking, route list, map, forecast playback and the main app flow. No test
calls an external service.

---

## Deployment

`render.yaml` defines both services for [Render](https://render.com)'s free
plan: the API as a web service from `backend/` and the React app as a static
site from `frontend/`.

1. In the Render dashboard choose **New → Blueprint** and select this
   repository.
2. Enter the requested values: `ORS_API_KEY`, `CORS_ALLOWED_ORIGINS` (the
   static site's URL) and `VITE_API_BASE_URL` (the API's URL).
3. After the first deploy, check that both URLs match those values (Render
   adds a suffix when a name is taken) and update them if needed.

For other hosts, run the backend with:

```bash
gunicorn config.wsgi --timeout 90 --workers 2 --threads 4    # from backend/
```

The longer timeout allows for slow searches. The API uses no database, so no
migrations are needed. Build the frontend with `npm run build` and serve
`frontend/dist`.
