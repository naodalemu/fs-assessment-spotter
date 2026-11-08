import { useEffect, useState } from 'react';
import { Box, Button, Fade, IconButton, Slider, Tooltip, Typography } from '@mui/material';
import {
  ExpandLess as ShowIcon,
  ExpandMore as HideIcon,
  Pause as PauseIcon,
  PlayArrow as PlayIcon,
  Schedule as ClockIcon,
} from '@mui/icons-material';
import { FORECAST_HOURS, RISK_LEVELS } from '../constants.js';
import { formatDateTime } from '../utils.js';

const MARKS = [0, 12, 24, 36, 48].map((h) => ({ value: h, label: `${h}h` }));
const PLAY_STEP_MS = 350;

// Shared look and position of the card and its collapsed pill
const FLOATING = {
  position: 'absolute',
  bottom: 24,
  left: '50%',
  transform: 'translateX(-50%)',
  zIndex: 1000,
  bgcolor: 'rgba(13, 17, 22, 0.92)',
  border: 1,
  borderColor: 'divider',
  boxShadow: 6,
};

/**
 * 0–48 h forecast scrubber. Hour 0 is the departure time; the label shows
 * the absolute time so drivers can relate it to checkpoint ETAs.
 *
 * Play follows the selected truck and stops when it arrives (`arrivalHour`).
 * Pressing play again from there continues through the rest of the 48 h
 * forecast; dragging can always go anywhere.
 */
function ForecastSlider({ hour, onChange, startTime, arrivalHour = FORECAST_HOURS }) {
  const [stopAt, setStopAt] = useState(null); // hour where playback ends; null = paused
  const [hidden, setHidden] = useState(false); // collapsed to a small pill; playback keeps running
  const playing = stopAt !== null;

  useEffect(() => {
    if (!playing) return undefined;
    const id = setTimeout(() => {
      if (hour >= stopAt) setStopAt(null);
      else onChange(hour + 1);
    }, PLAY_STEP_MS);
    return () => clearTimeout(id);
  }, [playing, stopAt, hour, onChange]);

  const togglePlay = () => {
    if (playing) {
      setStopAt(null);
      return;
    }
    const arrival = Math.min(arrivalHour, FORECAST_HOURS);
    const from = hour >= FORECAST_HOURS ? 0 : hour;
    if (from !== hour) onChange(from);
    setStopAt(from < arrival ? arrival : FORECAST_HOURS);
  };

  const time = new Date(new Date(startTime).getTime() + hour * 3600 * 1000);

  return (
    <>
      <Fade in={hidden}>
        <Button
          onClick={() => setHidden(false)}
          aria-label="Show forecast"
          startIcon={<ClockIcon />}
          endIcon={<ShowIcon />}
          sx={{
            ...FLOATING,
            color: 'text.primary',
            borderRadius: 5,
            px: 2,
            whiteSpace: 'nowrap',
            '&:hover': { bgcolor: 'rgba(13, 17, 22, 0.98)' },
          }}
        >
          Forecast +{hour} h
        </Button>
      </Fade>

      <Fade in={!hidden}>
        <Box sx={{ ...FLOATING, width: 'min(520px, calc(100% - 32px))', borderRadius: 2, px: 2, pt: 1.25, pb: 0.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Tooltip title={playing ? 'Pause' : 'Play forecast'}>
              <IconButton size="small" onClick={togglePlay} aria-label={playing ? 'Pause forecast' : 'Play forecast'}>
                {playing ? <PauseIcon /> : <PlayIcon />}
              </IconButton>
            </Tooltip>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.2 }}>
                Corridor forecast · departure +{hour} h
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: 700 }} aria-live="polite">
                {formatDateTime(time)}
              </Typography>
            </Box>
            <Tooltip title="Hide forecast">
              <IconButton size="small" onClick={() => setHidden(true)} aria-label="Hide forecast">
                <HideIcon />
              </IconButton>
            </Tooltip>
          </Box>
          <Box sx={{ px: 1 }}>
            <Slider
              aria-label="Forecast hour"
              value={hour}
              min={0}
              max={FORECAST_HOURS}
              step={1}
              marks={MARKS}
              onChange={(_, value) => {
                setStopAt(null);
                onChange(value);
              }}
              size="small"
            />
          </Box>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', columnGap: 1.5, pb: 0.75 }}>
            {RISK_LEVELS.map((level) => (
              <Box key={level.key} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Box sx={{ width: 9, height: 9, borderRadius: '50%', bgcolor: level.color }} />
                <Typography variant="caption">{level.key}</Typography>
              </Box>
            ))}
          </Box>
        </Box>
      </Fade>
    </>
  );
}

export default ForecastSlider;
