import test from 'node:test';
import assert from 'node:assert/strict';
import {installDom} from './fake_dom.mjs';
import * as model from '../../web/h3c_timeline_model.mjs';

installDom();
const {FrameImages} = await import('../../web/h3c_frame_images.mjs');

// The still panel against a host whose saved-sources answers the test releases by hand.
function panel() {
  const asked = [];
  const state = model.parseState(JSON.stringify({version: 1, prompt: '', boxes: [{id: 'a', frames: 96, prompt: 'A street.'}]}));
  const host = {
    context: () => 39, connected: () => ({images: []}), read: () => model.serialize(editor.state), referenceContext: () => 'g1',
    stillSources(request, {signal} = {}) {
      return new Promise((resolve, reject) => {
        asked.push({request, signal, resolve});
        signal?.addEventListener('abort', () => reject(signal.reason));
      });
    },
  };
  const editor = {host, state, selected: 0, commits: 0, box() { return this.state.boxes[this.selected]; },
    commit() { this.commits += 1; }};
  const frames = new FrameImages(editor);
  editor.frameImages = frames;
  Object.assign(frames, {boxId: 'a', target: {kind: 'first'}, render() {}});
  return {frames, editor, asked};
}

const pin = (take) => ({sequence: 's', box: 'a', take, created: '2026-11-01T10:00:00', layout: 'h3', latent_stamp: [1, 2], moment: 0});

test('a blank still prompt generates with the video prompt', async () => {
  const {frames, editor} = panel();
  frames.promptEl.value='   ';
  frames.refreshControls=()=>{};
  frames.host.generateStill=async request=>({state:'complete', request});
  frames.renderGenerateControls();
  assert.equal(frames.generateButton.disabled,false);
  const receipt=await frames.generate();
  assert.equal(receipt.request.prompt,model.assemblePrompt(editor.state,0));
  frames.promptEl.value='An explicit still.';
  assert.equal((await frames.generate()).request.prompt,'An explicit still.');
});

test('a newer saved-sources load cancels the one it replaces before the host asks the server', async () => {
  const {frames, asked} = panel();
  const first = frames.loadSources(), second = frames.loadSources();
  assert.equal(asked.length, 2);
  assert.equal(asked[0].signal?.aborted, true);
  assert.equal(asked[1].signal?.aborted, false);
  asked[1].resolve({ok: true, choices: [pin('t2')], suggested: pin('t2')});
  await Promise.all([first, second]);
  assert.equal(frames.sourcesFailed, false);
  assert.equal(frames.noteEl.textContent, '');
  assert.equal(frames.sourceEl.options.length, 2);
  assert.match(frames.sourceEl.options[1].textContent, /^a · 2026-11-01T10:00:00/);
  assert.equal(frames.sourceEl.value, '0');
});

test('the only load for a target is never cancelled and its answer fills the source list', async () => {
  const {frames, editor, asked} = panel();
  const load = frames.loadSources();
  assert.equal(asked[0].signal?.aborted, false);
  asked[0].resolve({ok: true, choices: [pin('t1')], suggested: pin('t1')});
  await load;
  assert.equal(frames.sourceEl.options.length, 2);
  assert.equal(editor.state.boxes[0].previews[0].still_source.take, 't1');
});
