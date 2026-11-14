import test from 'node:test';
import assert from 'node:assert/strict';
import {findAll, installDom} from './fake_dom.mjs';
import * as model from '../../web/h3c_timeline_model.mjs';
import {ScriptView, addNext, clipStage, continueBlocked, joinLine, promptParts} from '../../web/h3c_script.mjs';

installDom();

const H3 = 'integrated_multimodal_description:\n[Shot 1] A room.\n[Shot 2] A dog walks in.\n'
  + 'overall_soundscape: Rain.\nnon_diegetic_music: None.';

function state(boxes, extra = {}) {
  return model.parseState(JSON.stringify({version: 1, prompt: '', boxes, ...extra}));
}

function editor(value, statuses = []) {
  return {state: value, selected: 0, commits: 0, typings: 0, selections: [],
    host: {context: () => 39, viewUrl: (file) => `/view?filename=${file.filename}`},
    readOnly: [],
    statusOf(box) { return statuses.find((item) => item.id === box?.id); },
    select(index) { this.selected = index; this.selections.push(index); },
    commit() { this.commits += 1; },
    typed() { this.typings += 1; },
    inspectClip() {}};
}

const texts = (root, className) => findAll(root, (node) => node.className.split(' ').includes(className)).map((node) => node.textContent);
const named = (root, className) => findAll(root, (node) => node.className.split(' ').includes(className));

test('a clip is a draft until something is written, then follows its render', () => {
  const value = state([{id: 'a', frames: 107, prompt: '', seed: 1}, {id: 'b', frames: 107, prompt: 'Two.', seed: 2}]);
  assert.equal(clipStage(value, 0, undefined), 'draft');
  assert.equal(clipStage(value, 1, undefined), 'ready');
  assert.equal(clipStage(value, 1, {status: 'next'}), 'ready');
  assert.equal(clipStage(value, 1, {status: 'done'}), 'rendered');
  assert.equal(clipStage(value, 1, {status: 'outdated'}), 'outdated');
  value.prompt = 'A street.';
  assert.equal(clipStage(value, 0, undefined), 'ready', 'the shared prompt alone can be rendered');
});

test('the line between two clips says how the second one starts', () => {
  const value = state([{id: 'a', frames: 107, prompt: 'One.', seed: 1},
    {id: 'b', frames: 107, prompt: 'Two.', seed: 2},
    {id: 'c', frames: 107, prompt: 'Three.', seed: 3, cut: true, memory: 'scene'},
    {id: 'd', frames: 107, prompt: 'Four.', seed: 4, cut: true, new_scene: true, memory: 'off'}]);
  const say = (index) => { const line = joinLine(value, index); return `${line.lead}${line.rest}`; };
  assert.equal(say(1), 'Continues from clip 1');
  assert.equal(say(2), 'Cuts to a new angle, remembering the scene');
  assert.equal(say(3), 'New scene');
  assert.equal(joinLine(value, 1).problem, '');
});

test('a clip cannot continue one that has several videos', () => {
  const value = state([{id: 'a', frames: 107, prompt: 'One.', seed: 1}, {id: 'b', frames: 107, prompt: 'Two.', seed: 2}]);
  assert.equal(continueBlocked(value, 1), '');
  value.boxes[0].layers = [{id: 'a1'}];
  assert.match(continueBlocked(value, 1), /several videos/);
  assert.match(joinLine(value, 1).problem, /several videos/);
});

test('adding the next clip chooses how it starts, with the same flags the Settings tab writes', () => {
  const value = state([{id: 'a', frames: 107, prompt: 'One.', seed: 1}]);
  const flags = (index) => [!!value.boxes[index].cut, !!value.boxes[index].new_scene];
  assert.deepEqual(flags(addNext(value, 'continue', 39)), [false, false]);
  assert.deepEqual(flags(addNext(value, 'cut', 39)), [true, false]);
  assert.deepEqual(flags(addNext(value, 'new_scene', 39)), [true, true]);
  assert.equal(value.boxes.length, 4);
  value.boxes[3].layers = [{id: 'x1'}];
  assert.deepEqual(flags(addNext(value, 'continue', 39)), [true, false], 'after several videos it starts with a cut');
});

