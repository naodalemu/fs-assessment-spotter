# Weather-Aware Truck Routing

A React + Django app that helps a truck driver pick the safest route. Given an
origin, destination, departure time and load weight, it:

1. builds **3 real heavy-goods-vehicle routes** (OpenRouteService `driving-hgv`),
2. samples the **hourly forecast** every **10 / 25 / 50 miles** at the truck's
   **ETA** at each checkpoint (Open-Meteo),
3. classifies each checkpoint with the **wind / rain / snow thresholds and load rules**,
4. **recommends** the route with the fewest Severe miles, then High miles, then
   lowest average risk, then shortest time,
5. shows routes, checkpoints, risk levels, ETAs and summaries on a **Leaflet map**
   with a **0–48 h corridor weather heatmap** and forecast slider.

Routes and weather are always real, or, in explicit demo mode, fully
simulated: real and invented data are never mixed. A warning appears above the
results whenever data is simulated. If a live service fails, the user sees
"temporarily unavailable, try again" instead of invented data, and the cause
is logged for the operator.

**No Travel** is a verdict, not a degree of risk: conditions at that point and
time exceed safe limits and the truck should not drive through. If even the
recommended route crosses No Travel conditions, its card says so and suggests
delaying departure.

---

## How each requirement is met

| Requirement | Implementation |
| --- | --- |
| Origin, destination, departure, load | `RouteForm.jsx`, with US place autocomplete (Nominatim), or pick either point by clicking the map (pin button in each field, Esc to cancel). Picked points are named by reverse geocoding, but the exact coordinates are what the backend receives. The backend accepts a place name or `lat,lng`. |
| 3 route options from a routing API | `services/routing.py`. ORS only computes alternatives for trips under 100 km, so for longer trips the alternatives are real HGV routes forced through a via-point either side of the corridor. Requests run in parallel, out-and-back spurs at via-points are cut, and near-duplicates (>85 % shared path) or detours over 1.5× the fastest time are discarded. |
| Sample weather every 10 / 25 / 50 mi at the ETA | `services/checkpoints.py` walks the route polyline. Mile markers are scaled to the road distance, so the last checkpoint is the destination. ETA = departure + mile × (drive time / distance). "Auto" picks 10 / 25 / 50 mi for trips up to 200 / 600 / longer. |
| Weather risk rules | `services/risk.py`: worst of wind, rain and snow, then load modifiers. Each checkpoint also returns a human-readable `risk_reason`. |
| Recommendation | `services/recommender.py`. Ranking key: No Travel miles → Severe miles → High miles → mile-weighted average risk → travel time. No Travel is treated as stricter than Severe, because the road is not drivable at all. The response explains which criterion decided it. |
| Map with routes, checkpoints, risk, ETAs, summaries | `MapView.jsx`: every route drawn (hover for its summary), every checkpoint colored by risk, and popups with ETA, conditions and the reason. Popup rows have icons, each colored by that factor's own risk level. Light and dark basemaps both use full-detail OpenStreetMap tiles; dark mode recolors them with a CSS filter. The sidebar has route cards with a risk-mileage bar and a checkpoint table (click a row to fly to it). |
| Corridor heatmap with a 0–48 h slider | `services/heatmap.py` + `WeatherHeatmap.jsx`: a grid along all routes with 49 hourly values per cell, sent once. Each hour is rendered once into a tiny image that the browser upscales smoothly, and scrubbing crossfades between two stacked images, which is opacity only. A truck marker glides along the selected route to where the truck is at that hour. |

### Risk rules

| Condition | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 mph |
| Rain | < 0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

Load rules: wind ≥ 55 mph → No Travel for any load; 45–54 mph with > 30,000 lb →
No Travel; 35–44 mph with > 40,000 lb → Severe. A shared boundary value
(e.g. 0.25 in/hr) belongs to the higher level, except where the table says ">".

### Mileage attribution

Each checkpoint stands for the road closest to it: from the midpoint with the
previous checkpoint to the midpoint with the next one. Summing those stretches
gives Low / Moderate / High / Severe / No Travel miles that add up to the route
distance.

### Weather data

[Open-Meteo](https://open-meteo.com/) hourly forecasts (no API key). Units are
requested in mph and inches, so the values compare directly against the
thresholds: `rain + showers` and `snowfall` are inches during the hour, and wind
is sustained 10 m wind speed. For a checkpoint ETA, the forecast hour containing
that time is used. Forecasts are fetched in batches of 100 locations for all
unique ~0.1° cells, in parallel, and cached for 30 minutes.

The heatmap grid scales with trip length (0.1° to 2°). It covers each route
plus one cell either side on fine grids, and maps each threshold onto 0.2 /
0.4 / 0.6 / 0.8, so heatmap colors match the risk legend exactly.

### Running on free tiers

This build runs on free API plans, so it is designed to stay inside their
limits without changing what the user sees:

| Service | Free limit | How the app stays within it |
| --- | --- | --- |
| Open-Meteo | 600 locations/minute, 10,000/day | Each search fetches at most `FORECAST_LOCATION_BUDGET` locations (default 300). Checkpoints get first claim, so each one normally has its own ~7 mi forecast; the heatmap uses the rest. Forecasts are cached for an hour in 6-hour blocks, shared across all users. |
| OpenRouteService | daily request quota | Each search uses 3 to 5 requests, and results are cached for 24 hours, so repeated trips cost nothing. |

If a limit is still hit, the API returns `503` with a neutral "temporarily
unavailable" message, never invented data, and the specific cause (quota, rate
limit, invalid key) is logged server-side.

