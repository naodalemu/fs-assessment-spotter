import { Fragment, memo, useEffect, useMemo, useRef } from 'react';
import {
  CircleMarker,
  MapContainer,
  Polyline,
  Popup,
  TileLayer,
  Tooltip,
  ZoomControl,
  useMap,
  useMapEvents,
} from 'react-leaflet';
import L from 'leaflet';
import { Box, CircularProgress, Fade, Typography } from '@mui/material';
import {
  AcUnit as SnowIcon,
  Air as WindIcon,
  Schedule as EtaIcon,
  Thermostat as TempIcon,
  WaterDrop as RainIcon,
} from '@mui/icons-material';
import WeatherHeatmap from './WeatherHeatmap.jsx';
import WeatherIcon from './WeatherIcon.jsx';
import ForecastSlider from './ForecastSlider.jsx';
import { RISK_COLOR, ROUTE_COLORS, riskHeadline } from '../constants.js';
import { formatDateTime, formatDuration, formatMiles, pointAlongLine } from '../utils.js';

// Both themes use the full-detail OpenStreetMap tiles (roads, parks, water,
// place names). Dark mode recolours them with a CSS filter on the tile layer
// only (see .basemap-dark in index.css), so routes and the heatmap keep
// their true colours. No API key needed.
const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const US_CENTER = [39.5, -98.35];
const MARGIN = 48;
const SLIDER_CLEARANCE = 150; // forecast panel at the bottom of the map
const NO_INSETS = { top: 0, left: 0 };

// Style objects are module constants (or rebuilt only when inputs change):
// react-leaflet restyles a layer whenever it receives a *new* pathOptions
// object, and every restyle redraws the whole canvas.
const TRUCK_STYLE = { color: '#5fdede', weight: 4, fillColor: '#0d1116', fillOpacity: 1 };
const CASING_SELECTED = { color: '#0d1116', weight: 10, opacity: 0.55 };
const CASING_OTHER = { color: '#0d1116', weight: 7, opacity: 0.6 };
const ORIGIN_STYLE = { color: '#0d1116', weight: 3, fillColor: '#ffffff', fillOpacity: 1 };
const DESTINATION_STYLE = { color: '#ffffff', weight: 3, fillColor: '#0d1116', fillOpacity: 1 };
const lineStyle = (color, selected) => ({ color, weight: selected ? 6 : 4, opacity: selected ? 1 : 0.85 });
const dotStyle = (risk, selected) =>
  selected
    ? { color: '#ffffff', weight: 2, fillColor: RISK_COLOR[risk], fillOpacity: 1 }
    : { color: '#0d1116', weight: 1, fillColor: RISK_COLOR[risk], fillOpacity: 0.8 };

/**
 * Fly to frame all routes whenever a new result arrives, inside the part of
 * the map not covered by the header, side panel or forecast slider.
 */
function FitToRoutes({ routes, insets }) {
  const map = useMap();
  const insetsRef = useRef(insets);
  useEffect(() => {
    insetsRef.current = insets;
  });
  useEffect(() => {
    const points = routes.flatMap((r) => r.geometry);
    if (!points.length) return;
    const { top, left } = insetsRef.current;
    map.flyToBounds(L.latLngBounds(points), {
      paddingTopLeft: [left + MARGIN, top + MARGIN],
      paddingBottomRight: [MARGIN, SLIDER_CLEARANCE],
      duration: 1.1,
    });
  }, [routes, map]); // re-frame for new results only, not when panels open or close
  return null;
}

