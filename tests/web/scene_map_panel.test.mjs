import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as model from '../../web/h3c_timeline_model.mjs';
import * as maps from '../../web/h3c_scene_maps.mjs';
import {parseLayout} from '../../web/h3c_scene_map_model.mjs';
import {applyLayout, panelState, pictureName, promptText} from '../../web/h3c_scene_map_panel.mjs';

const cases = JSON.parse(readFileSync(new URL('../fixtures/scene_maps/linking.json', import.meta.url), 'utf8'));
const fixture = name => model.parseState(JSON.stringify(cases.find(item => item.name === name).timeline));
const preview = (mode, reason = '', parts = {}) => ({video: {mode, reason, parts: {blocking: '', definition: '',
  retention: '', slot: '', reason, ...parts}}, stills: {}});
// What the editor hands back: the layout it was shown, parsed, after `change`.
const edited = (state, index, phase, change) => {
  const layout = parseLayout(maps.layoutFor(state, index, phase));
  change(layout);
  return JSON.parse(JSON.stringify(layout));
};

test('panelState: a clip continuing a mapped clip is linked to it', () => {
  const state = fixture('continuous_borrows');
  assert.equal(panelState(state, 1, null).linkedTo, 1);
  assert.equal(panelState(state, 0, null).linkedTo, null);
  assert.equal(panelState(state, 0, null).on, true);
});

test('panelState: a Ref2VA clip can send the picture unless it already sends nine', () => {
  const state = fixture('single_clip');
  assert.deepEqual([panelState(state, 0, preview('ref2va')).canSendPicture, panelState(state, 0, preview('ref2va')).sendVisible],
    [true, true]);
  const full = panelState(state, 0, preview('ref2va', 'This clip already sends 9 pictures, so the map goes in as text only.'));
  assert.equal(full.canSendPicture, false);
  assert.equal(full.sendReason, 'This clip already sends 9 pictures, so the map goes in as text only.');
});

test('panelState: a T2VA clip hides the picture switch', () => {
  const got = panelState(fixture('single_clip'), 0, preview('t2va'));
  assert.deepEqual([got.sendVisible, got.canSendPicture], [false, false]);
});

test('panelState: a multi-shot prompt gets the first-shot note', () => {
  const state = fixture('single_clip');
  assert.equal(panelState(state, 0, null).multiShot, false);
  state.boxes[0].prompt = '[Shot 1] Wide.\n[Shot 2] Close.';
  assert.equal(panelState(state, 0, null).multiShot, true);
});

test('applyLayout: an opening drag on a linked clip moves the previous clip end', () => {
  const state = fixture('continuous_borrows');
  assert.equal(applyLayout(state, 1, 'opening', edited(state, 1, 'opening', layout => { layout.markers[0].x = 0.45; })), true);
  assert.equal(state.boxes[0].scene_map.end.markers.m1[0], 0.45);
  assert.equal(maps.layoutFor(state, 1, 'opening').markers[0].x, 0.45);
});

test('applyLayout: the same layout changes nothing', () => {
  const state = fixture('continuous_borrows'), before = JSON.stringify(state.boxes);
  assert.equal(applyLayout(state, 1, 'end', edited(state, 1, 'end', () => {})), false);
  assert.equal(JSON.stringify(state.boxes), before);
});

test('applyLayout: a new marker, a look change and a removal', () => {
  const state = fixture('single_clip');
  const id = maps.nextMarkerId(state);
  applyLayout(state, 0, 'opening', edited(state, 0, 'opening', layout => {
    layout.markers.push({...layout.markers[0], id, x: 0.9, y: 0.1, label: 'NEW'});
  }));
  const added = maps.layoutFor(state, 0, 'opening').markers.find(marker => marker.id === id);
  assert.deepEqual([added.label, added.x, added.y], ['NEW', 0.9, 0.1]);
  applyLayout(state, 0, 'end', edited(state, 0, 'end', layout => { layout.markers.find(marker => marker.id === id).color = '#3a86ff'; }));
  assert.equal(state.boxes[0].scene_map.markers.find(marker => marker.id === id).color, '#3a86ff');
  applyLayout(state, 0, 'opening', edited(state, 0, 'opening', layout => { layout.markers = layout.markers.filter(marker => marker.id !== id); }));
  assert.equal(state.boxes[0].scene_map.markers.some(marker => marker.id === id), false);
});

test('applyLayout: removing an inherited marker leaves it out of this clip only', () => {
  const state = fixture('continuous_borrows');
  applyLayout(state, 1, 'opening', edited(state, 1, 'opening', layout => { layout.markers = layout.markers.filter(marker => marker.id !== 'm1'); }));
  assert.deepEqual(state.boxes[1].scene_map.absent, ['m1']);
  assert.ok(maps.layoutFor(state, 0, 'end').markers.some(marker => marker.id === 'm1'));
});

test('applyLayout: camera look, legend and size go to the start of the chain', () => {
  const state = fixture('continuous_borrows');
  applyLayout(state, 1, 'end', edited(state, 1, 'end', layout => {
    layout.camera.fov = 70; layout.legend.position = 'top-right'; layout.width = 1600; layout.height = 900;
  }));
  const root = state.boxes[0].scene_map;
  assert.deepEqual([root.camera.fov, root.legend.position, root.width, root.height], [70, 'top-right', 1600, 900]);
  assert.equal(maps.layoutFor(state, 1, 'end').camera.fov, 70);
});

test('applyLayout: a camera dragged on the end tab stays in this clip', () => {
  const state = fixture('single_clip');
  applyLayout(state, 0, 'end', edited(state, 0, 'end', layout => { layout.camera.tx = 0.1; }));
  assert.equal(state.boxes[0].scene_map.end.camera.tx, 0.1);
  assert.notEqual(maps.layoutFor(state, 0, 'opening').camera.tx, 0.1);
});

test('pictureName and promptText', () => {
  assert.equal(pictureName({type: 'input', subfolder: 'maps', filename: 'yard.png'}), 'maps/yard.png');
  assert.equal(pictureName({type: 'input', subfolder: '', filename: 'yard.png'}), 'yard.png');
  assert.equal(pictureName(null), '');
  const text = promptText({video: {mode: 'ref2va', reason: '', parts: {blocking: 'B.', definition: 'D.', retention: 'R.',
    slot: 'image19', reason: ''}}, stills: {first: 'F.', last: 'L.'}});
  assert.equal(text, 'Video\nD.\nR.\nB.\n\nFirst-frame still\nF.\n\nLast-frame still\nL.');
  assert.equal(promptText(preview('ref2va', 'This clip continues the previous one.')),
    'Video\nNothing: This clip continues the previous one.');
});
