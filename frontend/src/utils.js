const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});

const timeFormat = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });
const dayTimeFormat = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' });

export function formatDateTime(value) {
  return dateTimeFormat.format(new Date(value));
}

/** "Sun 7:40 PM": enough within the 7-day planning window. */
export function formatDayTime(value) {
  return dayTimeFormat.format(new Date(value));
}

export function formatTime(value) {
  return timeFormat.format(new Date(value));
}

export function formatDuration(hours) {
  const totalMinutes = Math.round(hours * 60);
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  return h > 0 ? `${h} h ${String(m).padStart(2, '0')} min` : `${m} min`;
}

export function formatMiles(miles) {
  return `${Math.round(miles).toLocaleString()} mi`;
}

/** `datetime-local` input value for a Date, in local time. */
export function toLocalInputValue(date) {
  const pad = (n) => String(n).padStart(2, '0');
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

/** Now, rounded up to the next quarter hour. */
export function nextQuarterHour(now = new Date()) {
  const d = new Date(now);
  d.setSeconds(0, 0);
  d.setMinutes(Math.ceil((d.getMinutes() + 1) / 15) * 15);
  return d;
}

function distanceMiles([lat1, lng1], [lat2, lng2]) {
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 3958.8 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/** Point at `fraction` (0–1) of the way along a [lat, lng] polyline. */
export function pointAlongLine(geometry, fraction) {
  if (!geometry?.length) return null;
  if (fraction <= 0 || geometry.length === 1) return geometry[0];
  const segments = geometry.slice(1).map((pt, i) => distanceMiles(geometry[i], pt));
  let remaining = segments.reduce((sum, d) => sum + d, 0) * Math.min(fraction, 1);
  for (let i = 0; i < segments.length; i += 1) {
    if (remaining <= segments[i]) {
      const f = segments[i] > 0 ? remaining / segments[i] : 0;
      const [lat1, lng1] = geometry[i];
      const [lat2, lng2] = geometry[i + 1];
      return [lat1 + f * (lat2 - lat1), lng1 + f * (lng2 - lng1)];
    }
    remaining -= segments[i];
  }
  return geometry[geometry.length - 1];
}
