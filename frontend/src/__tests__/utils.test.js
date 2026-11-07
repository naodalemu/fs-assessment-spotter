import { describe, expect, it } from 'vitest';
import { heatmapCellStyle, intensityToRisk, RISK_COLOR, riskHeadline } from '../constants.js';
import { formatDuration, nextQuarterHour, pointAlongLine, toLocalInputValue } from '../utils.js';

describe('intensityToRisk', () => {
  it.each([
    [0, 'Low'],
    [0.19, 'Low'],
    [0.2, 'Moderate'],
    [0.4, 'High'],
    [0.6, 'Severe'], // 0.6 / 0.2 is 2.999… in floating point
    [0.8, 'No Travel'],
    [1, 'No Travel'],
  ])('maps %s to %s', (value, level) => {
    expect(intensityToRisk(value).key).toBe(level);
  });

  it('styles calm cells faintly and hazardous cells strongly', () => {
    expect(heatmapCellStyle(0).fillOpacity).toBeCloseTo(0.12);
    expect(heatmapCellStyle(0.8)).toEqual({ fillColor: RISK_COLOR['No Travel'], fillOpacity: 0.62 });
  });
});

describe('riskHeadline', () => {
  it('states No Travel as a verdict', () => {
    expect(riskHeadline('No Travel')).toBe('No Travel: do not drive');
    expect(riskHeadline('High')).toBe('High risk');
  });
});

describe('formatDuration', () => {
  it('formats hours and minutes', () => {
    expect(formatDuration(18.02)).toBe('18 h 01 min');
    expect(formatDuration(0.5)).toBe('30 min');
  });
});

describe('nextQuarterHour', () => {
  it('rounds up to the next quarter hour', () => {
    const d = nextQuarterHour(new Date(2026, 10, 8, 9, 7, 30));
    expect(toLocalInputValue(d)).toBe('2026-11-08T09:15');
  });

  it('always moves into the future', () => {
    const d = nextQuarterHour(new Date(2026, 10, 8, 9, 15, 0));
    expect(toLocalInputValue(d)).toBe('2026-11-08T09:30');
  });
});

describe('pointAlongLine', () => {
  const line = [
    [0, 0],
    [0, 1],
    [0, 3],
  ];

  it('returns endpoints at 0 and 1', () => {
    expect(pointAlongLine(line, 0)).toEqual([0, 0]);
    expect(pointAlongLine(line, 1)).toEqual([0, 3]);
    expect(pointAlongLine(line, 2)).toEqual([0, 3]);
  });

  it('interpolates by distance, not by vertex count', () => {
    const [lat, lng] = pointAlongLine(line, 0.5);
    expect(lat).toBeCloseTo(0);
    expect(lng).toBeCloseTo(1.5);
  });

  it('handles empty input', () => {
    expect(pointAlongLine([], 0.5)).toBeNull();
  });
});
