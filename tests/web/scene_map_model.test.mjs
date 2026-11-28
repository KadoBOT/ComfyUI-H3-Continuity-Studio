import test from 'node:test';
import assert from 'node:assert/strict';
import {ICONS} from '../../web/h3c_scene_map_icons.mjs';
import {addMarker, cone, heading, hitTest, iconNames, legendRows, parseLayout, placeCamera, serializeLayout, unit} from '../../web/h3c_scene_map_model.mjs';

const W = 2000, H = 1123;
const shot22 = () => parseLayout({width: W, height: H,
  camera: {x: 1368 / W, y: 928 / H, tx: 879 / W, ty: 440 / H, fov: 55, height: 0.5, label: 'CAMERA'},
  markers: [{label: 'WOUNDED GRAZER', icon: 'target', color: '#E0352B', x: 879 / W, y: 440 / H},
    {label: 'STRAY', icon: 'person', color: '#ff7a1a', x: 733 / W, y: 640 / H}]});

test('parseLayout fills defaults and clamps bad values', () => {
  const layout = parseLayout('{"scale": 99, "legend": {"position": "middle"}, "markers": [{"x": 3, "y": -1, "icon": "nope", "color": "red", "size": 0}, 5],'
    + '"camera": {"fov": 400}}');
  assert.equal(layout.scale, 4);
  assert.deepEqual(layout.legend, {show: true, position: 'bottom-left'});
  assert.equal(layout.markers.length, 1);
  assert.deepEqual([layout.markers[0].x, layout.markers[0].y, layout.markers[0].icon, layout.markers[0].color, layout.markers[0].size],
    [1, 0, 'dot', '#e0352b', 0.3]);
  assert.equal(layout.camera.fov, 170);
  assert.equal(layout.camera.label, 'CAMERA');
  assert.deepEqual(parseLayout('not json'), parseLayout(''));
  assert.deepEqual(parseLayout(serializeLayout(shot22())), shot22());
});

test('legend rows skip unlabelled and repeated markers and describe the camera arrow', () => {
  const layout = shot22();
  addMarker(layout, 0.1, 0.1);
  layout.markers.push({...layout.markers[1], id: 'copy'});
  assert.deepEqual(legendRows(layout).map(row => row.text),
    ['WOUNDED GRAZER', 'STRAY', 'CAMERA · tip = lens, 0.5 m above ground, 55° view']);
  assert.equal(legendRows(layout)[0].color, '#e0352b');
});

test('the view cone starts at the camera and is centred on its aim', () => {
  const layout = shot22(), camera = layout.camera;
  const points = cone(camera, W, H, 1, 2);
  assert.deepEqual(points[0], [1368, 928]);
  const middle = points[2], angle = heading(camera, W, H);
  assert.ok(Math.abs(Math.atan2(middle[1] - 928, middle[0] - 1368) - angle) < 1e-9);
  assert.ok(Math.abs(middle[0] - 879) < 1e-6 && Math.abs(middle[1] - 440) < 1e-6);
});

test('hitTest finds the aim ring, the arrow behind the lens and the topmost marker', () => {
  const layout = shot22(), r = unit(layout, W, H), camera = layout.camera;
  layout.camera.tx = 0.9;
  layout.camera.ty = 0.1;
  assert.deepEqual(hitTest(layout, W, H, 0.9 * W, 0.1 * H), {kind: 'target'});
  const angle = heading(camera, W, H);
  assert.deepEqual(hitTest(layout, W, H, 1368 - Math.cos(angle) * r * 3, 928 - Math.sin(angle) * r * 3), {kind: 'camera'});
  assert.equal(hitTest(layout, W, H, 1368 + Math.cos(angle) * r * 3, 928 + Math.sin(angle) * r * 3), null);
  layout.markers.push({...layout.markers[1], id: 'top'});
  assert.deepEqual(hitTest(layout, W, H, 733, 640), {kind: 'marker', index: 2});
  assert.equal(hitTest(layout, W, H, 50, 50), null);
});

test('addMarker gives a fresh id and placeCamera keeps the camera settings', () => {
  const layout = parseLayout({markers: [{id: 'm2'}]});
  assert.equal(addMarker(layout, 0.2, 0.3, {icon: 'paw', color: '#7b4bd6'}), 1);
  assert.deepEqual(layout.markers[1], {id: 'm3', x: 0.2, y: 0.3, icon: 'paw', color: '#7b4bd6', size: 1, label: '', text: '', legend: true});
  placeCamera(layout, 0.5, 0.8);
  assert.deepEqual([layout.camera.tx, layout.camera.ty], [0.5, 0.55]);
  layout.camera.fov = 30;
  placeCamera(layout, 0.5, 0, 0.5, 0);
  assert.equal(layout.camera.fov, 30);
  assert.deepEqual([layout.camera.tx, layout.camera.ty], [0.5, 0.25]);
  placeCamera(layout, 0.2, 0.2, 0.6, 0.7);
  assert.deepEqual([layout.camera.x, layout.camera.y, layout.camera.tx, layout.camera.ty], [0.2, 0.2, 0.6, 0.7]);
});

test('every icon is listed with its name', () => {
  assert.deepEqual(iconNames().map(icon => icon.key), Object.keys(ICONS));
  assert.ok(iconNames().every(icon => typeof icon.name === 'string' && icon.name));
});
