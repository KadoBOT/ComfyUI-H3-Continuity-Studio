import assert from 'node:assert/strict';
import test from 'node:test';
import {findAll, installDom} from './fake_dom.mjs';

installDom();
const context = new Proxy(function () {}, {get: (target, key) => key === 'measureText' ? () => ({width: 10}) : context, apply: () => context});
const create = document.createElement;
document.createElement = tag => Object.assign(create(tag), {
  getContext: () => context, getBoundingClientRect: () => ({left: 0, top: 0, width: 200, height: 100}), focus() {},
});
globalThis.window = {devicePixelRatio: 1};
globalThis.Image = class { set src(value) { this.url = value; } };
const {SceneMapEditor} = await import('../../web/h3c_scene_map_editor.mjs');

const api = {apiURL: path => path, fetchApi: async () => ({json: async () => ({images: ['maps/yard.png']})})};
const LAYOUT = {width: 2000, height: 1000, markers: [{id: 'm7', x: 0.2, y: 0.5, label: 'STRAY'}],
  camera: {x: 0.5, y: 0.9, tx: 0.5, ty: 0.4}};
const press = (x, y) => ({button: 0, clientX: x, clientY: y, pointerId: 1, preventDefault() {}, stopPropagation() {}});

function editor(options = {}) {
  const reported = [];
  const made = new SceneMapEditor({api, layout: LAYOUT, onLayout: layout => reported.push(layout), ...options});
  return {made, reported};
}

test('an edit reports the whole layout with marker ids kept', () => {
  const {made, reported} = editor();
  const legend = findAll(made.root, node => node.tagName === 'INPUT' && node.type === 'checkbox')[0];
  legend.checked = false;
  legend.fire('change');
  assert.equal(reported.length, 1);
  assert.equal(reported[0].legend.show, false);
  assert.deepEqual(reported[0].markers.map(marker => marker.id), ['m7']);
});

test('setLayout replaces the layout silently and keeps the selected marker', () => {
  const {made, reported} = editor();
  made.select({kind: 'marker', index: 0});
  made.setLayout({...LAYOUT, markers: [{id: 'm1', x: 0.9, y: 0.1}, {id: 'm7', x: 0.3, y: 0.3}]},
    {notice: 'Shared with clip 1\'s end', ghost: LAYOUT});
  assert.equal(reported.length, 0);
  assert.deepEqual(made.selected, {kind: 'marker', index: 1});
  assert.equal(made.notice.textContent, 'Shared with clip 1\'s end');
  assert.equal(made.ghost.markers[0].id, 'm7');
  made.setLayout(LAYOUT, {notice: ''});
  assert.equal(made.notice.textContent, '');
});

test('decorate adds to the marker panel of the selected marker', () => {
  const seen = [];
  const {made} = editor({decorate: (panel, marker) => { seen.push(marker.id); panel.append(document.createElement('select')); }});
  made.select({kind: 'marker', index: 0});
  assert.deepEqual(seen, ['m7']);
  assert.equal(findAll(made.panel, node => node.tagName === 'SELECT').length, 1);
});

test('a new marker takes its id from markerId', () => {
  const {made, reported} = editor({markerId: () => 'm42'});
  made.mode = 'marker';
  made.pointerDown(press(150, 20));
  made.pointerUp(press(150, 20));
  assert.deepEqual(reported.at(-1).markers.map(marker => marker.id), ['m7', 'm42']);
});

test('choosing a picture reports it; setImage does not', () => {
  const names = [];
  const {made} = editor({onImage: name => names.push(name)});
  made.setImage('maps/a.png');
  assert.deepEqual(names, []);
  made.chooseImage('maps/b.png');
  assert.deepEqual(names, ['maps/b.png']);
  assert.equal(made.image, 'maps/b.png');
});
