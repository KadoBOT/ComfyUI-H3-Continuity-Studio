import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  describeBox,
  joinKind,
  lintContinuationPair,
  lintScreenFx,
  setCut,
} from '../../web/h3c_timeline_model.mjs?v=c3173f40aa48';

test('lintScreenFx flags unsolicited overlays and honors negations, diegetic crackle and shared context', () => {
  const hits = lintScreenFx('A corridor shot on 35mm with subtle film grain and vignette.');
  assert.deepEqual(hits.map((h) => h.token), ['vignette', 'grain', '35mm']);

  assert.deepEqual(
    lintScreenFx('Clean image without vignette, film grain, or overlays; campfire crackles softly.'),
    [],
  );

  assert.deepEqual(
    lintScreenFx('Warm 35mm grain on the rain.', 'Shot on 35mm with fine film grain.'),
    [],
  );
});

test('lintContinuationPair flags framing jumps, speed flips and same-scene lighting flips across boxes', () => {
  const prev = 'integrated_multimodal_description: [Shot 1] Wide establishing shot moving slowly under warm tungsten glow. <d>Bright morning!</d>\noverall_soundscape: Hum.';
  const next = 'integrated_multimodal_description: [Shot 1] Tight close-up darting fast into sterile cool fluorescent light.';
  const cont = lintContinuationPair(prev, next, {sameScene: true, continuous: true});
  assert.deepEqual(
    cont.map((w) => w.code),
    ['continuation_framing_jump', 'continuation_speed_flip', 'lighting_drift'],
  );

  const cutSameScene = lintContinuationPair(prev, next, {sameScene: true, continuous: false});
  assert.deepEqual(cutSameScene.map((w) => w.code), ['lighting_drift']);

  const cutNewScene = lintContinuationPair(prev, next, {sameScene: false, continuous: false});
  assert.deepEqual(cutNewScene, []);
});

test('describeBox surfaces continuity and FX warnings before render', () => {
  const state = {
    version: 1,
    prompt: 'Clean daylight.',
    boxes: [
      {id: 'a', frames: 39, cut: true, prompt: 'Wide shot slowly tracking through warm sunlight.'},
      {id: 'b', frames: 34, cut: false, prompt: 'Tight close-up sprinting fast with a soft vignette in cool moonlight.'},
    ],
  };
  const info = describeBox(state, 1, {images: new Set(), audios: new Set()}, 22);
  assert.ok(info.warnings.some((w) => w.includes('vignette')));
  assert.ok(info.warnings.some((w) => w.includes('framing jump')));
  assert.ok(info.warnings.some((w) => w.includes('speed flip')));
  assert.ok(info.warnings.some((w) => w.includes('warm to cool')));
});

test('setCut(false) clears stale transition join so Cut does not stay stuck without a bible', () => {
  const state = {
    version: 1,
    prompt: '',
    boxes: [
      {id: 'a', frames: 39, cut: true, prompt: 'One.'},
      {id: 'b', frames: 34, cut: true, new_scene: true, join: {kind: 'transition', note: 'Push'}, prompt: 'Two.'},
    ],
  };
  setCut(state, 1, false, 39);
  assert.equal(state.boxes[1].cut, false);
  assert.equal(state.boxes[1].new_scene, undefined);
  assert.equal(state.boxes[1].join, undefined);
  assert.equal(joinKind(state.boxes[1]), 'continue');
});
