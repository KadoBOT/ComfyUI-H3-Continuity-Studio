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
const pointer = (type, clientX) => ({type, button: 0, pointerId: 1, clientX, bubbles: false, preventDefault() {},
  stopPropagation() {}});

// Shot 02 followed by a plain Cut clip, or a clip with `count` other videos swapping in at `cuts`.
function withClips(changes = {}, follower = true) {
  const doc = structuredClone(SHOT);
  Object.assign(doc.boxes[0], changes);
  if (follower) doc.boxes.push({id: 'c3', frames: 48, exact: true, prompt: 'Street.', seed: 2, cut: true});
  return doc;
}
function stacked(count, cuts, frames = 90) {
  const layers = Array.from({length: count}, (_, i) => ({...LAYER, id: `b2v${i + 1}`, seed: 5101 + i}));
  return withClips({frames, layers, switch: {cuts: cuts.map((at, i) => ({at, to: layers[i].id})), fade: 6,
    sound: 'screen'}}, false);
}

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

test('selected stack expands into one row per video', () => {
  const editor = open(withClips());
  const rows = byClass(editor.stackEl, 'h3ct-stack-row');
  assert.equal(editor.stackEl.hidden, false);
  assert.deepEqual(rows.map((row) => row.dataset.video), ['b2', 'b2v1']);
  assert.match(rows[0].textContent, /1 · main/);
  assert.match(rows[0].textContent, /First and Last: marker row ↑/);
  assert.equal(byClass(rows[0], 'h3ct-edge').length, 0, "the main video's tiles stay in the marker row");
  const [bar] = byClass(rows[0], 'h3ct-onscreen');
  assert.deepEqual([bar.style.left, bar.style.width], ['0.000%', '30.000%']);
  const area = byClass(editor.stackEl, 'h3ct-stack-rows')[0];
  assert.deepEqual([area.style.marginLeft, area.style.width], [editor.trackEl.children[0].style.left,
    editor.trackEl.children[0].style.width], 'the rows sit inside the clip’s own time');
  const track = editor.trackEl.children.map((node) => [node.style.left, node.style.width]);
  editor.select(1);
  assert.equal(editor.stackEl.hidden, true, 'a clip with one video draws no rows');
  assert.deepEqual(editor.trackEl.children.map((node) => [node.style.left, node.style.width]), track);
});

test('layer rows carry their First and Last tiles', () => {
  const editor = open();
  const [, row] = byClass(editor.stackEl, 'h3ct-stack-row');
  const edges = byClass(row, 'h3ct-edge');
  assert.deepEqual(edges.map((edge) => [edge.classList.contains('first'), edge.classList.contains('last')]),
    [[true, false], [false, true]]);
  assert.match(edges[0].textContent, /1b · First/);
  assert.equal(byClass(row, 'h3ct-stack-heading')[0].textContent, '1b not rendered');
  editor.setStatus({ok: true, message: '', boxes: [{id: 'b2', status: 'done', videos: [{id: 'b2v1', status: 'done'}]}]});
  const [, rendered] = byClass(editor.stackEl, 'h3ct-stack-row');
  assert.equal(byClass(rendered, 'h3ct-stack-heading')[0].textContent, '1b ✓ seed 5101');
});

test("a layer's Shot guide is a tick on its bar", () => {
  const guide = {filename: 'shot.png', subfolder: 'h3_previews', type: 'output'};
  const editor = open(withClips({layers: [{...LAYER, previews: [{target: {kind: 'shot', shot: 2}, frame: 50, guide}]}]}));
  const [, row] = byClass(editor.stackEl, 'h3ct-stack-row');
  const [tick] = byClass(row, 'h3ct-shot-tick');
  assert.equal(tick.style.left, '55.556%');
});

test('dragging a swap snaps to a beat', () => {
  const editor = open();
  editor.audioLanes.beatFrames = () => [30];
  editor.audioLanes.snapInput.checked = true;
  const [swap] = byClass(editor.stackEl, 'h3ct-swap');
  assert.equal(swap.dataset.cut, '0');
  assert.equal(byClass(swap, 'h3ct-swap-chip')[0].textContent, '27 · fade 6');
  swap.dispatchEvent(pointer('pointerdown', 270));
  editor.stackEl.dispatchEvent(pointer('pointermove', 290));
  editor.stackEl.dispatchEvent(pointer('pointerup', 290));
  assert.equal(editor.state.boxes[0].switch.cuts[0].at, 30);
  assert.equal(JSON.parse(editor.host.text).boxes[0].switch.cuts[0].at, 30, 'the drag is saved');
  assert.equal(byClass(byClass(editor.stackEl, 'h3ct-swap')[0], 'h3ct-swap-chip')[0].textContent, '30 · fade 6');
});

test('+ Video asks before turning a Continue into a Cut', () => {
  const doc = {version: 1, prompt: '', boxes: [{id: 'a', frames: 49, exact: true, prompt: 'Wide.', seed: 3, cut: false},
    {id: 'b', frames: 49, exact: true, prompt: 'On.', seed: 4, cut: false}]};
  const editor = open(doc);
  const before = editor.host.text;
  let asked = '';
  globalThis.confirm = (question) => { asked = question; return false; };
  editor.addVideo();
  assert.match(asked, /Clip 2 continues from clip 1\..*Change it\?/);
  assert.equal(editor.host.text, before, 'No changes nothing');
  assert.equal(editor.state.boxes[0].layers, undefined);
  globalThis.confirm = () => true;
  editor.addVideo();
  assert.equal(editor.state.boxes[1].cut, true);
  assert.equal(editor.state.boxes[0].layers.length, 1);
  assert.deepEqual(JSON.parse(editor.host.text).requires, ['video-layers-1']);
  delete globalThis.confirm;
});

test('+ Video is disabled at four videos', () => {
  const full = open(stacked(3, [22, 45, 68]));
  const [add] = byClass(full.stackEl, 'h3ct-add-video');
  assert.equal(add.disabled, true);
  assert.equal(add.title, 'A clip holds at most 4 videos.');
  const short = open(stacked(1, [5], 9));
  const [tight] = byClass(short.stackEl, 'h3ct-add-video');
  assert.equal(tight.disabled, true);
  assert.equal(tight.title, 'This clip is too short for another swap with this fade.');
  const roomy = open(stacked(1, [27]));
  assert.equal(byClass(roomy.stackEl, 'h3ct-add-video')[0].disabled, false);
});
