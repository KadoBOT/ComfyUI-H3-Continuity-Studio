import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as model from '../../web/h3c_timeline_model.mjs';
import * as maps from '../../web/h3c_scene_maps.mjs';

const cases = JSON.parse(readFileSync(new URL('../fixtures/scene_maps/linking.json', import.meta.url), 'utf8'));
const fixture = name => model.parseState(JSON.stringify(cases.find(item => item.name === name).timeline));

function positions(layout) {
  const camera = layout.camera;
  return {camera: camera ? [camera.x, camera.y, camera.tx, camera.ty] : null,
    markers: Object.fromEntries(layout.markers.map(marker => [marker.id, [marker.x, marker.y]]))};
}

function opening(state, index) {
  return positions(maps.resolve(state, index).opening);
}

test('resolve matches Python on every shared fixture case', () => {
  for (const item of cases) {
    const state = model.parseState(JSON.stringify(item.timeline));
    for (const want of item.expect) {
      const got = maps.resolve(state, want.index), name = `${item.name} clip ${want.index + 1}`;
      assert.equal(got.source, want.source, name);
      assert.deepEqual(got.opening.markers.map(marker => marker.id), want.markers, name);
      assert.deepEqual(positions(got.opening), want.opening, name);
      assert.deepEqual(positions(got.end), want.end, name);
    }
  }
});

test('moving a borrowed opening marker writes the previous clip end and refreshes the copy', () => {
  const state = fixture('continuous_borrows');
  maps.move(state, 1, 'opening', {kind: 'marker', id: 'm1'}, {x: 0.45, y: 0.35});
  assert.deepEqual(state.boxes[0].scene_map.end.markers.m1, [0.45, 0.35]);
  assert.deepEqual(opening(state, 1).markers.m1, [0.45, 0.35]);
  assert.deepEqual(state.boxes[1].scene_map.opening.markers.m1, [0.45, 0.35]);
  assert.equal(state.boxes[1].scene_map.markers.find(marker => marker.id === 'm1').borrowed, true);
});

test('moving the borrowed opening camera writes the previous clip end camera', () => {
  const state = fixture('continuous_borrows');
  maps.move(state, 1, 'opening', {kind: 'camera'}, {tx: 0.6, ty: 0.3});
  assert.deepEqual(state.boxes[0].scene_map.end.camera, {x: 0.5, y: 0.9, tx: 0.6, ty: 0.3});
  assert.deepEqual(opening(state, 1).camera, [0.5, 0.9, 0.6, 0.3]);
});

test('own markers and end edits stay in the clip', () => {
  const state = fixture('continuous_borrows');
  maps.move(state, 1, 'opening', {kind: 'marker', id: 'm9'}, {x: 0.7, y: 0.7});
  maps.move(state, 1, 'end', {kind: 'marker', id: 'm1'}, {x: 0.1, y: 0.1});
  assert.deepEqual(state.boxes[1].scene_map.opening.markers.m9, [0.7, 0.7]);
  assert.deepEqual(state.boxes[1].scene_map.end.markers.m1, [0.1, 0.1]);
  assert.deepEqual(positions(maps.resolve(state, 0).end).markers.m1, [0.3, 0.4]);
});

test('a cut after refreshChain keeps the last borrowed opening', () => {
  const state = fixture('continuous_borrows');
  maps.move(state, 1, 'opening', {kind: 'marker', id: 'm1'}, {x: 0.45, y: 0.35});
  const before = opening(state, 1);
  state.boxes[1].cut = true;
  assert.equal(maps.resolve(state, 1).source, null);
  assert.deepEqual(opening(state, 1), before);
  assert.equal(maps.resolve(state, 1).picture.filename, 'yard.png');
});

test('setAbsent on clip 2 removes the marker from clips 2 and 3 only', () => {
  const state = model.parseState(JSON.stringify(cases.find(item => item.name === 'absent_propagates').timeline));
  state.boxes[1].scene_map.absent = [];
  maps.setAbsent(state, 1, 'm2', true);
  const ids = index => maps.resolve(state, index).opening.markers.map(marker => marker.id);
  assert.deepEqual([ids(0), ids(1), ids(2)], [['m1', 'm2'], ['m1'], ['m1']]);
  maps.setAbsent(state, 1, 'm2', false);
  assert.deepEqual(ids(2), ['m1', 'm2']);
});

test('removing a marker upstream removes the borrowed copies downstream', () => {
  const state = fixture('absent_propagates');
  maps.refreshChain(state, 0);
  maps.setAbsent(state, 1, 'm2', false);
  maps.removeMarker(state, 0, 'm2');
  assert.deepEqual(maps.resolve(state, 2).opening.markers.map(marker => marker.id), ['m1']);
  state.boxes[2].cut = true;
  assert.deepEqual(maps.resolve(state, 2).opening.markers.map(marker => marker.id), ['m1']);
});

