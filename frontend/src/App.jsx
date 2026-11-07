import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  FormControlLabel,
  Switch,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import {
  Fullscreen as FullscreenIcon,
  FullscreenExit as FullscreenExitIcon,
  LocalShipping as TruckIcon,
} from '@mui/icons-material';
import RouteForm from './components/RouteForm.jsx';
import RouteSummary from './components/RouteSummary.jsx';
import MapView from './components/MapView.jsx';
import { fetchRoutes, reverseGeocode } from './api/routes.js';
import { simulatedDataNotice } from './constants.js';

const BASEMAP_KEY = 'basemap';
const darkQuery = () => window.matchMedia?.('(prefers-color-scheme: dark)');

function readSavedBasemap() {
  try {
    const saved = localStorage.getItem(BASEMAP_KEY);
    return saved === 'dark' || saved === 'light' ? saved : null;
  } catch {
    return null; // storage blocked (private mode, browser settings)
  }
}

/**
 * Map theme like other map apps: follow the device's light/dark setting until
 * the user picks one, then remember that choice across reloads.
 */
function useBasemap() {
  const [basemap, setBasemap] = useState(
    () => readSavedBasemap() ?? (darkQuery()?.matches === false ? 'light' : 'dark')
  );

  useEffect(() => {
    const query = darkQuery();
    if (!query || readSavedBasemap()) return undefined;
    const follow = (e) => {
      if (!readSavedBasemap()) setBasemap(e.matches ? 'dark' : 'light');
    };
    query.addEventListener('change', follow);
    return () => query.removeEventListener('change', follow);
  }, []);

  const choose = useCallback((value) => {
    setBasemap(value);
    try {
      localStorage.setItem(BASEMAP_KEY, value);
    } catch {
      // not saved; the choice still applies for this visit
    }
  }, []);

  return [basemap, choose];
}

const HEADER_HEIGHT = 56;
const EMPTY_PLACE = { text: '', coords: null };
const PANEL_WIDTH = 420;
// Only transform and opacity are animated: they run on the GPU compositor, and
// the map underneath never changes size, so nothing has to re-layout or redraw.
const SLIDE = 'transform 320ms cubic-bezier(0.4, 0, 0.2, 1), opacity 320ms cubic-bezier(0.4, 0, 0.2, 1)';

/**
 * Heatmap switch, basemap toggle and full-map button. They sit in the header's
 * top-right corner and stay exactly where they are when the header slides away.
 */
function MapToolbar({ fullMap, onFullMap, heatmapVisible, onHeatmapVisible, basemap, onBasemap }) {
  return (
    <Box
      sx={{
        position: 'absolute',
        top: 8,
        right: 12,
        height: 40,
        zIndex: 1300,
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        px: 1,
        borderRadius: 2,
        // Gains a backdrop only once the header behind it is gone
        bgcolor: fullMap ? 'rgba(13, 17, 22, 0.9)' : 'transparent',
        boxShadow: fullMap ? 6 : 0,
        transition: 'background-color 320ms, box-shadow 320ms',
      }}
    >
      <FormControlLabel
        sx={{ m: 0, gap: 0.5 }}
        labelPlacement="start"
        label={
          <Typography variant="body2" sx={{ display: { xs: 'none', sm: 'block' } }}>
            Heatmap
          </Typography>
        }
        control={
          <Switch
            size="small"
            checked={heatmapVisible}
            onChange={(e) => onHeatmapVisible(e.target.checked)}
            slotProps={{ input: { 'aria-label': 'Heatmap' } }}
          />
        }
      />
      <ToggleButtonGroup
        value={basemap}
        exclusive
        size="small"
        onChange={(_, v) => v && onBasemap(v)}
        aria-label="Basemap"
        sx={{ '& .MuiToggleButton-root': { py: 0.25, px: 1.25 } }}
      >
        <ToggleButton value="dark">Dark</ToggleButton>
        <ToggleButton value="light">Light</ToggleButton>
      </ToggleButtonGroup>
      <Tooltip title={fullMap ? 'Exit full map (F)' : 'Full map (F)'}>
        <Button
          size="small"
          variant={fullMap ? 'contained' : 'outlined'}
          onClick={onFullMap}
          aria-label={fullMap ? 'Exit full map' : 'Full map'}
          startIcon={fullMap ? <FullscreenExitIcon /> : <FullscreenIcon />}
          sx={{ minWidth: 0, whiteSpace: 'nowrap', '& .MuiButton-startIcon': { mr: { xs: 0, md: 1 } } }}
        >
          <Box component="span" sx={{ display: { xs: 'none', md: 'inline' } }}>
            {fullMap ? 'Exit full map' : 'Full map'}
          </Box>
        </Button>
      </Tooltip>
    </Box>
  );
}

