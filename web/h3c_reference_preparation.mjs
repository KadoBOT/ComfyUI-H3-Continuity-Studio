import {stringifyJSON,seedValue} from './h3c_project.mjs?v=0882b8a6265a';
import {ImageJobClient} from './h3c_image_jobs.mjs?v=441234615008';
export const REFERENCE_CATEGORIES = ['cast','locations','props'];

export function preparationOf(state) {
  return state.reference_preparation ?? {version:1, generate:{cast:false,locations:false,props:false}, assets:[], requests:[]};
}

export function setPreparationCategory(state, category, enabled) {
  if (!REFERENCE_CATEGORIES.includes(category) || typeof enabled !== 'boolean') throw new Error('Unknown reference category');
  const preparation = state.reference_preparation ??= preparationOf(state);
  preparation.generate[category] = enabled;
}

export function independentReferences(rows) {
  return rows.filter(row=>!row.from&&!['appearance','scene_layout'].includes(row.role)&&row.status!=='orphan');
}

export function requiredAssets(state, boxId, catalog) {
  const flags = preparationOf(state).generate;
  return independentReferences(catalog).filter(row => flags[row.category] && row.included !== false && row.clips.includes(boxId)
    && !['approved','orphan'].includes(row.status)).map(row => row.key);
}


export class ReferenceClient {
  constructor(host) {
    this.host=host;this.batch=null;
    this.jobs=new ImageJobClient({request:(path,body)=>host.request(path,body),
      capture:request=>host.prepareReference(request),context:()=>host.referenceContext(),
      receipts:()=>preparationOf(host.referenceState()).requests,
      save:(receipt,context)=>this.save(receipt,context),resultPath:'/h3c/reference-assets/result',
      identify:prepared=>({asset_key:prepared.request.asset_key,input_fingerprint:prepared.request.input_fingerprint})});
  }
  get busy() {return !!this.batch || !!this.jobs.active.size || !!this.jobs.recovering;}
  async save(receipt,context) {
    const check=()=>{if(context!==this.host.referenceContext())throw Error('The generation changed while preparing references.');};
    check();
    let row;
    if(receipt.state==='complete'||receipt.state==='submitting') {
      const before=this.host.referenceState();
      row=(await this.host.referenceCatalog()).find(row=>row.key===receipt.asset_key);
      check();
      if(stringifyJSON(before)!==stringifyJSON(this.host.referenceState()))throw Error('References changed while recovering this image.');
    }
    if(receipt.state==='submitting') {
      if(!row||row.status==='orphan'||row.input_fingerprint!==receipt.input_fingerprint)throw Error('The reference design changed before submission.');
      if(!preparationOf(this.host.referenceState()).generate[row.category])throw Error('Reference preparation was disabled before submission.');
    }
    const state=structuredClone(this.host.referenceState()),preparation=state.reference_preparation??=preparationOf(state);
    const index=preparation.requests.findIndex(r=>r.request_id===receipt.request_id&&r.prompt_id===receipt.prompt_id);
    if(index<0)preparation.requests.push(structuredClone(receipt));
    else preparation.requests[index]={...preparation.requests[index],...structuredClone(receipt)};
    const asset=preparation.assets.find(a=>a.key===receipt.asset_key);
    if(receipt.state==='complete' && asset && row?.status!=='orphan' && row?.input_fingerprint===receipt.input_fingerprint) {
      for(const image of receipt.images??[]) {
        const id=image.prompt_id+':'+image.batch_index;
        if(!asset.candidates.some(c=>c.id===id))asset.candidates.push({id,file:structuredClone(image.file),sha256:image.sha256,
          provenance:structuredClone(receipt.provenance),input_fingerprint:receipt.input_fingerprint,
          request_id:receipt.request_id,prompt_id:receipt.prompt_id,batch_index:image.batch_index});
      }
    }
    await this.host.writeReferenceState(state);check();
    if(receipt.state==='submitting'&&!preparationOf(this.host.referenceState()).generate[row.category])throw Error('Reference preparation was disabled before submission.');
    this.host.referenceChanged();return receipt;
  }
  async generateAsset(key) {
    const context=this.host.referenceContext(),before=this.host.referenceState();
    const rows=await this.host.referenceCatalog();
    if(context!==this.host.referenceContext()||stringifyJSON(before)!==stringifyJSON(this.host.referenceState()))throw Error('The references changed before preparation.');
    const row=rows.find(row=>row.key===key);
    if(!row||row.status==='orphan')throw Error('Choose an existing Story reference.');
    const preparation=preparationOf(before);
    if(!preparation.generate[row.category])throw Error('Enable '+row.category+' reference preparation first.');
    if(preparation.requests.some(r=>r.asset_key===key&&!r.historical&&!['complete','failed','cancelled'].includes(r.state)))throw Error('This reference already has a submitted image; recover it before generating another.');
    const state=structuredClone(before),stored=state.reference_preparation??=preparationOf(state);
    const index=stored.assets.findIndex(a=>a.key===key);
    if(index<0)stored.assets.push(structuredClone(row));else stored.assets[index]={...stored.assets[index],...structuredClone(row)};
    await this.host.writeReferenceState(state);
    return this.jobs.generate({asset_key:key,input_fingerprint:row.input_fingerprint,prompt:row.prompt,...(row.seed!=null?{seed:row.seed}:{}),...(row.size?{size:row.size}:{})});
  }
  async recover() {
    try {return await this.jobs.recover();}
    finally {this.host.referenceChanged();}
  }
  stopAfterCurrent() {if(this.batch&&!this.batch.stop){this.batch.stop=true;this.host.referenceChanged();}}
  async generateSelected(keys) {
    if(this.batch)throw Error('Reference preparation is already running.');
    const context=this.host.referenceContext();
    this.batch={keys:[...keys],completed:0,current:null,stop:false};this.host.referenceChanged();
    try {
      for(const key of keys) {
        if(this.batch.stop||context!==this.host.referenceContext())break;
        const row=(await this.host.referenceCatalog()).find(row=>row.key===key);
        if(!row||row.status==='orphan'||!preparationOf(this.host.referenceState()).generate[row.category])break;
        if(row.status==='approved'||row.candidates?.some(c=>c.input_fingerprint===row.input_fingerprint)){this.batch.completed++;continue;}
        this.batch.current=key;this.host.referenceChanged();
        let receipt=await this.generateAsset(key);
        while(!['complete','failed','cancelled'].includes(receipt.state)) {
          await this.recover();
          if(context!==this.host.referenceContext())return;
          receipt=preparationOf(this.host.referenceState()).requests.find(r=>r.prompt_id===receipt.prompt_id)??receipt;
          if(receipt.state==='unknown')throw Error('The image acknowledgement is unknown. Recover the existing request before resuming preparation.');
          if(!['complete','failed','cancelled'].includes(receipt.state))await new Promise(resolve=>setTimeout(resolve,3000));
        }
        if(receipt.state!=='complete')throw Error((row.name??key)+' generation '+receipt.state+'. Earlier candidates are retained.');
        this.batch.completed++;
      }
    } finally {this.batch=null;this.host.referenceChanged();}
  }
}

