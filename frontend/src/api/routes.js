import axios from 'axios';

// Same-origin '/api' in development (Vite proxy); set VITE_API_BASE_URL when
// the frontend and backend are hosted separately.
const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '' });

/**
 * Request routes with weather risk analysis.
 * @param {{origin: string, destination: string, departure_datetime: string,
 *          load_weight_lbs: number, interval_miles: number|null}} request
 */
export async function fetchRoutes(request) {
  try {
    const response = await api.post('/api/routes/', request);
    return response.data;
  } catch (err) {
    const message =
      err.response?.data?.error ||
      (err.response ? `Server error (${err.response.status}).` : 'Cannot reach the routing server.');
    throw new Error(message, { cause: err });
  }
}

/**
 * US place suggestions from Nominatim (OpenStreetMap).
 * @returns {Promise<Array<{label: string, lat: number, lng: number}>>}
 */
export async function searchLocations(query, signal) {
  if (!query || query.trim().length < 3) return [];
  const response = await axios.get('https://nominatim.openstreetmap.org/search', {
    params: { q: query, format: 'json', limit: 5, countrycodes: 'us' },
    headers: { 'Accept-Language': 'en' },
    signal,
  });
  return response.data.map((item) => ({
    label: item.display_name,
    lat: Number(item.lat),
    lng: Number(item.lon),
  }));
}

/**
 * Short place name for a point picked on the map, e.g. "Parker, Colorado".
 * Returns null if nothing is found.
 */
export async function reverseGeocode(lat, lng, signal) {
  const response = await axios.get('https://nominatim.openstreetmap.org/reverse', {
    params: { lat, lon: lng, format: 'json', zoom: 10 },
    headers: { 'Accept-Language': 'en' },
    signal,
  });
  const { address, display_name: fullName } = response.data ?? {};
  if (!address) return fullName ?? null;
  const place = address.city || address.town || address.village || address.hamlet || address.county;
  return [place, address.state].filter(Boolean).join(', ') || fullName || null;
}
