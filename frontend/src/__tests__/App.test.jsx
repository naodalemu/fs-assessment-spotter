import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../theme.js';
import { sampleResponse } from './fixtures.js';

const fetchRoutes = vi.fn();
const reverseGeocode = vi.fn();
vi.mock('../api/routes.js', () => ({
  fetchRoutes: (...args) => fetchRoutes(...args),
  reverseGeocode: (...args) => reverseGeocode(...args),
  searchLocations: vi.fn().mockResolvedValue([]),
}));
vi.mock('../components/MapView.jsx', () => ({
  default: ({ data, selectedIndex, basemap, heatmapVisible, picking, onMapPick }) => (
    <div
      data-testid="map"
      data-routes={data?.routes.length ?? 0}
      data-selected={selectedIndex}
      data-basemap={basemap}
      data-heatmap={String(heatmapVisible)}
      data-picking={picking ?? ''}
    >
      {/* stands in for clicking the map */}
      <button type="button" onClick={() => picking && onMapPick(picking, 35.4676123, -97.5164)}>
        click map
      </button>
    </div>
  ),
}));

const { default: App } = await import('../App.jsx');

function submitTrip() {
  fireEvent.change(screen.getByLabelText('Origin'), { target: { value: 'Oklahoma City, OK' } });
  fireEvent.change(screen.getByLabelText('Destination'), { target: { value: 'Wichita, KS' } });
  fireEvent.change(screen.getByLabelText('Load weight'), { target: { value: '42000' } });
  fireEvent.click(screen.getByRole('button', { name: /find routes/i }));
}

function renderApp() {
  render(
    <ThemeProvider theme={theme}>
      <App />
    </ThemeProvider>
  );
}

function mockDeviceTheme(dark) {
  window.matchMedia = vi.fn(() => ({ matches: dark, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
}

beforeEach(() => {
  localStorage.clear();
  delete window.matchMedia;
});

describe('App', () => {
  it('shows routes after a successful search, without data-source noise', async () => {
    fetchRoutes.mockResolvedValueOnce(sampleResponse);
    renderApp();
    submitTrip();
    await screen.findByText('Routes');
    expect(screen.getByTestId('map')).toHaveAttribute('data-routes', '2');
    expect(screen.queryByText(/demo mode/i)).not.toBeInTheDocument();
  });

  it('flags simulated data', async () => {
    fetchRoutes.mockResolvedValueOnce({ ...sampleResponse, sources: { routing: 'simulated', weather: 'simulated' } });
    renderApp();
    submitTrip();
    const notice = await screen.findByText(/demo mode/i);
    expect(notice).toHaveTextContent('Demo mode: routes are simulated and weather is simulated, not a real forecast.');
  });

  it('shows API errors', async () => {
    fetchRoutes.mockRejectedValueOnce(new Error("Could not find 'Wichita, KS'."));
    renderApp();
    submitTrip();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent("Could not find 'Wichita, KS'."));
  });

  it('keeps form values when toggling the full map', async () => {
    renderApp();
    fireEvent.change(screen.getByLabelText('Origin'), { target: { value: 'Tulsa, OK' } });
    fireEvent.click(screen.getByRole('button', { name: 'Full map' }));
    fireEvent.click(screen.getByRole('button', { name: 'Exit full map' }));
    expect(screen.getByLabelText('Origin')).toHaveValue('Tulsa, OK');
  });

  it('header toolbar controls the basemap and heatmap', () => {
    renderApp();
    const map = screen.getByTestId('map');
    expect(map).toHaveAttribute('data-basemap', 'dark');
    fireEvent.click(screen.getByRole('button', { name: 'Light' }));
    expect(map).toHaveAttribute('data-basemap', 'light');
    fireEvent.click(screen.getByRole('switch', { name: 'Heatmap' }));
    expect(map).toHaveAttribute('data-heatmap', 'false');
  });

  it('starts from the device light/dark setting', () => {
    mockDeviceTheme(false);
    renderApp();
    expect(screen.getByTestId('map')).toHaveAttribute('data-basemap', 'light');
  });

  it('remembers the chosen map theme over the device setting', () => {
    mockDeviceTheme(true);
    renderApp();
    fireEvent.click(screen.getByRole('button', { name: 'Light' }));
    expect(localStorage.getItem('basemap')).toBe('light');
  });

  it('restores a saved map theme on reload', () => {
    mockDeviceTheme(true);
    localStorage.setItem('basemap', 'light');
    renderApp();
    expect(screen.getByTestId('map')).toHaveAttribute('data-basemap', 'light');
  });

  it('sets origin and destination by clicking the map', async () => {
    reverseGeocode.mockResolvedValueOnce('Oklahoma City, Oklahoma');
    fetchRoutes.mockResolvedValueOnce(sampleResponse);
    renderApp();
    const map = screen.getByTestId('map');

    fireEvent.click(screen.getByRole('button', { name: 'Pick origin on map' }));
    expect(map).toHaveAttribute('data-picking', 'origin');
    fireEvent.click(screen.getByRole('button', { name: 'click map' }));
    expect(map).toHaveAttribute('data-picking', '');
    // exact point first, then the readable name from the reverse lookup
    await waitFor(() => expect(screen.getByLabelText('Origin')).toHaveValue('Oklahoma City, Oklahoma'));
    expect(reverseGeocode).toHaveBeenCalledWith(35.46761, -97.5164);

    fireEvent.change(screen.getByLabelText('Destination'), { target: { value: 'Wichita, KS' } });
    fireEvent.change(screen.getByLabelText('Load weight'), { target: { value: '42000' } });
    fireEvent.click(screen.getByRole('button', { name: /find routes/i }));
    await waitFor(() => expect(fetchRoutes).toHaveBeenCalled());
    // the picked point, not the name, is what the backend gets
    expect(fetchRoutes.mock.calls.at(-1)[0].origin).toBe('35.46761,-97.5164');
  });

  it('keeps the coordinates if the place name lookup fails', async () => {
    reverseGeocode.mockRejectedValueOnce(new Error('offline'));
    renderApp();
    fireEvent.click(screen.getByRole('button', { name: 'Pick destination on map' }));
    fireEvent.click(screen.getByRole('button', { name: 'click map' }));
    await waitFor(() => expect(reverseGeocode).toHaveBeenCalled());
    expect(screen.getByLabelText('Destination')).toHaveValue('35.46761, -97.5164');
  });

  it('Escape cancels picking', () => {
    renderApp();
    fireEvent.click(screen.getByRole('button', { name: 'Pick origin on map' }));
    expect(screen.getByTestId('map')).toHaveAttribute('data-picking', 'origin');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByTestId('map')).toHaveAttribute('data-picking', '');
  });

  it('full map hides both the header and the side panel', () => {
    renderApp();
    const header = screen.getByRole('banner');
    const panel = screen.getByRole('complementary');
    fireEvent.click(screen.getByRole('button', { name: 'Full map' }));
    expect(header).toHaveAttribute('inert');
    expect(panel).toHaveAttribute('inert');
    // The toolbar stays put and its button becomes "Exit full map"
    expect(screen.getByRole('button', { name: 'Exit full map' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Light' })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'f' });
    expect(header).not.toHaveAttribute('inert');
  });
});
