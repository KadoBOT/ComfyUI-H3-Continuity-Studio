import test from 'node:test';
import assert from 'node:assert/strict';
import {installDom,findAll} from './fake_dom.mjs';
import {ReferencePreparationPanel} from '../../web/h3c_reference_preparation.mjs';
installDom();
const row=(key,name,category)=>({key,name,category,role:category==='cast'?'character':'place',status:'missing',input_fingerprint:key+'-v1',included:true,clips:['A'],prompt:name+' visual description',candidates:[],existing_images:[]});
const rows=[row('a','Mara','cast'),row('b','The field','locations')];
async function open(){const editor={state:{boxes:[{id:'A',frames:48,cut:true}],reference_preparation:{version:1,generate:{cast:true,locations:true,props:false},assets:[],requests:[]}},readOnly:[],selected:0,commit(){},inspectClip(){},host:{referenceContext:()=> 'fixture',referenceCatalog:async()=>structuredClone(rows),stillControls:async()=>({adapter:'pixels'}),viewUrl:()=>'/image'}};const panel=new ReferencePreparationPanel(editor);panel.root.open=true;await panel.refresh();return panel;}
test('reference preparation edits one selected asset instead of rendering every form',async()=>{
 const panel=await open();let inputs=findAll(panel.body,n=>n.tagName==='TEXTAREA');assert.equal(inputs.length,1);assert.equal(inputs[0].getAttribute('aria-label'),'Mara image prompt');
 panel.choose('b');inputs=findAll(panel.body,n=>n.tagName==='TEXTAREA');assert.equal(inputs.length,1);assert.equal(inputs[0].getAttribute('aria-label'),'The field image prompt');
 panel.setFilter('cast');assert.equal(panel.selectedKey,'a');assert.equal(panel.editor.state.reference_preparation.generate.locations,true);
});
test('late catalog replies cannot replace a newer selection or catalog',async()=>{
 const panel=await open();panel.choose('b');const pending=[];panel.host.referenceCatalog=()=>new Promise(resolve=>pending.push(resolve));
 const first=panel.refresh(),second=panel.refresh();pending[1]([{...rows[0]},{...rows[1],name:'Updated field'}]);await second;
 pending[0]([rows[0]]);await first;assert.equal(panel.selectedKey,'b');assert.ok(panel.body.textContent.includes('Updated field'));
});

test('a catalog refresh preserves an unsaved description draft',async()=>{
 const panel=await open(),input=findAll(panel.body,n=>n.tagName==='TEXTAREA')[0];input.value='User description in progress';input.fire('input');await panel.refresh();
 assert.equal(findAll(panel.body,n=>n.tagName==='TEXTAREA')[0].value,'User description in progress');assert.equal(panel.editor.state.reference_preparation.assets.length,0);
});
test('stale candidate approval stays disabled, current candidate sends the selected asset identity',async()=>{
 const panel=await open(),candidate={id:'candidate1',file:{type:'input',filename:'candidate.png'},sha256:'a'.repeat(64),input_fingerprint:'old',request_id:'r',prompt_id:'p',batch_index:0,provenance:{origin:'uploaded'}};
 panel.host.referenceCatalog=async()=>[{...rows[0],candidates:[candidate]}];await panel.refresh();
 let approve=findAll(panel.body,n=>n.tagName==='BUTTON'&&n.textContent==='Use as reference')[0];assert.equal(approve.disabled,true);
 candidate.input_fingerprint='a-v1';await panel.refresh();approve=findAll(panel.body,n=>n.tagName==='BUTTON'&&n.textContent==='Use as reference')[0];assert.equal(approve.disabled,false);
 const sent=[];panel.host.approveReference=async request=>sent.push(request);approve.fire('click');await new Promise(setImmediate);
 assert.deepEqual(sent,[{asset_key:'a',candidate_id:'candidate1',expected_revision:0}]);
});
