import test from 'node:test';
import assert from 'node:assert/strict';
import { findAll, installDom } from './fake_dom.mjs';

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
element.closest ??= function (selector) {
  if (selector === '.h3cs') {
    let cur = this;
    while (cur) {
      if (cur.classList?.contains?.('h3cs')) return cur;
      cur = cur.parentNode;
    }
  }
  return null;
};

const {TimelineEditor} = await import('../../web/h3c_timeline_editor.mjs');
const tracks = await import('../../web/h3c_tracks.mjs');

function makeEditor(doc, onSave = () => {}) {
  const host = {
    text: JSON.stringify(doc),
    read() { return this.text; },
    write(value) { this.text = value; onSave(value); },
    context: () => 22,
    connected: () => ({images: [], audios: []}),
    viewUrl: (file) => `/view?filename=${file.filename}`,
    changed() {},
    asked: [],
    async preflight(box, count, rebuild) { this.asked.push(rebuild); return {cancelled: true}; },
    async queue() {},
  };
  return new TimelineEditor(host);
}

test('TrackEditor.addClip continues by default when abutting a non-stacked clip and exposes badges/tooltips', () => {
  const doc = {
    version: 1,
    requires: [tracks.FEATURE],
    tracks: [{id: 'v1', type: 'video', name: 'Video 1'}],
    boxes: [{id: 'a', track: 'v1', start: 0, frames: 39, cut: true, prompt: 'Wide scene.'}],
  };
  const editor = makeEditor(doc);
  editor.playheadFrame = 39;
  editor.trackEditor.selectedTrack = 'v1';
  editor.trackEditor.addClip();

  assert.equal(editor.state.boxes[1].start, 39);
  assert.equal(editor.state.boxes[1].cut, false);
  assert.equal(editor.state.boxes[1].memory, 'scene');

  // At a gap past clip 2 on the same track, adding a clip must start as a cut.
  const bEnd = editor.state.boxes[1].start + editor.state.boxes[1].frames;
  editor.playheadFrame = bEnd + 40;
  editor.trackEditor.addClip();
  const b = editor.state.boxes[1];
  const c = editor.state.boxes[2];
  assert.equal(c.start, bEnd + 40);
  assert.equal(c.cut, true);
  b.prompt = 'Continuing shot.';
  c.prompt = 'Cut after gap.';
  editor.commit();

  editor.setStatus({
    ok: true,
    message: 'ready',
    seam_warnings: [{kind: 'mixed_protection', message: 'Mixed protection on clip 2.'}],
    boxes: [
      {id: 'a', status: 'done'},
      {id: b.id, status: 'outdated', reason: 'stale overlap', seam_warnings: [{kind: 'mixed_protection', message: 'Mixed protection on clip 2.'}]},
      {id: c.id, status: 'done', check: {checked: '2026-11-28T10:00:00', problems: [], continuity: {warnings: ['vignette detected']}}},
    ],
  });
  editor.select(1);
  assert.match(editor.promptProblemEl.textContent, /Mixed protection on clip 2\./);
  assert.match(editor.summaryEl.textContent, /1 seam warning/);

  const trackClips = findAll(editor.trackEditor.rows, (node) => node.classList?.contains?.('h3ct-track-clip'));
  const second = trackClips.find((node) => node.getAttribute('aria-label') === 'Clip 2');
  const third = trackClips.find((node) => node.getAttribute('aria-label') === 'Clip 3');
  assert.ok(second.classList.contains('outdated'));
  assert.ok(second.classList.contains('warning'));
  assert.match(second.textContent, /⚠/);
  assert.match(second.title, /Mixed protection on clip 2/);
  assert.ok(third.classList.contains('cut'));
  assert.ok(third.classList.contains('warning'));
  assert.match(third.title, /Continuity check found issues/);
});

test('Play join computes seam region inside Studio and dispatches h3c-play-region, and Check Retake forwards Ctrl', async () => {
  const doc = {
    version: 1,
    boxes: [
      {id: 'a', frames: 90, cut: true, prompt: 'First clip.'},
      {id: 'b', frames: 68, cut: false, prompt: 'Second clip.'},
    ],
  };
  const editor = makeEditor(doc);
  const studioShell = document.createElement('div');
  studioShell.className = 'h3cs';
  studioShell.append(editor.root);

  const regions = [];
  studioShell.addEventListener('h3c-play-region', (event) => regions.push(event.detail));

  editor.setStatus({
    ok: true,
    message: 'done',
    full_video: {file: {filename: 'seq_full.mp4'}},
    full_video_clock: [[0, 158, 0, 1]],
    boxes: [
      {id: 'a', status: 'done'},
      {id: 'b', status: 'done', check: {checked: '2026-11-28T10:00:00', problems: [], continuity: {warnings: ['exposure jumped']}}},
    ],
  });
  editor.select(1);
  assert.equal(editor.playJoinButton.hidden, false);
  const expected = editor.joinPreviewRegion(1);
  assert.deepEqual(expected, {start: 2, end: 5.5});
  editor.playJoinButton.click();
  assert.deepEqual(regions, [expected]);

  // Ctrl+click on CheckPanel Retake forwards rebuild=true.
  assert.equal(editor.checks.retakeButton.hidden, false);
  editor.checks.retakeButton.dispatchEvent({
    type: 'click', bubbles: true, button: 0, ctrlKey: true,
    preventDefault() {}, stopPropagation() {},
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(editor.host.asked.at(-1), true);
});
