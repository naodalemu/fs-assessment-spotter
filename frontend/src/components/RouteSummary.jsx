import { memo, useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardActionArea,
  Chip,
  Collapse,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import { ExpandMore as ExpandIcon, Star as StarIcon, WarningAmber as WarningIcon } from '@mui/icons-material';
import WeatherIcon from './WeatherIcon.jsx';
import { RISK_COLOR, RISK_LEVELS, ROUTE_COLORS } from '../constants.js';
import { formatDayTime, formatDuration, formatMiles, formatTime } from '../utils.js';

function Dot({ color, size = 8 }) {
  return <Box component="span" sx={{ width: size, height: size, borderRadius: '50%', bgcolor: color, flexShrink: 0 }} />;
}

export function RiskBar({ summary, distance }) {
  const segments = RISK_LEVELS.map((level) => ({ ...level, miles: summary[level.field] || 0 })).filter(
    (s) => s.miles > 0
  );
  const tooltip = (
    <Box>
      {segments.map((s) => (
        <div key={s.key}>
          {s.key}: {formatMiles(s.miles)}
        </div>
      ))}
      <div>Risk score {summary.average_risk_score.toFixed(2)} (1 = all Low, 5 = all No Travel)</div>
    </Box>
  );
  return (
    <Tooltip title={tooltip} arrow placement="bottom">
      <Box
        role="img"
        aria-label={segments.map((s) => `${s.key} ${Math.round(s.miles)} miles`).join(', ')}
        sx={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', bgcolor: 'action.hover', gap: '2px' }}
      >
        {segments.map((s) => (
          <Box
            key={s.key}
            sx={{
              width: `${(s.miles / distance) * 100}%`,
              bgcolor: s.color,
              animation: 'grow-x 600ms cubic-bezier(0.4, 0, 0.2, 1) both',
              transformOrigin: 'left',
            }}
          />
        ))}
      </Box>
    </Tooltip>
  );
}

/** Only the levels worth attention; an all-Low route gets a single calm line. */
function RiskSummary({ summary }) {
  const notable = RISK_LEVELS.slice(1).filter((level) => summary[level.field] > 0);
  if (!notable.length) {
    return (
      <Typography variant="caption" color="text.secondary">
        Low risk the whole way
      </Typography>
    );
  }
  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', columnGap: 1.5 }}>
      {notable.map((level) => (
        <Box key={level.key} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Dot color={level.color} />
          <Typography variant="caption" color="text.secondary">
            {level.key} {formatMiles(summary[level.field])}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

function RouteCard({ route, selected, onSelect, order }) {
  const color = ROUTE_COLORS[route.route_index % ROUTE_COLORS.length];
  const summary = route.risk_summary;
  const unsafe = summary.no_travel_miles > 0;
  return (
    <Card
      variant="outlined"
      sx={{
        borderColor: selected ? 'primary.main' : 'divider',
        bgcolor: selected ? 'rgba(95, 222, 222, 0.05)' : 'transparent',
        transition: 'border-color 0.2s, background-color 0.2s',
        // Cards rise in one after another when new results arrive
        animation: `rise-in 360ms cubic-bezier(0.4, 0, 0.2, 1) ${order * 70}ms both`,
      }}
    >
      <CardActionArea onClick={onSelect} aria-pressed={selected} sx={{ px: 2, py: 1.75 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box sx={{ width: 14, height: 4, borderRadius: 2, bgcolor: color, flexShrink: 0 }} />
          <Typography sx={{ fontWeight: 700, flex: 1 }}>{route.name}</Typography>
          {route.is_recommended && <Chip icon={<StarIcon />} label="Recommended" size="small" color="primary" />}
        </Box>

        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, mb: 1.5 }}>
          {formatMiles(route.distance_miles)} · {formatDuration(route.travel_time_hours)} · arrives{' '}
          {formatDayTime(route.arrival_time)}
        </Typography>

        <RiskBar summary={summary} distance={route.distance_miles} />
        <Box sx={{ mt: 0.75 }}>
          <RiskSummary summary={summary} />
        </Box>

        {route.recommendation_reason && (
          <Typography
            variant="body2"
            sx={{ mt: 1.25, display: 'flex', gap: 0.75, alignItems: 'flex-start', color: unsafe ? 'error.light' : 'primary.light' }}
          >
            {unsafe && <WarningIcon sx={{ fontSize: 18, mt: '1px' }} />}
            {route.recommendation_reason}
          </Typography>
        )}
      </CardActionArea>
    </Card>
  );
}

function CheckpointList({ route, onCheckpointClick }) {
  const [open, setOpen] = useState(false);
  return (
    <Box sx={{ mt: 2 }}>
      <Button
        fullWidth
        color="inherit"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        endIcon={<ExpandIcon sx={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 200ms' }} />}
        sx={{ justifyContent: 'space-between', color: 'text.secondary', px: 1 }}
      >
        {route.name} checkpoints ({route.checkpoints.length})
      </Button>
      <Collapse in={open} unmountOnExit>
        <Table size="small" aria-label={`${route.name} checkpoints`} sx={{ '& td, & th': { borderColor: 'divider', py: 0.75 } }}>
          <TableHead>
            <TableRow>
              <TableCell>Mile</TableCell>
              <TableCell>Time</TableCell>
              <TableCell>Weather</TableCell>
              <TableCell>Risk</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {route.checkpoints.map((cp, index) => (
              <TableRow key={cp.mile_marker} hover onClick={() => onCheckpointClick(index)} sx={{ cursor: 'pointer' }}>
                <TableCell>{Math.round(cp.mile_marker)}</TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatTime(cp.eta)}</TableCell>
                <TableCell>
                  <Tooltip title={cp.weather.description} placement="left">
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, whiteSpace: 'nowrap' }}>
                      <WeatherIcon description={cp.weather.description} sx={{ fontSize: 16, color: 'text.secondary' }} />
                      {Math.round(cp.weather.wind_mph)} mph
                    </Box>
                  </Tooltip>
                </TableCell>
                <TableCell>
                  <Tooltip title={cp.risk_reason} placement="left">
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, whiteSpace: 'nowrap' }}>
                      <Dot color={RISK_COLOR[cp.risk_level]} />
                      {cp.risk_level}
                    </Box>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Collapse>
    </Box>
  );
}

function RouteSummary({ routes, selectedIndex, onSelect, onCheckpointClick }) {
  if (!routes?.length) return null;
  const selected = routes[selectedIndex];
  return (
    <Box sx={{ px: 3, pb: 3 }}>
      <Typography variant="h6" sx={{ fontSize: '1.1rem', mb: 1.5 }}>
        Routes
      </Typography>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
        {routes.map((route, index) => (
          <RouteCard
            key={route.route_index}
            route={route}
            selected={index === selectedIndex}
            onSelect={() => onSelect(index)}
            order={index}
          />
        ))}
      </Box>
      {selected && <CheckpointList key={selected.route_index} route={selected} onCheckpointClick={onCheckpointClick} />}
    </Box>
  );
}

// Memoised: the forecast slider and full-map toggle re-render App often, and
// this panel doesn't depend on either.
export default memo(RouteSummary);
