// H3 Scene Map layout: markers, one camera and the legend, in coordinates from 0 to 1 across the map picture.
// h3_continuity/scene_map.py normalizes and draws the same layout; keep the two in step.
import {ICONS} from './h3c_scene_map_icons.mjs?v=a943d84d2d3c';

export const MARKER_RADIUS = 0.017;
export const LEGEND_POSITIONS = ['bottom-left', 'bottom-right', 'top-left', 'top-right'];
export const PALETTE = ['#e0352b', '#ff7a1a', '#ffd23f', '#2ec4b6', '#3a86ff', '#7b4bd6', '#ffffff', '#1d1d1f'];

const unitRange = value => Math.min(1, Math.max(0, Number.isFinite(Number(value)) ? Number(value) : 0.5));
const range = (value, fallback, low, high) => {
  const number = Number(value);
  return Number.isFinite(number) && value !== null && value !== '' ? Math.min(high, Math.max(low, number)) : fallback;
};
const color = (value, fallback) => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value.toLowerCase() : fallback;
const text = (value, limit) => typeof value === 'string' ? value.trim().slice(0, limit) : '';

export function emptyLayout() {
  return {version: 1, width: null, height: null, scale: 1, legend: {show: true, position: 'bottom-left'}, camera: null, markers: []};
}

export function parseLayout(value) {
  let data;
  try { data = typeof value === 'string' ? (value.trim() ? JSON.parse(value) : {}) : value; } catch { data = {}; }
  if (!data || typeof data !== 'object' || Array.isArray(data)) data = {};
  const layout = emptyLayout();
  for (const key of ['width', 'height']) if (Number(data[key]) > 0) layout[key] = Math.round(Number(data[key]));
  layout.scale = range(data.scale, 1, 0.25, 4);
  const legend = data.legend && typeof data.legend === 'object' ? data.legend : {};
  layout.legend = {show: legend.show !== false, position: LEGEND_POSITIONS.includes(legend.position) ? legend.position : 'bottom-left'};
  layout.markers = (Array.isArray(data.markers) ? data.markers : []).filter(item => item && typeof item === 'object').map((item, index) => ({
    id: text(item.id, 40) || `m${index + 1}`, x: unitRange(item.x), y: unitRange(item.y),
    icon: Object.hasOwn(ICONS, item.icon) ? item.icon : 'dot', color: color(item.color, PALETTE[0]),
    size: range(item.size, 1, 0.3, 4), label: text(item.label, 60), text: text(item.text, 3), legend: item.legend !== false,
  }));
  const camera = data.camera;
  if (camera && typeof camera === 'object') {
    layout.camera = {x: unitRange(camera.x ?? 0.5), y: unitRange(camera.y ?? 0.8), tx: unitRange(camera.tx ?? 0.5), ty: unitRange(camera.ty ?? 0.4),
      fov: range(camera.fov, 55, 5, 170), height: range(camera.height, 1.5, 0, 10000), label: text(camera.label, 40) || 'CAMERA',
      color: color(camera.color, '#ffffff')};
  }
  return layout;
}

export const serializeLayout = layout => JSON.stringify(layout);

// The badge radius in picture pixels for a W x H picture.
export const unit = (layout, width, height) => MARKER_RADIUS * Math.max(width, height) * layout.scale;

export function heading(camera, width, height) {
  return Math.atan2((camera.ty - camera.y) * height, (camera.tx - camera.x) * width);
}

export function legendRows(layout) {
  const rows = [], seen = new Set();
  for (const marker of layout.markers) {
    const key = JSON.stringify([marker.icon, marker.color, marker.label, marker.text]);
    if (!marker.legend || !marker.label || seen.has(key)) continue;
    seen.add(key);
    rows.push({kind: 'marker', icon: marker.icon, color: marker.color, text: marker.label, mark: marker.text});
  }
  const camera = layout.camera;
  if (camera) rows.push({kind: 'camera', color: camera.color,
    text: `${camera.label} · tip = lens, ${Number(camera.height.toPrecision(6))} m above ground, ${Math.round(camera.fov)}° view`});
  return rows;
}

// The editor's view cone, in picture pixels: the camera, then the far arc. It is never drawn into the output.
export function cone(camera, width, height, reach = 1.25, steps = 32) {
  const px = camera.x * width, py = camera.y * height;
  const angle = heading(camera, width, height), half = camera.fov * Math.PI / 360;
  const length = Math.hypot(camera.tx * width - px, camera.ty * height - py) * reach;
  return [[px, py], ...Array.from({length: steps + 1}, (_, i) => {
    const a = angle - half + 2 * half * i / steps;
    return [px + length * Math.cos(a), py + length * Math.sin(a)];
  })];
}

// What lies under picture point (x, y): the camera's target, the camera, then the topmost marker.
export function hitTest(layout, width, height, x, y) {
  const r = unit(layout, width, height);
  const near = (px, py, radius) => Math.hypot(x - px, y - py) <= radius;
  const camera = layout.camera;
  if (camera && near(camera.tx * width, camera.ty * height, r * 0.9)) return {kind: 'target'};
  if (camera) {
    const angle = heading(camera, width, height), px = camera.x * width, py = camera.y * height;
    // The arrow runs back from its tip at the camera; grab it anywhere along its length.
    const along = -((x - px) * Math.cos(angle) + (y - py) * Math.sin(angle));
    const across = Math.abs(-(x - px) * Math.sin(angle) + (y - py) * Math.cos(angle));
    if ((along >= -r * 0.5 && along <= r * 4.2 && across <= r * 0.9) || near(px, py, r)) return {kind: 'camera'};
  }
  for (let index = layout.markers.length - 1; index >= 0; index--) {
    const marker = layout.markers[index];
    if (near(marker.x * width, marker.y * height, r * marker.size * 1.15)) return {kind: 'marker', index};
  }
  return null;
}

export function addMarker(layout, x, y, {icon = 'dot', color: fill = PALETTE[0]} = {}) {
  const used = new Set(layout.markers.map(marker => marker.id));
  let n = layout.markers.length + 1;
  while (used.has(`m${n}`)) n++;
  const marker = {id: `m${n}`, x: unitRange(x), y: unitRange(y), icon, color: fill, size: 1, label: '', text: '', legend: true};
  layout.markers.push(marker);
  return layout.markers.length - 1;
}

// A camera standing at (x, y) and looking at (tx, ty); a press without a drag looks up the map.
export function placeCamera(layout, x, y, tx = x, ty = y) {
  const previous = layout.camera ?? {fov: 55, height: 1.5, label: 'CAMERA', color: '#ffffff'};
  const still = Math.hypot(tx - x, ty - y) < 0.01;
  layout.camera = {...previous, x: unitRange(x), y: unitRange(y), tx: unitRange(still ? x : tx), ty: unitRange(still ? Math.max(0, y - 0.25) : ty)};
  if (layout.camera.tx === layout.camera.x && layout.camera.ty === layout.camera.y) layout.camera.ty = Math.min(1, y + 0.25);
  return layout.camera;
}

export const iconNames = () => Object.entries(ICONS).map(([key, icon]) => ({key, name: icon.name}));
