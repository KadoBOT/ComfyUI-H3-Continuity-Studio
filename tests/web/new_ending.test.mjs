import test from 'node:test';
import assert from 'node:assert/strict';
import {buttonNamed, findAll, installDom} from './fake_dom.mjs';

installDom();
const element = Object.getPrototypeOf(document.createElement('div'));
element.getBoundingClientRect ??= () => ({left: 0, top: 0, right: 900, bottom: 100, width: 900, height: 100});
if (!('validity' in element)) Object.defineProperty(element, 'validity', {get: () => ({valid: true})});
element.querySelectorAll ??= () => [];
element.querySelector ??= () => null;
element.setCustomValidity ??= () => {};
element.pause ??= () => {};
element.load ??= () => {};
element.play ??= () => Promise.resolve();
const {TimelineEditor} = await import('../../web/h3c_timeline_editor.mjs');

// Clip 2 continues from clip 1.
const CHAIN = {version: 1, prompt: '', boxes: [{id: 'a', frames: 49, exact: true, prompt: 'Wide.', seed: 3, cut: false},
  {id: 'b', frames: 49, exact: true, prompt: 'On.', seed: 4, cut: false}]};
const HINT = /Ctrl\+click \(⌘\+click on Mac\)/;

// The real editor; `preflight` records whether Generate asked for a new ending.
function open(statuses = ['done', 'done'], doc = CHAIN) {
  const host = {text: JSON.stringify(doc), read() { return this.text; }, write(value) { this.text = value; },
    context: () => 39, connected: () => ({images: [], audios: []}), viewUrl: (file) => `/view?filename=${file.filename}`,
    changed() {}, asked: [], async preflight(box, count, rebuild) { this.asked.push(rebuild); return {cancelled: true}; },
    async queue() {}};
  const editor = new TimelineEditor(host);
  editor.setStatus({ok: true, message: '', boxes: statuses.map((status, index) => ({id: CHAIN.boxes[index].id, status}))});
  return editor;
}

async function press(editor, keys = {}) {
  editor.boxRenderButton.dispatchEvent({type: 'click', bubbles: true, button: 0, preventDefault() {},
    stopPropagation() {}, ...keys});
  await new Promise((resolve) => setImmediate(resolve));
  return editor.host.asked.at(-1);
}

test('Generate keeps the ending; Ctrl or ⌘ makes a new one', async () => {
  const editor = open();
  assert.equal(await press(editor), false);
  assert.equal(await press(editor, {ctrlKey: true}), true);
  assert.equal(await press(editor, {metaKey: true}), true);
});

test('the clip panel has no separate rebuild button', () => {
  const labels = findAll(open().panelEl, (node) => node.tagName === 'BUTTON')
    .map((node) => node.textContent);
  assert.equal(labels.includes('Rebuild continuity'), false);
});

test('the Generate tooltip offers a new ending only when the next clip has a take that continues this one', () => {
  assert.match(open().boxRenderButton.title, HINT);
  assert.doesNotMatch(open(['done', 'next']).boxRenderButton.title, HINT);
  const last = open();
  last.select(1);
  assert.doesNotMatch(last.boxRenderButton.title, HINT);
});

test("Ctrl on a clip's other video renders it without asking for a new ending", async () => {
  const doc = structuredClone(CHAIN);
  Object.assign(doc, {requires: ['video-layers-1']});
  Object.assign(doc.boxes[0], {layers: [{id: 'a1', seed: 5, prompt: 'Close.', first: '', last: '', previews: [],
    memory: 'off', memories: [], dialogue: 'cues'}], switch: {cuts: [{at: 22, to: 'a1'}], fade: 6, sound: 'screen'}});
  doc.boxes[1].cut = true;
  const editor = open(undefined, doc);
  buttonNamed(editor.regions().videoPicker, '1b').click();
  assert.equal(await press(editor, {ctrlKey: true}), false);
});
