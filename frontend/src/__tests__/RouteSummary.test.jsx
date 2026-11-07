import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../theme.js';
import RouteSummary from '../components/RouteSummary.jsx';
import { sampleResponse } from './fixtures.js';

function renderSummary(selectedIndex = 0) {
  const onSelect = vi.fn();
  const onCheckpointClick = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <RouteSummary
        routes={sampleResponse.routes}
        selectedIndex={selectedIndex}
        onSelect={onSelect}
        onCheckpointClick={onCheckpointClick}
      />
    </ThemeProvider>
  );
  return { onSelect, onCheckpointClick };
}

describe('RouteSummary', () => {
  it('lists routes in the order given (safest first) with the recommendation', () => {
    renderSummary();
    const cards = screen.getAllByRole('button', { pressed: undefined }).filter((b) => b.hasAttribute('aria-pressed'));
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByText('Route 2')).toBeInTheDocument();
    expect(within(cards[0]).getByText('Recommended')).toBeInTheDocument();
    expect(within(cards[0]).getByText(/fewer Severe miles/)).toBeInTheDocument();
    expect(within(cards[1]).queryByText('Recommended')).not.toBeInTheDocument();
  });

  it('shows distance, drive time and only the risk levels worth attention', () => {
    renderSummary();
    const card = screen.getAllByRole('button').find((b) => within(b).queryByText('Route 1'));
    expect(within(card).getByText(/100 mi · 1 h 30 min · arrives/)).toBeInTheDocument();
    expect(within(card).getByText('Severe 30 mi')).toBeInTheDocument();
    expect(within(card).queryByText(/Low 70 mi/)).not.toBeInTheDocument();
    expect(within(card).getByRole('img')).toHaveAttribute('aria-label', 'Low 70 miles, Severe 30 miles');
  });

  it('summarises an all-Low route in one line', () => {
    render(
      <ThemeProvider theme={theme}>
        <RouteSummary
          routes={[{ ...sampleResponse.routes[0], risk_summary: { ...sampleResponse.routes[0].risk_summary, moderate_miles: 0, low_miles: 100 } }]}
          selectedIndex={0}
          onSelect={() => {}}
          onCheckpointClick={() => {}}
        />
      </ThemeProvider>
    );
    expect(screen.getByText('Low risk the whole way')).toBeInTheDocument();
  });

  it('marks the selected route and reports clicks', () => {
    const { onSelect } = renderSummary(1);
    const card = screen.getAllByRole('button').find((b) => within(b).queryByText('Route 1'));
    expect(card).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getAllByRole('button').find((b) => within(b).queryByText('Route 2')));
    expect(onSelect).toHaveBeenCalledWith(0);
  });

  it('lists checkpoints of the selected route behind a toggle', () => {
    const { onCheckpointClick } = renderSummary(1);
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Route 1 checkpoints (3)' }));
    const table = screen.getByRole('table', { name: 'Route 1 checkpoints' });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByText('Severe')).toBeInTheDocument();
    expect(within(rows[1]).getByText('40 mph')).toBeInTheDocument();
    fireEvent.click(rows[1]);
    expect(onCheckpointClick).toHaveBeenCalledWith(1);
  });
});
