import { useEffect, useMemo, useRef } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import { heatmapCellStyle } from '../constants.js';

const PANE = 'weather-heatmap';
const toRad = (deg) => (deg * Math.PI) / 180;
const mercatorY = (lat) => Math.log(Math.tan(Math.PI / 4 + toRad(lat) / 2));
const inverseMercator = (y) => (2 * Math.atan(Math.exp(y)) - Math.PI / 2) * (180 / Math.PI);
const cellKey = (lat, lng) => `${lat.toFixed(4)},${lng.toFixed(4)}`;

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/**
 * Render every forecast hour as a tiny image: one pixel per grid cell, rows
 * spaced in Mercator projection so the image lines up with the map. The
 * browser's smooth upscaling turns those pixels into a soft heat field.
 * Returns { bounds, frames: [dataUrl per hour] }.
 */
function renderHeatmapFrames(heatmap) {
  const size = heatmap.cell_size_deg;
  // One empty cell of padding on every side, so the outermost cells fade to
  // transparent instead of ending in a hard straight edge.
  const pad = size * 1.5;
  const lats = heatmap.cells.map((c) => c.lat);
  const lngs = heatmap.cells.map((c) => c.lng);
  const west = Math.min(...lngs) - pad;
  const east = Math.max(...lngs) + pad;
  const yTop = mercatorY(Math.max(...lats) + size / 2) + toRad(size);
  const yBottom = mercatorY(Math.min(...lats) - size / 2) - toRad(size);
  const north = inverseMercator(yTop);
  const south = inverseMercator(yBottom);

  const width = Math.round((east - west) / size);
  const height = Math.max(1, Math.round((yTop - yBottom) / toRad(size)));

  // Which cell (if any) each pixel shows
  const index = new Map(heatmap.cells.map((c, i) => [cellKey(c.lat, c.lng), i]));
  const pixelCell = new Int32Array(width * height).fill(-1);
  for (let row = 0; row < height; row += 1) {
    const lat = inverseMercator(yTop - ((row + 0.5) / height) * (yTop - yBottom));
    const cellLat = Math.round(lat / size) * size;
    for (let col = 0; col < width; col += 1) {
      const cellLng = Math.round((west + (col + 0.5) * size) / size) * size;
      pixelCell[row * width + col] = index.get(cellKey(cellLat, cellLng)) ?? -1;
    }
  }

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  const hours = heatmap.cells[0]?.values.length ?? 0;
  const frames = [];
  for (let h = 0; h < hours; h += 1) {
    const image = ctx.createImageData(width, height);
    pixelCell.forEach((cell, p) => {
      if (cell < 0) return;
      const { fillColor, fillOpacity } = heatmapCellStyle(heatmap.cells[cell].values[h]);
      const [r, g, b] = hexToRgb(fillColor);
      image.data.set([r, g, b, Math.round(fillOpacity * 255)], p * 4);
    });
    ctx.putImageData(image, 0, 0);
    frames.push(canvas.toDataURL());
  }
  return { bounds: [[south, west], [north, east]], frames };
}

/**
 * Corridor weather heatmap. Two stacked image layers crossfade between hours,
 * so scrubbing and playback only change opacity (GPU-composited) instead of
 * repainting anything.
 */
function WeatherHeatmap({ heatmap, hour, visible }) {
  const map = useMap();
  const layersRef = useRef(null); // { front, back, hour }
  const rendered = useMemo(() => (heatmap?.cells?.length ? renderHeatmapFrames(heatmap) : null), [heatmap]);

  useEffect(() => {
    if (map.getPane(PANE)) return;
    const pane = map.createPane(PANE);
    pane.style.zIndex = 350; // above tiles (200), below routes (400)
    pane.style.pointerEvents = 'none';
    pane.style.transition = 'opacity 250ms';
  }, [map]);

  useEffect(() => {
    if (!rendered) return undefined;
    // Decode every frame up front so swaps never wait on the image decoder
    rendered.frames.forEach((src) => {
      new Image().src = src;
    });
    const options = { pane: PANE, className: 'heat-frame', interactive: false };
    const front = L.imageOverlay(rendered.frames[0], rendered.bounds, { ...options, opacity: 1 }).addTo(map);
    const back = L.imageOverlay(rendered.frames[0], rendered.bounds, { ...options, opacity: 0 }).addTo(map);
    layersRef.current = { front, back, hour: 0 };
    return () => {
      front.remove();
      back.remove();
      layersRef.current = null;
    };
  }, [rendered, map]);

  useEffect(() => {
    const layers = layersRef.current;
    if (!layers || !rendered || layers.hour === hour) return;
    const { front, back } = layers;
    back.setUrl(rendered.frames[hour]);
    back.setOpacity(1);
    front.setOpacity(0);
    layersRef.current = { front: back, back: front, hour };
  }, [hour, rendered]);

  useEffect(() => {
    const pane = map.getPane(PANE);
    if (pane) pane.style.opacity = visible ? '1' : '0';
  }, [visible, map]);

  return null;
}

export default WeatherHeatmap;
