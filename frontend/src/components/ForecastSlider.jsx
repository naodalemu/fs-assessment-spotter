import { useEffect, useState } from 'react';
import { Box, IconButton, Slider, Tooltip, Typography } from '@mui/material';
import { Pause as PauseIcon, PlayArrow as PlayIcon } from '@mui/icons-material';
import { FORECAST_HOURS, RISK_LEVELS } from '../constants.js';
import { formatDateTime } from '../utils.js';

const MARKS = [0, 12, 24, 36, 48].map((h) => ({ value: h, label: `${h}h` }));
const PLAY_STEP_MS = 350;

/**
 * 0–48 h forecast scrubber. Hour 0 is the departure time; the label shows
 * the absolute time so drivers can relate it to checkpoint ETAs.
 */
function ForecastSlider({ hour, onChange, startTime }) {
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return undefined;
    const id = setTimeout(() => {
      if (hour >= FORECAST_HOURS) setPlaying(false);
      else onChange(hour + 1);
    }, PLAY_STEP_MS);
    return () => clearTimeout(id);
  }, [playing, hour, onChange]);

  const togglePlay = () => {
    if (!playing && hour >= FORECAST_HOURS) onChange(0);
    setPlaying((p) => !p);
  };

  const time = new Date(new Date(startTime).getTime() + hour * 3600 * 1000);

  return (
    <Box
      sx={{
        position: 'absolute',
        bottom: 24,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 1000,
        width: 'min(520px, calc(100% - 32px))',
        bgcolor: 'rgba(13, 17, 22, 0.92)',
        border: 1,
        borderColor: 'divider',
        borderRadius: 2,
        boxShadow: 6,
        px: 2,
        pt: 1.25,
        pb: 0.5,
      }}
    >
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
            setPlaying(false);
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
  );
}

export default ForecastSlider;
