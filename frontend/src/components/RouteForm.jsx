import { memo, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  CircularProgress,
  IconButton,
  InputAdornment,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  CalendarMonth as CalendarIcon,
  Flag as DestinationIcon,
  MyLocation as OriginIcon,
  PinDrop as PickIcon,
  Scale as WeightIcon,
  Search as SearchIcon,
} from '@mui/icons-material';
import { searchLocations } from '../api/routes.js';
import { SAMPLING_OPTIONS } from '../constants.js';
import { nextQuarterHour, toLocalInputValue } from '../utils.js';

const MAX_LOAD_LBS = 100000;
const MAX_DAYS_AHEAD = 7;

/** Place input with debounced Nominatim suggestions and a "pick on map" button. */
function PlaceField({ label, placeholder, icon, value, onChange, error, picking, onPick }) {
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const timer = useRef(null);
  const controller = useRef(null);

  useEffect(
    () => () => {
      clearTimeout(timer.current);
      controller.current?.abort();
    },
    []
  );

  const search = (query) => {
    clearTimeout(timer.current);
    controller.current?.abort();
    if (query.trim().length < 3) {
      setOptions([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    timer.current = setTimeout(async () => {
      controller.current = new AbortController();
      try {
        setOptions(await searchLocations(query, controller.current.signal));
      } catch {
        setOptions([]);
      } finally {
        setLoading(false);
      }
    }, 400);
  };

  return (
    <Autocomplete
      freeSolo
      options={options}
      filterOptions={(x) => x}
      getOptionLabel={(option) => (typeof option === 'string' ? option : option.label)}
      loading={loading}
      inputValue={value.text}
      onInputChange={(_, text, reason) => {
        if (reason === 'reset') return; // handled by onChange
        onChange({ text, coords: null });
        search(text);
      }}
      onChange={(_, option) => {
        if (option && typeof option !== 'string') {
          onChange({ text: option.label, coords: [option.lat, option.lng] });
        }
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          placeholder={placeholder}
          error={Boolean(error)}
          helperText={error}
          slotProps={{
            ...params.slotProps,
            input: {
              ...params.slotProps.input,
              startAdornment: <InputAdornment position="start">{icon}</InputAdornment>,
              endAdornment: (
                <>
                  <Tooltip title={picking ? 'Click the map, or press Esc to cancel' : 'Pick on map'}>
                    <IconButton
                      size="small"
                      onClick={onPick}
                      aria-label={`Pick ${label.toLowerCase()} on map`}
                      aria-pressed={picking}
                      color={picking ? 'primary' : 'default'}
                      sx={{ mr: -0.5, ...(picking && { bgcolor: 'rgba(95, 222, 222, 0.15)' }) }}
                    >
                      <PickIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  {params.slotProps.input.endAdornment}
                </>
              ),
            },
          }}
        />
      )}
    />
  );
}

/**
 * Origin and destination live in App, because they can also be set by
 * clicking the map. `picking` is 'origin', 'destination' or null.
 */
function RouteForm({ onSubmit, loading, error, origin, destination, onOriginChange, onDestinationChange, picking, onPick }) {
  const [departure, setDeparture] = useState(() => toLocalInputValue(nextQuarterHour()));
  const [loadWeight, setLoadWeight] = useState('');
  const [interval, setSamplingInterval] = useState('auto');
  const [errors, setErrors] = useState({});

  const validate = () => {
    const next = {};
    if (!origin.text.trim()) next.origin = 'Enter an origin';
    if (!destination.text.trim()) next.destination = 'Enter a destination';

    const departureDate = new Date(departure);
    const now = Date.now();
    if (!departure || Number.isNaN(departureDate.getTime())) {
      next.departure = 'Choose a departure date and time';
    } else if (departureDate.getTime() < now - 60 * 60 * 1000) {
      next.departure = 'Departure is in the past';
    } else if (departureDate.getTime() > now + MAX_DAYS_AHEAD * 24 * 3600 * 1000) {
      next.departure = `Forecasts cover the next ${MAX_DAYS_AHEAD} days only`;
    }

    const weight = Number(loadWeight);
    if (loadWeight === '') next.loadWeight = 'Enter the load weight';
    else if (!Number.isFinite(weight) || weight < 0 || weight > MAX_LOAD_LBS) {
      next.loadWeight = `Enter a weight between 0 and ${MAX_LOAD_LBS.toLocaleString()} lb`;
    }

    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const place = ({ text, coords }) => (coords ? `${coords[0]},${coords[1]}` : text.trim());

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!validate()) return;
    onSubmit({
      origin: place(origin),
      destination: place(destination),
      departure_datetime: new Date(departure).toISOString(),
      load_weight_lbs: Number(loadWeight),
      interval_miles: interval === 'auto' ? null : interval,
    });
  };

  const iconSx = { color: 'primary.main', fontSize: 20 };

  return (
    <Box component="form" noValidate onSubmit={handleSubmit} sx={{ p: 3, display: 'flex', flexDirection: 'column', gap: 2.5 }}>
      <Typography variant="h6" sx={{ fontSize: '1.1rem' }}>
        Plan a trip
      </Typography>

      {error && <Alert severity="error">{error}</Alert>}

      <PlaceField
        label="Origin"
        placeholder="e.g. Oklahoma City, OK"
        icon={<OriginIcon sx={iconSx} />}
        value={origin}
        onChange={onOriginChange}
        error={errors.origin}
        picking={picking === 'origin'}
        onPick={() => onPick('origin')}
      />
      <PlaceField
        label="Destination"
        placeholder="e.g. Casper, WY"
        icon={<DestinationIcon sx={iconSx} />}
        value={destination}
        onChange={onDestinationChange}
        error={errors.destination}
        picking={picking === 'destination'}
        onPick={() => onPick('destination')}
      />

      <TextField
        label="Departure"
        type="datetime-local"
        value={departure}
        onChange={(e) => setDeparture(e.target.value)}
        error={Boolean(errors.departure)}
        helperText={errors.departure}
        sx={{ colorScheme: 'dark' }}
        slotProps={{
          inputLabel: { shrink: true },
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <CalendarIcon sx={iconSx} />
              </InputAdornment>
            ),
          },
        }}
      />

      <TextField
        label="Load weight"
        type="number"
        value={loadWeight}
        onChange={(e) => setLoadWeight(e.target.value)}
        placeholder="e.g. 42000"
        error={Boolean(errors.loadWeight)}
        helperText={errors.loadWeight}
        slotProps={{
          htmlInput: { min: 0, max: MAX_LOAD_LBS, step: 500 },
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <WeightIcon sx={iconSx} />
              </InputAdornment>
            ),
            endAdornment: <InputAdornment position="end">lb</InputAdornment>,
          },
        }}
      />

      <Box>
        <Typography id="sampling-label" variant="body2" color="text.secondary" sx={{ mb: 0.75 }}>
          Check weather every
        </Typography>
        <ToggleButtonGroup
          aria-labelledby="sampling-label"
          value={interval}
          exclusive
          fullWidth
          size="small"
          onChange={(_, value) => value !== null && setSamplingInterval(value)}
        >
          {SAMPLING_OPTIONS.map((option) => (
            <ToggleButton key={option.value} value={option.value} title={option.hint}>
              {option.label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Box>

      <Button
        type="submit"
        variant="contained"
        size="large"
        disabled={loading}
        sx={{ mt: 0.5 }}
        startIcon={loading ? <CircularProgress size={18} color="inherit" /> : <SearchIcon />}
      >
        {loading ? 'Finding routes…' : 'Find routes'}
      </Button>
    </Box>
  );
}

// Memoised: the forecast slider and full-map toggle re-render App often, and
// this panel doesn't depend on either.
export default memo(RouteForm);