On a paid plan, set `FORECAST_LOCATION_BUDGET=0`. The same code then gives
every checkpoint and heatmap cell full resolution. The only case the budget
visibly coarsens today is 10-mile sampling on a cross-country trip, where
neighbouring checkpoints share a forecast cell (each still at its own ETA).

### Smoothness

The map always fills the window, and the header and side panel slide over it
using only `transform` and `opacity`. The map therefore never resizes or
redraws during the transition. Route layers and the side panel are memoized,
so moving the forecast slider re-renders only the heatmap and truck marker.
Measured in Chrome: entering or leaving full map, playback and rapid scrubbing
all hold 60 fps.

### Assumptions and limits

- ETAs assume the routing engine's average speed and no rest breaks.
- Forecasts are limited to departures within the next 7 days.
- Wind risk uses sustained wind, not gusts.

---

## Architecture

```
frontend/ (React 19, Vite, MUI, react-leaflet)
  App.jsx                 layout: full-screen map with a header, side panel and
                          toolbar (heatmap, basemap, full map / F) layered on top
  components/RouteForm    inputs + validation + autocomplete
  components/RouteSummary route cards, risk bars, checkpoint table
  components/MapView      routes, checkpoints, popups, truck marker
  components/WeatherHeatmap  per-hour heat images with crossfade
  components/ForecastSlider  0–48 h scrubber with play button + legend

backend/ (Django 5, DRF)
  routing/views.py        POST /api/routes/
  routing/services/
    routing.py            ORS HGV routes, via-point alternatives, demo routes
    checkpoints.py        distance sampling + ETAs
    weather.py            Open-Meteo batching, cache, demo weather
    risk.py               thresholds + load rules
    recommender.py        risk mileage + ranking + explanation
    heatmap.py            corridor grid, 49 hourly frames
```

### API

`POST /api/routes/`

```json
{
  "origin": "Oklahoma City, OK",
  "destination": "Casper, WY",
  "departure_datetime": "2026-11-08T14:00:00Z",
  "load_weight_lbs": 45000,
  "interval_miles": 25
}
```

`interval_miles` is 10, 25 or 50; omit it or send `null` for Auto. The response
contains `routes` (safest first, each with `checkpoints`, `risk_summary`,
`is_recommended` and `recommendation_reason`), `heatmap`, `origin`,
`destination` and `sources`. Errors are returned as `{"error": "...", "fields": {...}}`.

---

## Running locally

Requirements: Python 3.11+, Node 18+.

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # then set ORS_API_KEY
python manage.py runserver 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api to :8000)
```

### Environment variables (`backend/.env`)

| Variable | Purpose |
| --- | --- |
| `ORS_API_KEY` | OpenRouteService key ([free signup](https://openrouteservice.org/dev/#/signup)). Without it the app runs in demo mode with simulated routes, labelled as such. Use a separate key for the hosted deployment so local testing can't use up its quota. |
| `WEATHER_PROVIDER` | `open-meteo` (default, live) or `simulated`: deterministic moving storm fronts. Useful for demos when real weather is calm. |
| `FORECAST_LOCATION_BUDGET` | Forecast locations per search (default `300`, fits Open-Meteo's free tier). `0` removes the limit for a paid plan. |
| `DJANGO_SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` | Standard Django settings. |
| `CORS_ALLOWED_ORIGINS` | Comma-separated frontend origins (needed when hosted separately). |

Frontend: set `VITE_API_BASE_URL` (e.g. `https://your-api.example.com`) when
the API is on a different origin.

## Tests

```bash
cd backend && .venv\Scripts\python -m pytest     # 197 tests: risk boundaries, load rules, sampling,
                                                 # ranking, ORS/Open-Meteo integration (mocked), API
cd frontend && npx vitest run                    # 49 tests: form validation, map picking, route list, map, app flow
```

No test calls external services.

## Deployment

- **Backend**: any Python host (Render, Railway, Fly.io). Start command:
  `gunicorn config.wsgi --chdir backend --timeout 90 --workers 2 --threads 4`.
  The longer timeout matters: a cold search (several routing calls plus
  forecasts) can exceed gunicorn's 30-second default. Set `ORS_API_KEY` (a
  key used only by this deployment), `DJANGO_SECRET_KEY`, `DEBUG=False`,
  `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` (the frontend URL). No database
  or migrations are needed.
- **Frontend**: `npm run build` in `frontend/` and serve `dist/` (Vercel,
  Netlify). Set `VITE_API_BASE_URL` to the backend URL at build time.