export function settledPreparation(value) {
  if(!value)return value;
  const result=structuredClone(value);delete result.batch;
  result.requests=(result.requests??[]).filter(r=>r.state==='complete').map(r=>({...r,historical:true}));
  return result;
}


export async function applyReferenceApproval(host,request) {
  if(host.referenceReady)await host.referenceReady();
  const context=host.referenceContext(),timeline=stringifyJSON(host.referenceState());
  const result=await host.request('/h3c/reference-assets/approve',{...request,timeline});
  if(context!==host.referenceContext()||timeline!==stringifyJSON(host.referenceState()))throw Error('The Timeline changed during reference approval; current edits were preserved.');
  if(!result.ok)throw Error(result.error??'Could not approve the reference.');
  if(host.referenceCatalog) {
    const candidate=preparationOf(host.referenceState()).assets.find(a=>a.key===request.asset_key)?.candidates?.find(c=>c.id===request.candidate_id);
    const row=(await host.referenceCatalog()).find(r=>r.key===request.asset_key);
    if(context!==host.referenceContext()||timeline!==stringifyJSON(host.referenceState()))throw Error('The Timeline changed during reference approval; current edits were preserved.');
    if(!row||!candidate||row.input_fingerprint!==candidate.input_fingerprint)throw Error('The reference source or design changed during approval; review a current candidate.');
  }
  host.undoStep?.();
  const saved=host.writeReferenceState(result.timeline);
  host.undoStep?.();
  await saved;host.referenceChanged();return result;
}


