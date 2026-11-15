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
test('invalid shot starts stay local and prevent navigation and generation until discarded',async()=>{
  const prompt='integrated_multimodal_description:\n[Shot 1] A room.\n[Shot 2] At 00:02.000, the camera cuts to a doorway.';
  const h=formHarness({prompt});h.editor.state.boxes.push({...h.editor.state.boxes[0],id:'b'});
  h.input('Shot 2 start (seconds)','-1');
  assert.equal(h.stored().boxes[0].prompt,prompt);assert.equal(h.panel.canLeave(),false);
  h.editor.select(1);assert.equal(h.editor.selected,0);
  await h.editor.queueBox(1);assert.equal(h.queued(),0);
  h.panel.render();assert.equal(findAll(h.panel.root,n=>n.getAttribute?.('aria-label')==='Shot 2 start (seconds)')[0].value,'-1');
  h.panel.discardDrafts();assert.equal(h.panel.canLeave(),true);assert.equal(h.stored().boxes[0].prompt,prompt);
});
test('later starts serialize clean seconds while Shot 1 never has a timestamp input',()=>{
  const h=formHarness({prompt:'integrated_multimodal_description:\n[Shot 1] A room.\n[Shot 2] At 00:02.000, the camera cuts to a doorway.'});
  assert.equal(findAll(h.panel.root,n=>n.getAttribute?.('aria-label')==='Shot 1 start (seconds)').length,0);
  h.input('Shot 2 start (seconds)','2.5');
  assert.match(h.stored().boxes[0].prompt,/At 00:02\.500,/);assert.equal(h.panel.hasDrafts(),false);
});
test('a project or history reload explicitly discards an incompatible structural draft',()=>{
  const prompt='integrated_multimodal_description:\n[Shot 1] A room.\n[Shot 2] At 00:02.000, the camera cuts to a doorway.';
  const h=formHarness({prompt});const saved=JSON.stringify(h.stored());
  h.input('Shot 2 start (seconds)','-1');
  h.editor.host.read=()=>saved;h.editor.replacements={close(){}};h.editor.cast={changed(){}};h.editor.render=()=>h.panel.render();
  h.editor.load();
  assert.equal(h.panel.hasDrafts(),false);assert.equal(h.stored().boxes[0].prompt,prompt);
  assert.match(h.panel.root.textContent,/discarded.*history/i);
});
