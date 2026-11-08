import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../theme.js';
import ForecastSlider from '../components/ForecastSlider.jsx';

function Harness({ start = 0, arrivalHour }) {
  const [hour, setHour] = useState(start);
  return (
    <>
      <output data-testid="hour">{hour}</output>
      <ForecastSlider hour={hour} onChange={setHour} startTime="2026-11-08T14:00:00Z" arrivalHour={arrivalHour} />
    </>
  );
}

function renderSlider(props) {
  render(
    <ThemeProvider theme={theme}>
      <Harness {...props} />
    </ThemeProvider>
  );
}

// Advance playback one step at a time so each React update is flushed
function runFor(steps) {
  for (let i = 0; i < steps; i += 1) {
    act(() => {
      vi.advanceTimersByTime(400);
    });
  }
}

const hour = () => Number(screen.getByTestId('hour').textContent);

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('ForecastSlider playback', () => {
  it('stops when the truck arrives', () => {
    renderSlider({ arrivalHour: 5 });
    fireEvent.click(screen.getByRole('button', { name: 'Play forecast' }));
    runFor(20);
    expect(hour()).toBe(5);
    expect(screen.getByRole('button', { name: 'Play forecast' })).toBeInTheDocument();
  });

  it('continues through the rest of the forecast when played again after arrival', () => {
    renderSlider({ start: 5, arrivalHour: 5 });
    fireEvent.click(screen.getByRole('button', { name: 'Play forecast' }));
    runFor(60);
    expect(hour()).toBe(48);
  });

  it('restarts from departure when played at the end', () => {
    renderSlider({ start: 48, arrivalHour: 5 });
    fireEvent.click(screen.getByRole('button', { name: 'Play forecast' }));
    runFor(20);
    expect(hour()).toBe(5);
  });

  it('collapses to a pill and back, keeping the hour', () => {
    renderSlider({ start: 7, arrivalHour: 20 });
    fireEvent.click(screen.getByRole('button', { name: 'Hide forecast' }));
    runFor(2); // let the fade finish
    expect(screen.getByRole('button', { name: 'Show forecast' })).toHaveTextContent('Forecast +7 h');
    expect(screen.getByRole('slider', { hidden: true })).not.toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Show forecast' }));
    runFor(2);
    expect(screen.getByRole('slider')).toBeVisible();
    expect(hour()).toBe(7);
  });
});
