import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../theme.js';
import { sampleResponse } from './fixtures.js';

// Leaflet needs a real browser; render react-leaflet components as plain DOM.
const fakeMap = {
  flyToBounds: vi.fn(),
  flyTo: vi.fn(),
  once: vi.fn(),
  getPane: vi.fn(() => ({ style: {} })),
  createPane: vi.fn(() => ({ style: {} })),
  on: vi.fn(),
  off: vi.fn(),
  getContainer: vi.fn(),
  invalidateSize: vi.fn(),
};

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => <div data-testid="map">{children}</div>,
  TileLayer: ({ className }) => <div data-testid="tiles" className={className} />,
  Polyline: ({ children, pathOptions, eventHandlers }) => (
    <div data-testid="polyline" data-color={pathOptions.color} onClick={eventHandlers?.click}>
      {children}
    </div>
  ),
  CircleMarker: ({ children, radius }) => (
    <div data-testid="marker" data-radius={radius}>
      {children}
    </div>
  ),
  Popup: ({ children }) => <div data-testid="popup">{children}</div>,
  Tooltip: ({ children }) => <div data-testid="tooltip">{children}</div>,
  ZoomControl: () => null,
  useMapEvents: () => fakeMap,
  useMap: () => fakeMap,
}));

vi.mock('../components/WeatherHeatmap.jsx', () => ({
  default: ({ hour, visible }) => <div data-testid="heatmap" data-hour={hour} data-visible={String(visible)} />,
}));

const { default: MapView } = await import('../components/MapView.jsx');

function renderMap(props = {}) {
  const handlers = { onSelect: vi.fn(), onHourChange: vi.fn() };
  render(
    <ThemeProvider theme={theme}>
      <MapView data={sampleResponse} selectedIndex={0} focus={null} loading={false} hour={0} {...handlers} {...props} />
    </ThemeProvider>
  );
  return handlers;
}

describe('MapView', () => {
  it('shows an empty-state hint before a search', () => {
    renderMap({ data: null });
    expect(screen.getByText(/enter a trip/i)).toBeInTheDocument();
    expect(screen.queryByRole('slider')).not.toBeInTheDocument();
  });

  it('shows a loading overlay', () => {
    renderMap({ data: null, loading: true });
    expect(screen.getByRole('status')).toHaveTextContent(/fetching forecasts/i);
  });

  it('draws every route on top of a dark casing', () => {
    const { onSelect } = renderMap();
    const lines = screen.getAllByTestId('polyline');
    // each route = casing + coloured line
    expect(lines).toHaveLength(4);
    expect(lines.filter((l) => l.dataset.color === '#0d1116')).toHaveLength(2);
    fireEvent.click(lines.find((l) => l.textContent.startsWith('Route 1')));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it('shows popups with ETA, weather and the risk reason for the selected route', () => {
    renderMap();
    const popups = screen.getAllByTestId('popup');
    expect(popups).toHaveLength(3);
    expect(popups[1]).toHaveTextContent('Moderate risk');
    expect(popups[2]).toHaveTextContent('Low risk');
    expect(popups[1]).toHaveTextContent('Route 2 · mile 50');
    expect(popups[1]).toHaveTextContent('Moderate reason');
    expect(popups[1]).toHaveTextContent('0.12 in/h');
  });

  it('places the truck along the selected route at the forecast hour', () => {
    renderMap({ hour: 1 });
    expect(screen.getByText('Truck at +1 h · mile 50')).toBeInTheDocument();
    expect(screen.getByTestId('heatmap')).toHaveAttribute('data-hour', '1');
  });

  it('applies the basemap and heatmap visibility it is given', () => {
    renderMap();
    expect(screen.getByTestId('tiles')).toHaveClass('basemap-dark');
    expect(screen.getByTestId('heatmap')).toHaveAttribute('data-visible', 'true');
  });

  it('uses the light basemap and can hide the heatmap', () => {
    renderMap({ basemap: 'light', heatmapVisible: false });
    expect(screen.getByTestId('tiles')).not.toHaveClass('basemap-dark');
    expect(screen.getByTestId('heatmap')).toHaveAttribute('data-visible', 'false');
  });

  it('shows a hint and pins while picking places on the map', () => {
    renderMap({ data: null, picking: 'destination', onMapPick: vi.fn(), pickedPlaces: { origin: [35, -97], destination: null } });
    expect(screen.getByText('Click the map to set the destination · Esc to cancel')).toBeInTheDocument();
    expect(screen.getByText('Origin')).toBeInTheDocument();
  });

  it('reports slider changes', () => {
    const { onHourChange } = renderMap();
    const slider = screen.getByRole('slider', { name: 'Forecast hour' });
    fireEvent.keyDown(slider, { key: 'ArrowRight' });
    expect(onHourChange).toHaveBeenCalledWith(1);
  });
});
