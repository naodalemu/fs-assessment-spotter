const checkpoint = (mile, risk, extra = {}) => ({
  lat: 35 + mile / 100,
  lng: -97 - mile / 100,
  mile_marker: mile,
  eta: new Date(Date.UTC(2026, 10, 8, 14) + mile * 60 * 1000).toISOString(),
  weather: { description: 'Rain', temperature_f: 50, wind_mph: 20, rain_in_hr: 0.12, snow_in_hr: 0, ...extra },
  risk_level: risk,
  risk_score: { Low: 1, Moderate: 2, High: 3, Severe: 4, 'No Travel': 5 }[risk],
  risk_reason: `${risk} reason`,
  factor_levels: { wind: risk, rain: 'Low', snow: 'Low' },
});

const route = (index, rank, overrides = {}) => ({
  name: `Route ${index + 1}`,
  route_index: index,
  rank,
  is_recommended: rank === 1,
  recommendation_reason: rank === 1 ? 'Safest option: fewer Severe miles (0 vs 30 mi) than Route 1.' : null,
  distance_miles: 100,
  travel_time_hours: 2,
  departure_time: '2026-11-08T14:00:00+00:00',
  arrival_time: '2026-11-08T16:00:00+00:00',
  interval_miles: 50,
  geometry: [
    [35, -97],
    [36, -98],
  ],
  checkpoints: [checkpoint(0, 'Low'), checkpoint(50, 'Moderate'), checkpoint(100, 'Low')],
  risk_summary: {
    low_miles: 50,
    moderate_miles: 50,
    high_miles: 0,
    severe_miles: 0,
    no_travel_miles: 0,
    average_risk_score: 1.5,
    max_risk_score: 2,
  },
  ...overrides,
});

export const sampleResponse = {
  routes: [
    route(1, 1),
    route(0, 2, {
      travel_time_hours: 1.5,
      checkpoints: [checkpoint(0, 'Low'), checkpoint(50, 'Severe', { wind_mph: 40 }), checkpoint(100, 'Low')],
      risk_summary: {
        low_miles: 70,
        moderate_miles: 0,
        high_miles: 0,
        severe_miles: 30,
        no_travel_miles: 0,
        average_risk_score: 1.9,
        max_risk_score: 4,
      },
    }),
  ],
  heatmap: {
    start_time: '2026-11-08T14:00:00+00:00',
    hours: 48,
    cell_size_deg: 0.1,
    cells: [{ lat: 35, lng: -97, values: Array.from({ length: 49 }, (_, h) => h / 48) }],
  },
  origin: { query: 'Oklahoma City, OK', lat: 35, lng: -97 },
  destination: { query: 'Wichita, KS', lat: 36, lng: -98 },
  load_weight_lbs: 42000,
  sources: { routing: 'openrouteservice', weather: 'open-meteo' },
};