/** While picking, a map click sets the origin or destination. */
function PickOnClick({ picking, onMapPick }) {
  useMapEvents({
    click: (e) => {
      if (picking) onMapPick(picking, e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

const samePoint = (a, b) => Boolean(a && b) && Math.abs(a[0] - b.lat) < 1e-4 && Math.abs(a[1] - b.lng) < 1e-4;

/** Pins for points picked on the map that haven't been routed yet. */
function PickedPins({ places, data }) {
  return [
    ['origin', 'Origin', ORIGIN_STYLE],
    ['destination', 'Destination', DESTINATION_STYLE],
  ].map(([field, label, style]) => {
    const coords = places?.[field];
    if (!coords || samePoint(coords, data?.[field])) return null;
    return (
      <CircleMarker key={field} center={coords} radius={9} pathOptions={style}>
        <Tooltip permanent direction="top" offset={[0, -8]}>
          {label}
        </Tooltip>
      </CircleMarker>
    );
  });
}

/** Keep Leaflet's size in sync with the window. */
function SizeObserver() {
  const map = useMap();
  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(() => map.invalidateSize({ pan: false }));
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);
  return null;
}

/**
 * Fly to a checkpoint chosen in the sidebar table and open its popup. The
 * target is offset so the checkpoint lands in the middle of the visible area.
 */
function FocusCheckpoint({ focus, markers, insets }) {
  const map = useMap();
  const insetsRef = useRef(insets);
  useEffect(() => {
    insetsRef.current = insets;
  });
  useEffect(() => {
    if (!focus) return;
    const marker = markers.current[focus.index];
    if (!marker) return;
    const zoom = Math.max(map.getZoom(), 8);
    const { top, left } = insetsRef.current;
    const center = map.unproject(map.project(marker.getLatLng(), zoom).subtract([left / 2, top / 2]), zoom);
    map.once('moveend', () => marker.openPopup());
    map.flyTo(center, zoom, { duration: 0.9 });
  }, [focus, map, markers]);
  return null;
}

/**
 * Truck position at the forecast hour on the selected route. The marker is
 * moved with setLatLng in an animation-frame loop, so the glide between hours
 * never re-renders any React component.
 */
function TruckMarker({ route, hour }) {
  const markerRef = useRef(null);
  const fraction = hour / route.travel_time_hours;
  const target = useMemo(() => pointAlongLine(route.geometry, fraction), [route, fraction]);
  const start = useMemo(() => pointAlongLine(route.geometry, 0), [route]);
  const label =
    fraction >= 1 ? 'Arrived' : `Truck at +${hour} h · mile ${Math.round(fraction * route.distance_miles)}`;

  useEffect(() => {
    const marker = markerRef.current;
    if (!marker || !target) return undefined;
    const from = marker.getLatLng();
    const begin = performance.now();
    let frame;
    const step = (now) => {
      const t = Math.min((now - begin) / 300, 1);
      const e = 1 - (1 - t) ** 3; // ease-out
      marker.setLatLng([from.lat + (target[0] - from.lat) * e, from.lng + (target[1] - from.lng) * e]);
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target]);

  if (!start) return null;
  return (
    <CircleMarker ref={markerRef} center={start} radius={8} interactive={false} pathOptions={TRUCK_STYLE}>
      <Tooltip permanent direction="auto" offset={[10, 0]}>
        {label}
      </Tooltip>
    </CircleMarker>
  );
}

function PopupRow({ icon: Icon, iconColor, label, children }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.35 }}>
      <Icon sx={{ fontSize: 18, color: iconColor ?? 'text.secondary', flexShrink: 0 }} />
      <Typography variant="body2" color="text.secondary" sx={{ width: 44, flexShrink: 0 }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        {children}
      </Typography>
    </Box>
  );
}

function CheckpointPopup({ checkpoint: cp, routeName }) {
  const w = cp.weather;
  const color = RISK_COLOR[cp.risk_level];
  // Each factor's icon takes the colour of that factor's own risk level,
  // so the culprit stands out at a glance.
  const factorColor = (factor) => RISK_COLOR[cp.factor_levels?.[factor]];
  return (
    <Box sx={{ minWidth: 230 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, pr: 2.5 }}>
        <Box
          sx={{
            width: 40,
            height: 40,
            borderRadius: 2,
            display: 'grid',
            placeItems: 'center',
            bgcolor: `${color}26`,
            border: `1px solid ${color}`,
            flexShrink: 0,
          }}
        >
          <WeatherIcon description={w.description} sx={{ color }} />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 800, color, lineHeight: 1.2 }}>
            {riskHeadline(cp.risk_level)}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {routeName} · mile {Math.round(cp.mile_marker)}
          </Typography>
        </Box>
      </Box>
      <Typography variant="caption" sx={{ display: 'block', mt: 1, mb: 0.75, px: 1, py: 0.5, borderRadius: 1, bgcolor: 'action.hover' }}>
        {cp.risk_reason}
      </Typography>
      <PopupRow icon={EtaIcon} label="ETA">{formatDateTime(cp.eta)}</PopupRow>
      <PopupRow icon={(props) => <WeatherIcon description={w.description} {...props} />} label="Sky">
        {w.description}
      </PopupRow>
      <PopupRow icon={WindIcon} iconColor={factorColor('wind')} label="Wind">
        {Math.round(w.wind_mph)} mph
      </PopupRow>
      <PopupRow icon={RainIcon} iconColor={factorColor('rain')} label="Rain">
        {w.rain_in_hr.toFixed(2)} in/h
      </PopupRow>
      <PopupRow icon={SnowIcon} iconColor={factorColor('snow')} label="Snow">
        {w.snow_in_hr.toFixed(2)} in/h
      </PopupRow>
      <PopupRow icon={TempIcon} label="Temp">{Math.round(w.temperature_f)}°F</PopupRow>
    </Box>
  );
}

function routeTooltip(route) {
  const s = route.risk_summary;
  return (
    `${route.name}${route.is_recommended ? ' (recommended)' : ''} · ` +
    `${formatMiles(route.distance_miles)} · ${formatDuration(route.travel_time_hours)} · ` +
    `Severe+ ${formatMiles(s.severe_miles + s.no_travel_miles)}, High ${formatMiles(s.high_miles)}`
  );
}

/**
 * Routes, checkpoints and endpoints. Memoised so moving the forecast slider
 * (which re-renders the map) never touches these layers.
 */
const RouteLayers = memo(function RouteLayers({ data, selectedIndex, onSelect, markers, popupPadding }) {
  const routes = data.routes;
  const selected = routes[selectedIndex];
  // Draw unselected routes first so the selected one is on top
  const drawOrder = routes
    .map((route, index) => ({ route, index }))
    .sort((a, b) => (a.index === selectedIndex) - (b.index === selectedIndex));

  return (
    <>
      {drawOrder.map(({ route, index }) => {
        const isSelected = index === selectedIndex;
        const color = ROUTE_COLORS[route.route_index % ROUTE_COLORS.length];
        const select = { click: () => onSelect(index) };
        return (
          <Fragment key={`${route.route_index}-${isSelected}`}>
            {/* Dark casing keeps every route visible on both light and dark basemaps */}
            <Polyline
              positions={route.geometry}
              pathOptions={isSelected ? CASING_SELECTED : CASING_OTHER}
              interactive={false}
            />
            <Polyline positions={route.geometry} pathOptions={lineStyle(color, isSelected)} eventHandlers={select}>
              <Tooltip sticky>{routeTooltip(route)}</Tooltip>
            </Polyline>
            {!isSelected &&
              route.checkpoints.map((cp) => (
                <CircleMarker
                  key={cp.mile_marker}
                  center={[cp.lat, cp.lng]}
                  radius={3.5}
                  pathOptions={dotStyle(cp.risk_level, false)}
                  eventHandlers={select}
                />
              ))}
          </Fragment>
        );
      })}

      {selected.checkpoints.map((cp, i) => (
        <CircleMarker
          key={`${selected.route_index}-${cp.mile_marker}`}
          ref={(el) => {
            markers.current[i] = el;
          }}
          center={[cp.lat, cp.lng]}
          radius={6.5}
          pathOptions={dotStyle(cp.risk_level, true)}
        >
          {/* Popup options are fixed at creation, so re-create popups when the padding changes */}
          <Popup key={popupPadding.join()} autoPanPaddingTopLeft={popupPadding} autoPanPadding={[16, 16]}>
            <CheckpointPopup checkpoint={cp} routeName={selected.name} />
          </Popup>
        </CircleMarker>
      ))}

      <CircleMarker center={[data.origin.lat, data.origin.lng]} radius={9} pathOptions={ORIGIN_STYLE}>
        <Tooltip direction="top" offset={[0, -8]}>Origin: {data.origin.query}</Tooltip>
      </CircleMarker>
      <CircleMarker center={[data.destination.lat, data.destination.lng]} radius={9} pathOptions={DESTINATION_STYLE}>
        <Tooltip direction="top" offset={[0, -8]}>Destination: {data.destination.query}</Tooltip>
      </CircleMarker>
    </>
  );
});

function MapView({
  data,
  selectedIndex,
  onSelect,
  focus,
  loading,
  hour,
  onHourChange,
  basemap = 'dark',
  heatmapVisible = true,
  insets = NO_INSETS,
  picking = null,
  onMapPick,
  pickedPlaces,
}) {
  const markers = useRef([]);
  const selected = data?.routes[selectedIndex];
  // When a popup opens, Leaflet pans it into view; keep it clear of the header
  // and side panel, which cover part of the map.
  const popupPadding = useMemo(() => [insets.left + 16, insets.top + 16], [insets.left, insets.top]);
  // Centre floating overlays (slider, messages) in the visible part of the map,
  // moved with a GPU transform alongside the side panel.
  const shift = {
    transform: `translateX(${insets.left / 2}px)`,
    transition: 'transform 320ms cubic-bezier(0.4, 0, 0.2, 1)',
  };

  return (
    <Box
      className={`basemap-${basemap}-bg${picking ? ' picking' : ''}`}
      sx={{ position: 'relative', height: '100%', width: '100%' }}
    >
      <MapContainer
        center={US_CENTER}
        zoom={4}
        maxZoom={19}
        zoomControl={false}
        preferCanvas
        style={{ height: '100%', width: '100%' }}
      >
        <TileLayer
          key={basemap}
          url={TILE_URL}
          attribution={ATTRIBUTION}
          maxZoom={19}
          className={basemap === 'dark' ? 'basemap-dark' : undefined}
        />
        <ZoomControl position="bottomright" />
        <SizeObserver />
        {data && <FitToRoutes routes={data.routes} insets={insets} />}
        <FocusCheckpoint focus={focus} markers={markers} insets={insets} />
        <WeatherHeatmap heatmap={data?.heatmap} hour={hour} visible={heatmapVisible} />
        {data && (
          <RouteLayers
            data={data}
            selectedIndex={selectedIndex}
            onSelect={onSelect}
            markers={markers}
            popupPadding={popupPadding}
          />
        )}
        {selected && <TruckMarker key={selected.route_index} route={selected} hour={hour} />}
        <PickedPins places={pickedPlaces} data={data} />
        {onMapPick && <PickOnClick picking={picking} onMapPick={onMapPick} />}
      </MapContainer>

      <Fade in={Boolean(picking)} unmountOnExit>
        <Box
          role="status"
          sx={{
            position: 'absolute',
            top: insets.top + 16,
            left: 0,
            right: 0,
            zIndex: 1000,
            display: 'flex',
            justifyContent: 'center',
            pointerEvents: 'none',
            ...shift,
          }}
        >
          <Typography
            variant="body2"
            sx={{ bgcolor: 'primary.main', color: 'primary.contrastText', fontWeight: 600, px: 2, py: 0.75, borderRadius: 5, boxShadow: 6 }}
          >
            Click the map to set the {picking ?? 'origin'} · Esc to cancel
          </Typography>
        </Box>
      </Fade>

      {data?.heatmap && (
        <Box sx={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 0, zIndex: 1000, ...shift }}>
          <ForecastSlider hour={hour} onChange={onHourChange} startTime={data.heatmap.start_time} />
        </Box>
      )}

      {!data && !loading && !picking && !pickedPlaces?.origin && !pickedPlaces?.destination && (
        <Box
          sx={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', pointerEvents: 'none', zIndex: 900, ...shift }}
        >
          <Typography sx={{ bgcolor: 'rgba(13, 17, 22, 0.85)', px: 2, py: 1, borderRadius: 2 }} color="text.secondary">
            Enter a trip to compare routes and corridor weather.
          </Typography>
        </Box>
      )}

      <Fade in={loading} unmountOnExit>
        <Box
          role="status"
          sx={{ position: 'absolute', inset: 0, zIndex: 1100, display: 'grid', placeItems: 'center', bgcolor: 'rgba(13, 17, 22, 0.55)' }}
        >
          <Box
            sx={{ display: 'flex', alignItems: 'center', gap: 1.5, bgcolor: 'background.paper', px: 2.5, py: 1.5, borderRadius: 2, boxShadow: 8, ...shift }}
          >
            <CircularProgress size={20} />
            <Typography variant="body2">Routing and fetching forecasts…</Typography>
          </Box>
        </Box>
      </Fade>
    </Box>
  );
}

export default MapView;