test('setLook on an inherited marker writes its owner and reaches every borrowing clip', () => {
  const state = fixture('absent_propagates');
  maps.setLook(state, 2, 'm1', {label: 'THE STRAY', entity: 'e1'});
  assert.equal(state.boxes[0].scene_map.markers[0].label, 'THE STRAY');
  assert.equal(maps.resolve(state, 2).opening.markers[0].label, 'THE STRAY');
  assert.equal(maps.resolve(state, 2).opening.markers[0].entity, 'e1');
});

test('setShared on a borrowing clip writes the start of its chain', () => {
  const state = fixture('absent_propagates');
  maps.setShared(state, 2, {picture: {type: 'input', subfolder: 'maps', filename: 'new.png'}, width: 800, height: 600,
    camera: {fov: 40}});
  assert.equal(state.boxes[0].scene_map.picture.filename, 'new.png');
  assert.equal(state.boxes[0].scene_map.camera.fov, 40);
  const got = maps.resolve(state, 2);
  assert.deepEqual([got.picture.filename, got.width, got.opening.camera.fov], ['new.png', 800, 40]);
});

test('addMarker gives a fresh id and the end follows the opening until edited', () => {
  const state = fixture('continuous_borrows');
  const id = maps.addMarker(state, 1, {label: 'NEW', icon: 'flag'}, {x: 0.25, y: 0.75});
  assert.ok(!['m1', 'm2', 'm9'].includes(id));
  assert.deepEqual(positions(maps.resolve(state, 1).end).markers[id], [0.25, 0.75]);
});

test('enable after a cut copies the nearest earlier map end positions', () => {
  const state = fixture('single_clip');
  state.boxes.push({id: 'b', frames: 39, prompt: 'y', cut: true, first: '', last: ''});
  maps.enable(state, 1);
  const map = state.boxes[1].scene_map;
  assert.equal(map.on, true);
  assert.equal(map.picture.filename, 'yard.png');
  assert.deepEqual(opening(state, 1), positions(maps.resolve(state, 0).end));
  assert.ok(map.markers.every(marker => !marker.borrowed));
  assert.equal(maps.resolve(state, 1).source, null);
});

test('enable on a continuing clip borrows and keeps a copy', () => {
  const state = fixture('single_clip');
  state.boxes.push({id: 'b', frames: 34, prompt: 'y', cut: false, first: '', last: ''});
  maps.enable(state, 1);
  assert.equal(maps.resolve(state, 1).source, 0);
  assert.deepEqual(state.boxes[1].scene_map.opening.markers, {m1: [0.3, 0.4], m2: [0.6, 0.5]});
});

test('enable with no earlier map starts empty with no picture, and disable keeps the work', () => {
  const state = model.parseState(JSON.stringify({version: 1, prompt: '', boxes: [{id: 'a', frames: 39, prompt: 'x'}]}));
  maps.enable(state, 0);
  assert.equal(state.boxes[0].scene_map.picture, null);
  assert.deepEqual(state.boxes[0].scene_map.markers, []);
  maps.addMarker(state, 0, {label: 'A'}, {x: 0.5, y: 0.5});
  maps.disable(state, 0);
  assert.equal(state.boxes[0].scene_map.on, false);
  assert.equal(state.boxes[0].scene_map.markers.length, 1);
  assert.equal(maps.resolve(state, 0), null);
});

test('layoutFor returns a parseLayout-compatible layout for each phase', () => {
  const state = fixture('single_clip');
  const layout = maps.layoutFor(state, 0, 'end');
  assert.deepEqual([layout.width, layout.height, layout.camera.fov, layout.markers[0].x], [2000, 1000, 55, 0.3]);
});

test('scene_map survives normalize and serialize and adds scene-map-1 only when on', () => {
  const state = fixture('single_clip');
  const saved = JSON.parse(model.serialize(state));
  assert.deepEqual(saved.requires, ['scene-map-1']);
  assert.equal(saved.boxes[0].scene_map.markers[1].label, 'OUTCAST');
  maps.disable(state, 0);
  const off = JSON.parse(model.serialize(state));
  assert.equal(off.requires, undefined);
  assert.equal(off.boxes[0].scene_map.on, false);
  assert.ok(model.OWN_FEATURES.includes('scene-map-1'));
});

test('normalizeSceneMap drops what cannot be kept', () => {
  const map = maps.normalizeSceneMap({on: true, picture: {type: 'input', filename: '../x.png'},
    markers: [{id: 'a'}, {id: 'a'}, {label: 'no id'}, 'junk'], opening: {markers: {a: [2, -1], b: 'x'}}});
  assert.equal(map.picture, null);
  assert.deepEqual(map.markers.map(marker => marker.id), ['a']);
  assert.deepEqual(map.opening.markers, {a: [1, 0]});
  assert.equal(map.video_picture, false);
});

test('a timeline without scene_map serializes without any scene map trace', () => {
  const text = JSON.stringify({version: 1, prompt: '', boxes: [{id: 'a', frames: 39, prompt: 'x'}]});
  const saved = model.serialize(model.parseState(text));
  assert.ok(!saved.includes('scene_map') && !saved.includes('scene-map-1'));
});
