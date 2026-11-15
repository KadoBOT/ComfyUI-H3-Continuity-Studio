import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readPromptFields,writePromptField} from '../../web/h3c_prompt_fields.mjs';
test('retention controls create exact subject and picture scope syntax',()=>{
  const source='retention_analysis:\n';
  const value={target:'<Subject 1>',shots:[1,3],scope:'',relationship:'fully_preserved',detail:'Keeps the coat.'};
  const next=writePromptField(source,{expectedSource:source,section:'retention_analysis',kind:'retention',entry:null,value});
  assert.equal(next,source+'<Subject 1> (appears in [Shot 1], [Shot 3]): fully_preserved - Keeps the coat.');
  assert.deepEqual(readPromptFields(next).sections[0].entries[0].value,value);
});
test('custom markers and opaque content survive reload and a local field edit',()=>{
  const source='retention_analysis:\n<Subject 1>: my_custom_relation - Keep this.\n\ncustom_section: untouched 😀';
  const entry=readPromptFields(source).sections[0].entries[0];
  const next=writePromptField(source,{expectedSource:source,section:'retention_analysis',kind:'retention',entry,value:{...entry.value,detail:'Changed.'}});
  assert.equal(next,'retention_analysis:\n<Subject 1>: my_custom_relation - Changed.\n\ncustom_section: untouched 😀');
});
test('stable slots are not retargeted when native reference numbering changes',()=>{
  const source='subject_definitions:\n@image17 is the opening frame.';
  for(const tags of [[{name:'image17',tag:'<Picture 1>'}],[{name:'image20',tag:'<Picture 1>'}]])
    assert.equal(readPromptFields(source,{tags}).sections[0].entries[0].value.target,'@image17');
  const unresolved=readPromptFields('retention_analysis:\n<Picture 9>: fully_preserved - Frame.');
  assert.equal(unresolved.sections[0].entries[0].kind,'existing');
});
test('deleting a referenced subject and applying stale source ranges are rejected',()=>{
  const source='subject_definitions:\n<Subject 1> is Mara.\ndetailed_description:\n[Shot 1] <Subject 1> waits.';
  const entry=readPromptFields(source).sections[0].entries[0];
  const edit={expectedSource:source,section:'subject_definitions',kind:'definition',entry,value:null};
  assert.throws(()=>writePromptField(source,edit),/used|reference/i);
  assert.throws(()=>writePromptField(source+'!',edit),/changed/i);
});
