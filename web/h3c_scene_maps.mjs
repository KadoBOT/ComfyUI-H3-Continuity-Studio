// Scene maps on Studio clips: an opening and an end layout per clip. A clip that continues an adjacent clip whose map is
// on borrows that clip's picture, camera look, markers and end positions as its opening, and keeps a copy (markers
// flagged `borrowed`) for when the link breaks. Mirrors h3_continuity/scene_maps.py; every edit here mutates the state
// and the caller commits it for undo.
import * as tracks from './h3c_tracks.mjs';

export const FEATURE = 'scene-map-1';
const LEGEND_POSITIONS = ['bottom-left', 'bottom-right', 'top-left', 'top-right'];
const CAMERA_LOOK = {fov: 55, height: 1.5, label: 'CAMERA', color: '#ffffff'};
const PLACE = ['x', 'y', 'tx', 'ty'];

const record = value => !!value && typeof value === 'object' && !Array.isArray(value);
const finite = value => typeof value === 'number' && Number.isFinite(value);
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const number = (value, fallback, low, high) => finite(value) ? clamp(value, low, high) : fallback;
const text = (value, limit) => typeof value === 'string' ? value.trim().slice(0, limit) : '';
const color = (value, fallback) => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value.toLowerCase() : fallback;
const point = value => Array.isArray(value) && value.length === 2 && value.every(finite)
  ? [clamp(value[0], 0, 1), clamp(value[1], 0, 1)] : null;

function localFile(value) {
  return record(value) && ['input', 'output', 'temp'].includes(value.type) && typeof value.filename === 'string'
    && !['', '.', '..'].includes(value.filename) && !/[\\/:\x00]/.test(value.filename)
    && (value.subfolder === undefined || typeof value.subfolder === 'string');
}

function place(value) {
  return record(value) && PLACE.every(key => finite(value[key]))
    ? Object.fromEntries(PLACE.map(key => [key, clamp(value[key], 0, 1)])) : null;
}

function phase(value) {
  const markers = record(value?.markers) ? value.markers : {};
  return {camera: place(value?.camera), markers: Object.fromEntries(Object.entries(markers)
    .map(([key, item]) => [key, point(item)]).filter(([, item]) => item))};
}

function look(value) {
  const camera = record(value) ? value : {};
  return {fov: number(camera.fov, CAMERA_LOOK.fov, 5, 170), height: number(camera.height, CAMERA_LOOK.height, 0, 10000),
    label: text(camera.label, 40) || CAMERA_LOOK.label, color: color(camera.color, CAMERA_LOOK.color)};
}

// The box's scene map with every field present, or undefined without one; what can't be kept is dropped.
export function normalizeSceneMap(raw) {
  if (!record(raw)) return undefined;
  const ids = new Set(), markers = [];
  for (const item of Array.isArray(raw.markers) ? raw.markers : []) {
    if (!record(item) || typeof item.id !== 'string' || !item.id.trim()) continue;
    const id = item.id.trim().slice(0, 40);
    if (ids.has(id)) continue;
    ids.add(id);
    markers.push({id, label: text(item.label, 60), text: text(item.text, 3), icon: typeof item.icon === 'string' ? item.icon : 'dot',
      color: color(item.color, '#e0352b'), size: number(item.size, 1, 0.3, 4), legend: item.legend !== false,
      ...(typeof item.entity === 'string' && item.entity ? {entity: item.entity} : {}),
      ...(item.borrowed === true ? {borrowed: true} : {})});
  }
  const legend = record(raw.legend) ? raw.legend : {};
  const size = key => Number.isInteger(raw[key]) && raw[key] > 0 ? raw[key] : null;
  return {on: raw.on === true, picture: localFile(raw.picture) ? structuredClone(raw.picture) : null,
    width: size('width'), height: size('height'), markers, camera: look(raw.camera),
    opening: phase(raw.opening), end: phase(raw.end),
    absent: [...new Set((Array.isArray(raw.absent) ? raw.absent : []).filter(item => typeof item === 'string'))],
    legend: {show: legend.show !== false, position: LEGEND_POSITIONS.includes(legend.position) ? legend.position : 'bottom-left'},
    scale: number(raw.scale, 1, 0.25, 4), video_picture: raw.video_picture === true};
}

function fresh(state, index) {
  return !!state.boxes[index]?.cut
    || (tracks.enabled(state) ? tracks.previousIndex(state, index, false) === null : index === 0);
}

function mapOf(state, index) {
  const map = state.boxes[index]?.scene_map;
  return map?.on ? map : null;
}