test('editing one shot of a complete H3 prompt changes nothing else in it', () => {
  const edit = promptParts(H3);
  assert.deepEqual(edit.parts.map((part) => [part.label, part.value]), [['Shot 1', 'A room.'], ['Shot 2', 'A dog walks in.']]);
  assert.equal(edit.write(1, 'A cat walks in.'), H3.replace('A dog walks in.', 'A cat walks in.'));
  const plain = promptParts('Just a sentence.');
  assert.deepEqual(plain.parts.map((part) => [part.label, part.value]), [['', 'Just a sentence.']]);
  assert.equal(plain.write(0, 'Another.'), 'Another.');
  const one = promptParts('integrated_multimodal_description:\n[Shot 1] A room.\noverall_soundscape: Rain.\nnon_diegetic_music: None.');
  assert.deepEqual(one.parts.map((part) => part.label), [''], 'a single shot needs no label');
});

test('the Script lists the clips, their joins and what happens next', () => {
  const value = state([{id: 'a', frames: 107, prompt: 'One.', seed: 1},
    {id: 'b', frames: 107, prompt: '', seed: 2, cut: true, new_scene: true, memory: 'off'}]);
  const host = editor(value, [{id: 'a', status: 'done', thumb: {filename: 'a.jpg'}}]);
  const view = new ScriptView();
  view.setEditor(host);
  assert.deepEqual(texts(view.root, 'h3cs-num'), ['1', '2']);
  assert.deepEqual(texts(view.root, 'h3cs-stage'), ['Rendered', 'Not written yet']);
  assert.deepEqual(texts(view.root, 'h3cs-scene'), ['Scene 2']);
  assert.equal(findAll(view.root, (node) => node.tagName === 'IMG')[0].src, '/view?filename=a.jpg');
  assert.deepEqual(named(view.root, 'h3cs-next-grid')[0].children.map((node) => node.children[0].textContent),
    ['It keeps going', 'Cut to a new angle', 'Go somewhere new']);
});

test('typing in a clip writes its prompt and selects it', () => {
  const value = state([{id: 'a', frames: 107, prompt: 'One.', seed: 1}, {id: 'b', frames: 107, prompt: '', seed: 2}]);
  const host = editor(value);
  const view = new ScriptView();
  view.setEditor(host);
  const areas = findAll(view.root, (node) => node.tagName === 'TEXTAREA');
  areas[1].fire('focus');
  assert.deepEqual(host.selections, [1]);
  areas[1].value = 'The dog sits.';
  areas[1].fire('input');
  assert.equal(value.boxes[1].prompt, 'The dog sits.');
  assert.equal(host.typings, 1);
  assert.deepEqual(texts(view.root, 'h3cs-stage'), ['Not rendered', 'Not rendered'], 'the first word makes it ready');
});

test('choosing an answer to "What happens next?" adds a clip that starts that way', () => {
  const value = state([{id: 'a', frames: 107, prompt: 'One.', seed: 1}]);
  const host = editor(value);
  const view = new ScriptView();
  view.setEditor(host);
  named(view.root, 'h3cs-next-grid')[0].children[1].click();
  assert.equal(value.boxes.length, 2);
  assert.equal(value.boxes[1].cut, true);
  assert.equal(host.selected, 1);
  assert.equal(host.commits, 1);
  assert.deepEqual(texts(view.root, 'h3cs-num'), ['1', '2']);
});

test('changing a join from its line writes the join and closes the choice', () => {
  const value = state([{id: 'a', frames: 107, prompt: 'One.', seed: 1}, {id: 'b', frames: 107, prompt: 'Two.', seed: 2}]);
  const host = editor(value);
  const view = new ScriptView();
  view.setEditor(host);
  named(view.root, 'h3cs-join')[0].click();
  const options = named(view.root, 'h3cs-options')[0].children.filter((node) => node.tagName === 'BUTTON');
  assert.deepEqual(options.map((node) => node.getAttribute('aria-checked')), ['true', 'false', 'false']);
  options[2].click();
  assert.deepEqual([value.boxes[1].cut, value.boxes[1].new_scene], [true, true]);
  assert.equal(host.commits, 1);
  assert.equal(named(view.root, 'h3cs-options').length, 0);
  assert.deepEqual(texts(view.root, 'h3cs-scene'), ['Scene 2']);
});

test('a Timeline from a newer Studio is shown and cannot be changed from the Script', () => {
  const value = state([{id: 'a', frames: 107, prompt: 'One.', seed: 1}]);
  const host = {...editor(value), readOnly: ['something-new-1']};
  const view = new ScriptView();
  view.setEditor(host);
  assert.equal(findAll(view.root, (node) => node.tagName === 'TEXTAREA')[0].readOnly, true);
  assert.ok(named(view.root, 'h3cs-next-grid')[0].children.every((node) => node.disabled));
});
