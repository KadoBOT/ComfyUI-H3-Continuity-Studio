import {test} from 'node:test';
import assert from 'node:assert/strict';
import {formHarness} from './prompt_form_fixture.mjs';
import {findAll,buttonNamed} from './fake_dom.mjs';
test('opening and redrawing an empty form does not invent prompt content or history',()=>{
  const h=formHarness({prompt:''});h.panel.render();
  assert.equal(h.stored().boxes[0].prompt,'');assert.equal(h.history.entries.length,1);
});
test('new definition rows expose a type selector and source picker',()=>{
  const h=formHarness({prompt:'subject_definitions:\n<Subject 1> is Mara.'});
  buttonNamed(h.panel.root,'Add definition').click();
  const types=findAll(h.panel.root,n=>n.getAttribute?.('aria-label')==='Definition type')[0];
  assert.ok(types);
  assert.deepEqual(types.options.map(o=>o.value).filter(Boolean),['subject','image','video','audio']);
});
test('a Basic description field replaces only the selected definition',()=>{
  const h=formHarness({prompt:'subject_definitions:\n<Subject 1> is Mara.\n\ncustom_section: Keep this.'});
  h.input('<Subject 1> description','Mara in a blue coat.');
  assert.equal(h.stored().boxes[0].prompt,'subject_definitions:\n<Subject 1> is Mara in a blue coat.\n\ncustom_section: Keep this.');
});
test('summary task types are a multiple selection that generates the expected prefix',()=>{
  const h=formHarness({prompt:'summary:\nA pause.'});
  const input=findAll(h.panel.root,n=>n.getAttribute?.('aria-label')==='Task types')[0];
  assert.equal(input.multiple,true);
  input.options[0].selected=true;input.options[1].selected=true;input.fire('change');
  assert.equal(h.stored().boxes[0].prompt,'summary:\n[keyframe completion + reference generation] A pause.');
});