// The clip box `index` borrows its opening from: the adjacent clip it continues, when that clip's map is on.
export function source(state, index) {
  if (!mapOf(state, index) || fresh(state, index)) return null;
  const before = tracks.previousIndex(state, index);
  return before !== null && mapOf(state, before) ? before : null;
}

function layout(shared, camera, cameraLook, positions) {
  return {version: 1, width: shared.width, height: shared.height, scale: shared.scale, legend: {...shared.legend},
    camera: camera ? {...camera, ...cameraLook} : null,
    markers: shared.markers.map(marker => ({...marker, x: positions[marker.id][0], y: positions[marker.id][1]}))};
}

// {picture, width, height, opening, end, source, owners, look} for box `index`, or null when its map is off; the
// layouts are what parseLayout reads, `owners` maps each marker id to the box whose marker list defines it.
export function resolve(state, index, memo = new Map()) {
  if (memo.has(index)) return memo.get(index);
  const map = mapOf(state, index);
  if (!map) return null;
  const before = source(state, index);
  let base;
  if (before === null) {
    base = {picture: map.picture, width: map.width, height: map.height, scale: map.scale, legend: map.legend,
      look: map.camera, camera: map.opening.camera, markers: [], positions: {}, owners: {}};
  } else {
    const previous = resolve(state, before, memo), end = previous.end;
    base = {picture: previous.picture, width: previous.width, height: previous.height, scale: end.scale,
      legend: end.legend, look: previous.look,
      camera: end.camera ? Object.fromEntries(PLACE.map(key => [key, end.camera[key]])) : null,
      markers: end.markers.filter(marker => !map.absent.includes(marker.id)).map(({x, y, ...marker}) => marker),
      positions: Object.fromEntries(end.markers.map(marker => [marker.id, [marker.x, marker.y]])),
      owners: Object.fromEntries(Object.entries(previous.owners).filter(([key]) => !map.absent.includes(key)))};
  }
  const inherited = new Set(base.markers.map(marker => marker.id));
  for (const marker of map.markers) {
    if (inherited.has(marker.id) || (before !== null && marker.borrowed)) continue;
    const {borrowed, ...own} = marker;
    base.markers.push(own);
    base.owners[marker.id] = index;
    base.positions[marker.id] = map.opening.markers[marker.id] ?? [0.5, 0.5];
  }
  const opening = base.positions;
  const closing = Object.fromEntries(Object.entries(opening).map(([key, item]) => [key, map.end.markers[key] ?? item]));
  const endCamera = map.end.camera ?? base.camera;
  const result = {picture: base.picture, width: base.width, height: base.height, source: before, owners: base.owners,
    look: base.look, opening: layout(base, base.camera, base.look, opening),
    end: layout(base, base.camera ? endCamera : null, base.look, closing)};
  memo.set(index, result);
  return result;
}

// The layout the editor shows for `phase` ('opening' or 'end'), or null when the map is off.
export function layoutFor(state, index, phaseName) {
  return resolve(state, index)?.[phaseName] ?? null;
}

function positionsOf(resolved) {
  return Object.fromEntries(resolved.markers.map(marker => [marker.id, [marker.x, marker.y]]));
}

function placeOf(camera) {
  return camera ? Object.fromEntries(PLACE.map(key => [key, camera[key]])) : null;
}

// Writes what box `index` borrows into its own fields, so a broken link falls back to the last state seen.
export function copyBorrowed(state, index) {
  const resolved = resolve(state, index);
  if (!resolved || resolved.source === null) return;
  const map = state.boxes[index].scene_map;
  map.picture = resolved.picture ? structuredClone(resolved.picture) : null;
  map.width = resolved.width;
  map.height = resolved.height;
  map.camera = {...resolved.look};
  map.legend = {...resolved.opening.legend};
  map.scale = resolved.opening.scale;
  map.markers = resolved.opening.markers.map(({x, y, ...marker}) =>
    resolved.owners[marker.id] === index ? marker : {...marker, borrowed: true});
  map.opening = {camera: placeOf(resolved.opening.camera), markers: positionsOf(resolved.opening)};
}

// copyBorrowed for every clip after box `index` that borrows along its chain.
export function refreshChain(state, index) {
  let current = index;
  for (let guard = 0; guard < state.boxes.length; guard++) {
    const after = tracks.followingIndex(state, current);
    if (after === null || source(state, after) !== current) return;
    copyBorrowed(state, after);
    current = after;
  }
}

function emptyPhase() {
  return {camera: null, markers: {}};
}

