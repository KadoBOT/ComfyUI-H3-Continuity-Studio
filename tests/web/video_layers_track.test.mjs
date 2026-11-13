import test from 'node:test';
import assert from 'node:assert/strict';
import {findAll, installDom} from './fake_dom.mjs';

installDom();
const element = Object.getPrototypeOf(document.createElement('div'));
element.getBoundingClientRect ??= () => ({left: 0, top: 0, right: 900, bottom: 100, width: 900, height: 100});
if (!('validity' in element)) Object.defineProperty(element, 'validity', {get: () => ({valid: true})});
const {TimelineEditor} = await import('../../web/h3c_timeline_editor.mjs');

const LAYER = {id: 'b2v1', seed: 5101, prompt: 'Close.', first: '', last: '', previews: [], memory: 'off', memories: [],
  dialogue: 'cues'};
// Shot 02: one 90-frame clip whose second video takes over at frame 27 with a 6-frame fade.
const SHOT = {version: 1, prompt: '', requires: ['video-layers-1'], boxes: [{id: 'b2', frames: 90, exact: true,
  prompt: 'Wide.', seed: 1, cut: false, layers: [LAYER], switch: {cuts: [{at: 27, to: 'b2v1'}], fade: 6, sound: 'screen'}}]};

// The real editor on the fake DOM; the clip panel isn't drawn (its own tests cover it).
function open(doc = SHOT) {
  const host = {text: JSON.stringify(doc), read() { return this.text; }, write(value) { this.text = value; },
    context: () => 39, connected: () => ({images: [], audios: []}), viewUrl: (file) => `/view?filename=${file.filename}`,
    changed() {}};
  return new (class extends TimelineEditor { renderPanel() {} })(host);
}

const byClass = (root, name) => findAll(root, (node) => node.classList?.contains(name));

test('status line with layers', () => {
  assert.equal(open().summaryEl.textContent, '1 clip · on screen 3.8 s · renders 7.5 s');
});

test('status line without layers is unchanged', () => {
  const plain = structuredClone(SHOT);
  delete plain.boxes[0].layers;
  delete plain.boxes[0].switch;
  plain.requires = [];
  assert.equal(open(plain).summaryEl.textContent, '1 clip · 3.8 s');
});

test('badge and stripes', () => {
  const editor = open();
  const [clip] = byClass(editor.trackEl, 'h3ct-box');
  assert.equal(byClass(clip, 'h3ct-stack-badge')[0]?.textContent, '▤ 2');
  const stripes = byClass(clip, 'h3ct-stripe');
  assert.equal(stripes.length, 2);
  assert.equal(stripes[0].parentNode.classList.contains('h3ct-stripes'), true);
  const [main] = byClass(stripes[0], 'on'), [layer] = byClass(stripes[1], 'on');
  assert.deepEqual([main.style.left, main.style.width], ['0.000%', '30.000%']);
  assert.deepEqual([layer.style.left, layer.style.width], ['30.000%', '70.000%']);
});

test('a clip with one video has no badge or stripes', () => {
  const plain = structuredClone(SHOT);
  delete plain.boxes[0].layers;
  delete plain.boxes[0].switch;
  const [clip] = byClass(open(plain).trackEl, 'h3ct-box');
  assert.equal(byClass(clip, 'h3ct-stack-badge').length + byClass(clip, 'h3ct-stripes').length, 0);
});

test('Last caption names the closing video', () => {
  const editor = open();
  const last = findAll(editor.stillsEl, (node) => node.dataset?.target === 'last')[0];
  assert.match(last.textContent, /under 1b/);
  const first = findAll(editor.stillsEl, (node) => node.dataset?.target === 'first')[0];
  assert.doesNotMatch(first.textContent, /under/);
});

test('Render remaining counts videos', () => {
  const editor = open();
  assert.equal(editor.renderButton.textContent, '▶ Render 2 remaining', 'before a status: the clip and its video');
  editor.setStatus({ok: true, message: '', boxes: [{id: 'b2', status: 'done', videos: [{id: 'b2v1', status: 'next'}]}],
    layers_remaining: 1});
  assert.equal(editor.renderButton.textContent, '▶ Render 1 remaining');
  assert.equal(editor.nextBox(), 1, 'the run after the clip is its video');
  editor.setStatus({ok: true, message: '', boxes: [{id: 'b2', status: 'done', videos: [{id: 'b2v1', status: 'done'}]}],
    layers_remaining: 0});
  assert.equal(editor.renderButton.textContent, '✓ All rendered');
  assert.equal(editor.nextBox(), null);
});