export function addObjectReference(state,{name,description,boxId,wholeScene=false}) {
  if(!name.trim()||!description.trim())throw Error('Give the object a name and visual description.');
  const index=state.boxes.findIndex(box=>box.id===boxId);
  if(index<0)throw Error('Select a Story clip for this object.');
  const bible=state.bible??={next:1,entities:[]},used=new Set(bible.entities.map(e=>e.id));
  let number=bible.next??1;while(used.has('e'+number))number++;
  const id='e'+number;bible.next=number+1;
  bible.entities.push({id,kind:'prop',name:name.trim(),description:description.trim(),pictures:[],looks:[]});
  let start=index;if(wholeScene)while(start>0&&!state.boxes[start].new_scene)start--;
  for(let at=start;at<state.boxes.length;at++) {
    if(at>start&&(!wholeScene||state.boxes[at].new_scene))break;
    const schedule=state.boxes[at].schedule??={entities:[]};schedule.entities=[...new Set([...(schedule.entities??[]),id])];
  }
  return id;
}

const element=(tag,className,text)=>{const node=document.createElement(tag);if(className)node.className=className;if(text!=null)node.textContent=text;return node;};
const action=(text,run)=>{const node=element('button','h3ct-button',text);node.type='button';node.addEventListener('click',()=>run());return node;};