// Turns the map on: an existing map keeps its work; a new one borrows, or copies the nearest earlier map's end.
export function enable(state, index) {
  const box = state.boxes[index];
  if (box.scene_map) {
    box.scene_map.on = true;
    copyBorrowed(state, index);
    refreshChain(state, index);
    return;
  }
  box.scene_map = normalizeSceneMap({on: true});
  if (source(state, index) !== null) {
    copyBorrowed(state, index);
    return;
  }
  const indices = tracks.trackIndices(state, index);
  const earlier = indices.slice(0, indices.indexOf(index)).reverse().find(item => mapOf(state, item));
  if (earlier === undefined) return;
  const from = resolve(state, earlier), map = box.scene_map;
  Object.assign(map, {picture: from.picture ? structuredClone(from.picture) : null, width: from.width, height: from.height,
    camera: {...from.look}, legend: {...from.end.legend}, scale: from.end.scale,
    markers: from.end.markers.map(({x, y, ...marker}) => marker),
    opening: {camera: placeOf(from.end.camera), markers: positionsOf(from.end)}, end: emptyPhase()});
}

export function disable(state, index) {
  if (state.boxes[index].scene_map) state.boxes[index].scene_map.on = false;
}

// Moves a marker ({kind: 'marker', id}) or the camera ({kind: 'camera'}) in `phaseName`. `to` is {x, y} for a
// marker, any of {x, y, tx, ty} for the camera, or null to remove the camera. Opening edits of what the clip
// borrows write the previous clip's end.
export function move(state, index, phaseName, target, to) {
  const resolved = resolve(state, index);
  if (!resolved) return;
  const borrowed = phaseName === 'opening' && resolved.source !== null
    && (target.kind !== 'marker' || resolved.owners[target.id] !== index);
  const owner = borrowed ? resolved.source : index;
  const map = state.boxes[owner].scene_map;
  const field = borrowed ? 'end' : phaseName;
  map[field] ??= emptyPhase();
  if (target.kind === 'marker') {
    map[field].markers[target.id] = [clamp(to.x, 0, 1), clamp(to.y, 0, 1)];
  } else if (to === null) {
    map[field].camera = null;
  } else {
    const current = placeOf((borrowed ? resolve(state, owner).end : resolved[phaseName]).camera);
    const next = {...(current ?? {x: to.x, y: to.y, tx: to.x, ty: clamp((to.y ?? 0.5) - 0.1, 0, 1)}), ...to};
    map[field].camera = Object.fromEntries(PLACE.map(key => [key, clamp(next[key], 0, 1)]));
  }
  refreshChain(state, owner);
}

// Changes a marker's look ({label, icon, color, size, legend, text, entity}) in the clip that owns it.
export function setLook(state, index, id, patch) {
  const owner = resolve(state, index)?.owners[id];
  if (owner === undefined) return;
  const marker = state.boxes[owner].scene_map.markers.find(item => item.id === id && (item.borrowed !== true || owner === index));
  if (!marker) return;
  for (const [key, value] of Object.entries(patch)) {
    if (key === 'entity' && !value) delete marker.entity;
    else marker[key] = value;
  }
  refreshChain(state, owner);
}

// Changes what the whole chain shares ({picture, width, height, camera: look fields, legend, scale}) at its start.
export function setShared(state, index, patch) {
  let root = index;
  for (let guard = 0; guard < state.boxes.length && source(state, root) !== null; guard++) root = source(state, root);
  const map = state.boxes[root].scene_map;
  for (const [key, value] of Object.entries(patch)) {
    if (key === 'camera' || key === 'legend') map[key] = {...map[key], ...value};
    else map[key] = value;
  }
  refreshChain(state, root);
}

export function setAbsent(state, index, id, absent) {
  const map = state.boxes[index].scene_map;
  map.absent = absent ? [...new Set([...map.absent, id])] : map.absent.filter(item => item !== id);
  copyBorrowed(state, index);
  refreshChain(state, index);
}

// Adds a marker the clip owns at `at` ({x, y}); its end follows the opening until the end is edited. Returns its id.
export function addMarker(state, index, marker, at) {
  const used = new Set(state.boxes.flatMap(box => box.scene_map?.markers.map(item => item.id) ?? []));
  let count = used.size + 1;
  while (used.has(`m${count}`)) count++;
  const id = `m${count}`, map = state.boxes[index].scene_map;
  map.markers.push(normalizeSceneMap({markers: [{...marker, id}]}).markers[0]);
  map.opening.markers[id] = [clamp(at.x, 0, 1), clamp(at.y, 0, 1)];
  refreshChain(state, index);
  return id;
}

// Removes a marker the clip owns; an inherited marker is left out with setAbsent instead.
export function removeMarker(state, index, id) {
  const map = state.boxes[index].scene_map;
  if (resolve(state, index)?.owners[id] !== index) return;
  map.markers = map.markers.filter(item => item.id !== id);
  delete map.opening.markers[id];
  delete map.end.markers[id];
  refreshChain(state, index);
}