function App() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [forecastHour, setForecastHour] = useState(0);
  const [focus, setFocus] = useState(null);
  const [fullMap, setFullMap] = useState(false);
  const [origin, setOrigin] = useState(EMPTY_PLACE);
  const [destination, setDestination] = useState(EMPTY_PLACE);
  const [picking, setPicking] = useState(null); // 'origin' | 'destination' | null
  const [basemap, setBasemap] = useBasemap();
  const [heatmapVisible, setHeatmapVisible] = useState(true);

  // "F" toggles the full-map view (ignored while typing); Esc cancels map picking
  useEffect(() => {
    const onKeyDown = (e) => {
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName) || e.target.isContentEditable;
      if (e.key === 'Escape') setPicking(null);
      if (!typing && e.key.toLowerCase() === 'f' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        setFullMap((v) => !v);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const handleSubmit = useCallback(async (request) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchRoutes(request);
      setData(result);
      setSelectedIndex(0); // routes arrive safest-first
      setForecastHour(0);
      setFocus(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSelect = useCallback((index) => {
    setSelectedIndex(index);
    setFocus(null);
  }, []);

  const handleCheckpointClick = useCallback((index) => setFocus({ index }), []);

  const handlePick = useCallback((field) => setPicking((current) => (current === field ? null : field)), []);

  // A map click fills the field with the exact point right away, then swaps in
  // a readable place name once the reverse lookup answers. The coordinates are
  // what get sent to the backend either way.
  const handleMapPick = useCallback(async (field, lat, lng) => {
    const setPlace = field === 'origin' ? setOrigin : setDestination;
    const coords = [Number(lat.toFixed(5)), Number(lng.toFixed(5))];
    setPlace({ text: `${coords[0]}, ${coords[1]}`, coords });
    setPicking(null);
    try {
      const name = await reverseGeocode(coords[0], coords[1]);
      if (name) setPlace((current) => (current.coords === coords ? { text: name, coords } : current));
    } catch {
      // keep showing the coordinates
    }
  }, []);

  const pickedPlaces = useMemo(
    () => ({ origin: origin.coords, destination: destination.coords }),
    [origin.coords, destination.coords]
  );

  // On phones the panel covers the top of the map, so it steps aside while picking
  const panelHidden = fullMap || (isMobile && picking !== null);

  // Screen area covered by the header and panel, so the map can frame routes
  // and checkpoints in the part of the map that is actually visible.
  const insets = useMemo(() => {
    if (panelHidden) return { top: 56, left: 0 }; // keep clear of the floating toolbar
    if (isMobile) return { top: HEADER_HEIGHT + Math.round(window.innerHeight * 0.45), left: 0 };
    return { top: HEADER_HEIGHT, left: PANEL_WIDTH };
  }, [panelHidden, isMobile]);

  return (
    <Box sx={{ position: 'relative', height: '100dvh', overflow: 'hidden', bgcolor: 'background.default' }}>
      <Box component="main" sx={{ position: 'absolute', inset: 0 }}>
        <MapView
          data={data}
          selectedIndex={selectedIndex}
          onSelect={handleSelect}
          focus={focus}
          loading={loading}
          hour={forecastHour}
          onHourChange={setForecastHour}
          basemap={basemap}
          heatmapVisible={heatmapVisible}
          insets={insets}
          picking={picking}
          onMapPick={handleMapPick}
          pickedPlaces={pickedPlaces}
        />
      </Box>

      <Box
        component="header"
        inert={fullMap}
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: HEADER_HEIGHT,
          zIndex: 1200,
          px: { xs: 2, md: 3 },
          pr: { xs: '220px', md: '420px' }, // room for the toolbar
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          bgcolor: 'secondary.main',
          borderBottom: 1,
          borderColor: 'divider',
          transform: fullMap ? `translateY(-${HEADER_HEIGHT + 1}px)` : 'none',
          transition: SLIDE,
          willChange: 'transform',
        }}
      >
        <TruckIcon sx={{ color: 'primary.main' }} />
        <Typography component="h1" noWrap sx={{ fontWeight: 700, fontSize: { xs: '1rem', sm: '1.1rem' } }}>
          Weather-Aware Truck Routing
        </Typography>
      </Box>

      <MapToolbar
        fullMap={fullMap}
        onFullMap={() => setFullMap((v) => !v)}
        heatmapVisible={heatmapVisible}
        onHeatmapVisible={setHeatmapVisible}
        basemap={basemap}
        onBasemap={setBasemap}
      />

      {/* Slides out rather than unmounting, so the form keeps its values */}
      <Box
        component="aside"
        inert={panelHidden}
        sx={{
          position: 'absolute',
          top: HEADER_HEIGHT,
          left: 0,
          zIndex: 1150,
          width: isMobile ? '100%' : PANEL_WIDTH,
          ...(isMobile ? { height: '45%' } : { bottom: 0 }),
          overflowY: 'auto',
          bgcolor: 'background.default',
          borderRight: isMobile ? 0 : 1,
          borderBottom: isMobile ? 1 : 0,
          borderColor: 'divider',
          boxShadow: panelHidden ? 0 : 8,
          transform: panelHidden ? (isMobile ? 'translateY(-110%)' : 'translateX(-101%)') : 'none',
          opacity: panelHidden ? 0 : 1,
          transition: SLIDE,
          willChange: 'transform',
        }}
      >
        <RouteForm
          onSubmit={handleSubmit}
          loading={loading}
          error={error}
          origin={origin}
          destination={destination}
          onOriginChange={setOrigin}
          onDestinationChange={setDestination}
          picking={picking}
          onPick={handlePick}
        />
        {simulatedDataNotice(data?.sources) && (
          <Alert severity="warning" sx={{ mx: 2.5, mb: 2 }}>
            {simulatedDataNotice(data.sources)}
          </Alert>
        )}
        {data && (
          <RouteSummary
            key={data.routes.map((r) => r.distance_miles).join()}
            routes={data.routes}
            selectedIndex={selectedIndex}
            onSelect={handleSelect}
            onCheckpointClick={handleCheckpointClick}
          />
        )}
      </Box>
    </Box>
  );
}

export default App;