export class ReferencePreparationPanel {
  constructor(editor) {
    this.editor=editor;this.host=editor.host;this.rows=[];this.asked=0;this.busy=false;this.message='';this.capability=null;
    this.root=element('details','h3cr-preparation');
    this.root.append(element('summary',null,'Prepare references'));
    this.body=element('div','h3cr-body');this.root.append(this.body);
    this.root.addEventListener('toggle',()=>{if(this.root.open)this.refresh();});
    if(!document.getElementById('h3cr-preparation-style')) {
      const style=element('style');style.id='h3cr-preparation-style';style.textContent=`
      .h3cr-preparation{min-width:0;border:1px solid #343a46;border-radius:6px;padding:8px}
      .h3cr-preparation summary{cursor:pointer;font-weight:600}.h3cr-body{display:flex;flex-direction:column;gap:8px;padding-top:8px;min-width:0}
      .h3cr-preparation .h3cr-switches,.h3cr-preparation .h3cr-actions{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.h3cr-preparation .h3cr-switches label{display:flex;gap:4px;align-items:center}
      .h3cr-asset{display:flex;flex-direction:column;gap:6px;min-width:0;border-top:1px solid #343a46;padding-top:8px}
      .h3cr-preparation textarea,.h3cr-preparation input:not([type=checkbox]),.h3cr-preparation select{max-width:100%;box-sizing:border-box;min-width:0}
      .h3cr-preparation textarea{width:100%;resize:vertical}.h3cr-preparation img{width:112px;max-width:100%;height:84px;object-fit:contain;background:#151923;border-radius:4px}
      .h3cr-candidates{display:flex;flex-wrap:wrap;gap:8px}.h3cr-candidate{display:flex;flex-direction:column;gap:4px;max-width:100%}
      .h3cr-preparation .h3cr-title{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.h3cr-status,.h3cr-note{font-size:12px;color:#aab1bd;overflow-wrap:anywhere;margin:0}
      .h3cr-preparation .h3ct-text{flex:1 1 130px}.h3cr-object{display:flex;flex-wrap:wrap;gap:6px;min-width:0}
      `;document.head.append(style);
    }
    this.render();
  }
  destroy() {this.asked++;}
  async open(keys=[]) {
    this.highlight=new Set(keys);this.root.open=true;await this.refresh();
    this.root.dispatchEvent(new CustomEvent('h3c-show-page',{bubbles:true,detail:{page:'cast'}}));
    this.root.scrollIntoView?.({block:'nearest'});
  }
  async refresh() {
    if(!this.root.open)return;
    const asked=++this.asked,context=this.host.referenceContext?.(),before=stringifyJSON(this.editor.state);
    try {
      const [rows,controls]=await Promise.all([this.host.referenceCatalog(),this.host.stillControls?.()]);
      if(asked!==this.asked||context!==this.host.referenceContext?.()||before!==stringifyJSON(this.editor.state))return;
      this.rows=independentReferences(rows);this.controls=controls;this.capability=controls?.adapter==='pixels';this.message='';this.render();
    } catch(error) {if(asked===this.asked){this.message=error.message;this.render();}}
  }
  commit(edit) {
    this.host.undoStep?.();edit(this.editor.state);this.editor.commit();this.host.undoStep?.();
    this.refresh();
  }
  editRow(row,values) {
    this.commit(state=>{
      const preparation=state.reference_preparation??=preparationOf(state);
      let stored=preparation.assets.find(a=>a.key===row.key);
      if(!stored)preparation.assets.push(stored=structuredClone(row));Object.assign(stored,values);
    });
  }
  async run(operation) {
    if(this.busy)return;this.busy=true;this.message='';this.render();
    try {await operation();}catch(error){this.message=error.message;}
    finally{this.busy=false;const message=this.message;await this.refresh();if(message)this.message=message;this.render();}
  }
  async upload(row,file) {
    if(!file)return;
    const context=this.host.referenceContext?.(),fingerprint=row.input_fingerprint;
    const image=await this.host.importGuide(file),pin=await this.host.pinGuide(image);
    const rows=await this.host.referenceCatalog(),current=rows.find(r=>r.key===row.key);
    if(context!==this.host.referenceContext?.()||current?.input_fingerprint!==fingerprint)throw Error('The reference changed during upload.');
    const request_id=crypto.randomUUID(),prompt_id=crypto.randomUUID();
    this.editRow(current,{candidates:[...(current.candidates??[]),{id:prompt_id+':0',file:pin.file,sha256:pin.sha256,
      input_fingerprint:fingerprint,request_id,prompt_id,batch_index:0,provenance:{origin:'uploaded'}}]});
  }
  render() {
    const focus=this.body.contains(document.activeElement)?document.activeElement:null,focusKey=focus?.dataset.focus;
    const selection=focus&&typeof focus.selectionStart==='number'?[focus.selectionStart,focus.selectionEnd]:null;
    const state=this.editor.state,flags=preparationOf(state).generate,busy=this.busy||this.host.referenceBusy?.();
    const switches=element('div','h3cr-switches');
    for(const [category,title] of [['cast','Generate cast images'],['locations','Generate location images'],['props','Generate object / prop images']]) {
      const label=element('label'),control=element('input');control.type='checkbox';control.checked=!!flags[category];control.dataset.category=category;
      control.addEventListener('change',()=>this.commit(state=>setPreparationCategory(state,category,control.checked)));
      label.append(control,element('span',null,title));switches.append(label);
    }
    const buttons=element('div','h3cr-actions');
    const generate=action('Generate missing references',()=>this.run(()=>this.host.generateSelectedReferences(this.rows.filter(r=>flags[r.category]&&r.included!==false&&r.role!=='scene_layout'&&r.status!=='orphan').map(r=>r.key))));
    generate.disabled=!!busy||this.capability!==true||!this.rows.some(r=>flags[r.category]&&r.included!==false&&['missing','outdated'].includes(r.status));
    const settings=action('Generator settings',()=>this.run(()=>this.host.openStillGenerator()));settings.dataset.action='generator-settings';
    const stop=action('Stop after current image',()=>this.host.stopReferencePreparation());stop.disabled=!this.host.referenceBatch?.();
    buttons.append(generate,settings,stop);
    const parts=[element('p','h3cr-note','One reference per character, outfit, location or object. Uploaded references are ready; generated candidates need Use as reference. Switching preparation off keeps approved images; Enabled references controls their use.'),switches,buttons];
    if(this.capability===false)parts.push(element('p','h3cr-note','Connect a pixel image recipe to generate references here. Uploaded and imported images remain available.'));
    const batch=this.host.referenceBatch?.();if(batch)parts.push(element('p','h3cr-note',`Preparing ${batch.current??'references'} · ${batch.completed} of ${batch.keys.length} completed${batch.stop?' · stopping after current image':''}`));
    if(this.message)parts.push(element('p','h3cr-note',this.message));
    parts.push(this.objectForm());
    for(const row of this.rows) {
      const card=element('section','h3cr-asset');card.dataset.asset=row.key;
      const title=element('div','h3cr-title'),include=element('input');include.type='checkbox';include.checked=row.included!==false;
      include.setAttribute('aria-label','Prepare '+row.name);include.addEventListener('change',()=>this.editRow(row,{included:include.checked}));
      title.append(include,element('strong',null,row.name),element('span','h3cr-status',row.status));card.append(title);
      card.append(element('p','h3cr-note',row.clips.length?'Used in clips '+row.clips.map(id=>state.boxes.findIndex(b=>b.id===id)+1).join(', '):'Owner removed or not yet scheduled'));
      const prompt=element('textarea','h3ct-text');prompt.rows=3;prompt.value=row.prompt??'';prompt.setAttribute('aria-label',row.name+' image prompt');prompt.dataset.focus=row.key+':prompt';
      prompt.addEventListener('change',()=>this.editRow(row,{prompt:prompt.value}));card.append(prompt);
      const fields=element('div','h3cr-actions');
      const seed=element('input','h3ct-text');seed.type='text';seed.inputMode='numeric';seed.placeholder='Seed: native generator';seed.value=row.seed==null?'':String(row.seed);seed.setAttribute('aria-label',row.name+' seed');seed.dataset.focus=row.key+':seed';
      seed.addEventListener('change',()=>{const value=seed.value===''?undefined:seedValue(seed.value);if(seed.value!==''&&value===undefined){this.message='Image seed must be an unsigned 64-bit integer.';this.render();return;}this.editRow(row,{seed:value});});
      fields.append(seed);
      for(const dimension of ['width','height']) {
        const size=element('input','h3ct-text');size.type='number';size.min='1';size.placeholder=dimension+' (native)';size.value=row.size?.[dimension]??'';size.setAttribute('aria-label',row.name+' '+dimension);size.dataset.focus=row.key+':'+dimension;
        size.addEventListener('change',()=>{if(size.value===''){this.editRow(row,{size:undefined});return;}const width=Number(dimension==='width'?size.value:row.size?.width??this.controls?.width),height=Number(dimension==='height'?size.value:row.size?.height??this.controls?.height);if(Number.isInteger(width)&&width>0&&Number.isInteger(height)&&height>0)this.editRow(row,{size:{width,height}});else {this.message='Choose positive width and height, or use Generator settings.';this.render();}});fields.append(size);
      }
      card.append(fields);
      const controls=element('div','h3cr-actions'),generateOne=action(row.status==='approved'?'Regenerate reference':row.candidates.length?'Regenerate candidate':'Generate reference',()=>this.run(()=>this.host.generateReference(row.key)));
      generateOne.disabled=!!busy||!flags[row.category]||this.capability!==true||row.status==='orphan';
      const upload=element('input');upload.type='file';upload.accept='image/*';upload.setAttribute('aria-label','Upload '+row.name+' reference');upload.hidden=true;upload.addEventListener('change',()=>this.run(()=>this.upload(row,upload.files[0])));
      const uploadButton=action('Upload candidate',()=>upload.click());uploadButton.disabled=!!busy||row.status==='orphan';
      controls.append(generateOne,uploadButton,upload);card.append(controls);
      const candidates=element('div','h3cr-candidates');
      for(const original of row.existing_images??[]) {
        const item=element('div','h3cr-candidate'),image=element('img');image.src=this.host.viewUrl(original.file);image.alt=row.name+' uploaded reference';
        item.append(image,element('span','h3cr-status','Uploaded reference — ready'));candidates.append(item);
      }
      for(const candidate of row.candidates) {
        const item=element('div','h3cr-candidate'),image=element('img');image.src=this.host.viewUrl(candidate.file);image.alt=row.name+' candidate';
        const accept=action(row.approved?.candidate_id===candidate.id?'Approved reference':'Use as reference',()=>this.run(()=>this.host.approveReference({asset_key:row.key,candidate_id:candidate.id,expected_revision:row.approved?.revision??0})));
        accept.disabled=!!busy||row.status==='orphan'||candidate.input_fingerprint!==row.input_fingerprint||row.approved?.candidate_id===candidate.id;
        item.append(image,accept);if(candidate.input_fingerprint!==row.input_fingerprint)item.append(element('span','h3cr-status','Out of date'));candidates.append(item);
      }
      card.append(candidates);parts.push(card);
    }
    this.body.replaceChildren(...parts);
    const again=focusKey&&[...this.body.querySelectorAll('[data-focus]')].find(n=>n.dataset.focus===focusKey);
    if(again){again.focus();if(selection&&again.setSelectionRange)again.setSelectionRange(...selection);}
  }
  objectForm() {
    const form=element('div','h3cr-object'),name=element('input','h3ct-text'),description=element('input','h3ct-text');
    name.placeholder='Object name (weapon, car, prop…)';name.setAttribute('aria-label','New object reference name');
    description.placeholder='Visual description';description.setAttribute('aria-label','New object reference description');
    const label=element('label'),whole=element('input');whole.type='checkbox';whole.checked=true;label.append(whole,element('span',null,'Use throughout this scene'));
    const add=action('Add object reference',()=>{try{this.commit(state=>addObjectReference(state,{name:name.value,description:description.value,boxId:state.boxes[this.editor.selected]?.id,wholeScene:whole.checked}));}catch(error){this.message=error.message;this.render();}});
    form.append(name,description,label,add);return form;
  }
}
