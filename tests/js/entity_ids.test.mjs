import test from 'node:test';
import assert from 'node:assert/strict';
import {renumberEntities} from '../../web/h3c_timeline_model.mjs';

const entity = (id, kind = 'character') => ({id, kind, name: id, pictures: [], description: '', looks: []});

test('Cast ids written elsewhere become e-numbers in the bible, schedules and clip casts', () => {
  const state = {bible: {entities: [entity('stellar'), entity('e2'), entity('kitchen', 'place')]}, boxes: [
    {id: 'b1', schedule: {entities: ['stellar', 'e2'], place: 'kitchen'}, cast: {'<Subject 1>': 'stellar', '<Subject 2>': 'e2'}},
    {id: 'b2', schedule: {entities: [], place: null}},
    {id: 'b3'}]};
  assert.equal(renumberEntities(state), true);
  assert.deepEqual(state.bible.entities.map(e => e.id), ['e3', 'e2', 'e4']);
  assert.equal(state.bible.next, 5);
  assert.deepEqual(state.boxes[0].schedule, {entities: ['e3', 'e2'], place: 'e4'});
  assert.deepEqual(state.boxes[0].cast, {'<Subject 1>': 'e3', '<Subject 2>': 'e2'});
  assert.deepEqual(state.boxes[1].schedule, {entities: [], place: null});
});

test('a bible with e-number ids, or none, is left alone', () => {
  const state = {bible: {entities: [entity('e1')], next: 4}, boxes: [{id: 'b1', schedule: {entities: ['e1'], place: null}}]};
  const before = structuredClone(state);
  assert.equal(renumberEntities(state), false);
  assert.deepEqual(state, before);
  assert.equal(renumberEntities({boxes: []}), false);
});

test('renumbering skips past the saved next id', () => {
  const state = {bible: {entities: [entity('e1'), entity('hero')], next: 7}, boxes: []};
  renumberEntities(state);
  assert.deepEqual(state.bible.entities.map(e => e.id), ['e1', 'e7']);
  assert.equal(state.bible.next, 8);
});
