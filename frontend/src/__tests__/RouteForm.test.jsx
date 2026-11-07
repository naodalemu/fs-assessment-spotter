import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../theme.js';
import RouteForm from '../components/RouteForm.jsx';

vi.mock('../api/routes.js', () => ({ searchLocations: vi.fn().mockResolvedValue([]) }));

// Holds origin/destination the way App does
function Harness({ onSubmit, onPick, ...props }) {
  const [origin, setOrigin] = useState({ text: '', coords: null });
  const [destination, setDestination] = useState({ text: '', coords: null });
  return (
    <RouteForm
      onSubmit={onSubmit}
      loading={false}
      error={null}
      origin={origin}
      destination={destination}
      onOriginChange={setOrigin}
      onDestinationChange={setDestination}
      picking={null}
      onPick={onPick}
      {...props}
    />
  );
}

function renderForm(props = {}) {
  const onSubmit = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <Harness onSubmit={onSubmit} onPick={vi.fn()} {...props} />
    </ThemeProvider>
  );
  return onSubmit;
}

function fill(label, value) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe('RouteForm', () => {
  it('requires origin, destination and load weight', () => {
    const onSubmit = renderForm();
    fireEvent.click(screen.getByRole('button', { name: /find routes/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Enter an origin')).toBeInTheDocument();
    expect(screen.getByText('Enter a destination')).toBeInTheDocument();
    expect(screen.getByText('Enter the load weight')).toBeInTheDocument();
  });

  it('rejects out-of-range load weights', () => {
    const onSubmit = renderForm();
    fill('Origin', 'Dallas, TX');
    fill('Destination', 'Austin, TX');
    fill('Load weight', '150000');
    fireEvent.click(screen.getByRole('button', { name: /find routes/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/between 0 and 100,000 lb/)).toBeInTheDocument();
  });

  it('rejects a departure in the past', () => {
    const onSubmit = renderForm();
    fill('Origin', 'Dallas, TX');
    fill('Destination', 'Austin, TX');
    fill('Load weight', '20000');
    fill('Departure', '2020-01-01T08:00');
    fireEvent.click(screen.getByRole('button', { name: /find routes/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Departure is in the past')).toBeInTheDocument();
  });

  it('submits auto sampling as null', () => {
    const onSubmit = renderForm();
    fill('Origin', 'Dallas, TX');
    fill('Destination', 'Austin, TX');
    fill('Load weight', '42000');
    fireEvent.click(screen.getByRole('button', { name: /find routes/i }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const request = onSubmit.mock.calls[0][0];
    expect(request).toMatchObject({
      origin: 'Dallas, TX',
      destination: 'Austin, TX',
      load_weight_lbs: 42000,
      interval_miles: null,
    });
    expect(new Date(request.departure_datetime).getTime()).toBeGreaterThan(Date.now());
  });

  it('submits the chosen sampling interval', () => {
    const onSubmit = renderForm();
    fill('Origin', 'Dallas, TX');
    fill('Destination', 'Austin, TX');
    fill('Load weight', '0');
    fireEvent.click(screen.getByRole('button', { name: '10 mi' }));
    expect(screen.getByRole('button', { name: '10 mi' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: /find routes/i }));
    expect(onSubmit.mock.calls[0][0].interval_miles).toBe(10);
  });

  it('offers a pick-on-map button for each place', () => {
    const onPick = vi.fn();
    renderForm({ onPick });
    fireEvent.click(screen.getByRole('button', { name: 'Pick destination on map' }));
    expect(onPick).toHaveBeenCalledWith('destination');
  });

  it('highlights the field being picked', () => {
    renderForm({ picking: 'origin' });
    expect(screen.getByRole('button', { name: 'Pick origin on map' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Pick destination on map' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('shows server errors and the loading state', () => {
    renderForm({ error: 'Could not find "Nowhere".', loading: true });
    expect(screen.getByRole('alert')).toHaveTextContent('Could not find "Nowhere".');
    expect(screen.getByRole('button', { name: /finding routes/i })).toBeDisabled();
  });
});
