// Risk levels in increasing severity. `key` matches the API's `risk_level`.
export const RISK_LEVELS = [
  { key: 'Low', field: 'low_miles', color: '#22c55e' },
  { key: 'Moderate', field: 'moderate_miles', color: '#eab308' },
  { key: 'High', field: 'high_miles', color: '#f97316' },
  { key: 'Severe', field: 'severe_miles', color: '#ef4444' },
  { key: 'No Travel', field: 'no_travel_miles', color: '#a855f7' },
];

export const RISK_COLOR = Object.fromEntries(RISK_LEVELS.map((l) => [l.key, l.color]));

/** Headline for a checkpoint: "No Travel" is a verdict, not a degree of risk. */
export function riskHeadline(level) {
  return level === 'No Travel' ? 'No Travel: do not drive' : `${level} risk`;
}

// Route identity colours (list swatch + map line). Chosen to stay distinct
// from the risk colours above.
export const ROUTE_COLORS = ['#22d3ee', '#3b82f6', '#cbd5e1'];

export const SAMPLING_OPTIONS = [
  { value: 'auto', label: 'Auto', hint: '10, 25 or 50 mi depending on trip length' },
  { value: 10, label: '10 mi' },
  { value: 25, label: '25 mi' },
  { value: 50, label: '50 mi' },
];

export const FORECAST_HOURS = 48;

/**
 * Heatmap intensity (0–1) to risk band. The backend maps every threshold
 * of the risk table onto 0.2 / 0.4 / 0.6 / 0.8, so the bands are exact.
 */
export function intensityToRisk(value) {
  // epsilon guards float error at exact thresholds (0.6 / 0.2 = 2.999…)
  const index = Math.min(Math.floor(value / 0.2 + 1e-9), RISK_LEVELS.length - 1);
  return RISK_LEVELS[Math.max(index, 0)];
}

/** Fill opacity grows with intensity so calm cells only lightly tint the corridor. */
export function heatmapCellStyle(value) {
  return {
    fillColor: intensityToRisk(value).color,
    fillOpacity: 0.12 + 0.5 * Math.min(value / 0.8, 1),
  };
}

/**
 * Users only need to hear about data sources in demo mode, where routes or
 * weather are simulated on purpose. Returns that notice, or null.
 */
export function simulatedDataNotice(sources) {
  if (!sources) return null;
  const parts = [];
  if (sources.routing !== 'openrouteservice') parts.push('routes are simulated');
  if (sources.weather === 'simulated') parts.push('weather is simulated, not a real forecast');
  return parts.length ? `Demo mode: ${parts.join(' and ')}.` : null;
}
