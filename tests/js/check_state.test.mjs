import { test } from 'node:test';
import assert from 'node:assert/strict';
import { checkGroups, checkState, hasCheckIssue } from '../../web/h3c_check.mjs?v=e094466f59ac';

const base = {checked: '2026-11-04T07:40:00', model: null, problems: null};

test('holds read as lines and enable Retake', () => {
  const state = checkState({...base, holds: [{start_ms: 0, frames: 3, join: true}, {start_ms: 4167, frames: 12, join: false}]});
  assert.deepEqual(state.lines, ['Holds still: 3 frames at the join.', 'Holds still: 12 frames at 4.2 s.']);
  assert.equal(state.retake, true);
});

test('texture words arrive through drift words unchanged', () => {
  const state = checkState({...base, drift: {box: 'a', words: 'warmer and 30% grainier', texture: [1.3, 1, 1]}}, () => 1);
  assert.deepEqual(state.lines, ['Drift: warmer and 30% grainier than box 1.']);
});

test('no holds and no drift: nothing to retake', () => {
  assert.equal(checkState({...base, holds: []}).retake, false);
});

test('quantitative continuity warnings suppress false clean message and enable Retake', () => {
  const check = {
    checked: '2026-11-28T10:15:00',
    model: 'qwen-vl',
    problems: [],
    continuity: {warnings: ['exposure jumped 5.2 L* darker from box 1']},
  };
  const state = checkState(check, () => 1);
  assert.equal(state.lines.includes('No problems found.'), false);
  assert.deepEqual(state.continuityWarnings, ['exposure jumped 5.2 L* darker from box 1']);
  assert.deepEqual(state.lines, ['Continuity: exposure jumped 5.2 L* darker from box 1.']);
  assert.equal(state.retake, true);
  assert.equal(hasCheckIssue(check), true);
  assert.equal(hasCheckIssue({...check, stale: true}), false);
});

test('checkGroups maps fx problems to Screen FX after entity groups', () => {
  const groups = checkGroups(
    {problems: [
      {about: 'fx', shot: 2, what: 'Dark corner vignette.'},
      {about: 'e1', shot: 1, what: 'Wrong jacket.'},
      {about: 'place', shot: 0, what: 'Rain vanished.'},
    ]},
    {entities: [{id: 'e1', name: 'Mara'}]},
    {entities: ['e1']},
  );
  assert.deepEqual(groups.map((g) => g.heading), ['Mara', 'Place', 'Screen FX']);
  assert.deepEqual(groups[2].items, ['Dark corner vignette (shot 2).']);
});
