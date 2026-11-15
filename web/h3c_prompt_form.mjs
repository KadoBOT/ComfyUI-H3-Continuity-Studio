import {readPromptFields,writePromptField,SECTION_TITLES,RETENTION_VISUAL,RETENTION_AUDIO,SUMMARY_TASKS} from './h3c_prompt_fields.mjs';
import {promptShots} from './h3c_prompt_sections.mjs';
import {promptSections,replacePromptRanges} from './h3c_prompt_sections.mjs';
import {SwitchSection} from './h3c_switch_section.mjs';
import {MentionLayer} from './h3c_mentions.mjs';
const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;};
const button=(text,action)=>{const node=el('button','h3ct-button',text);node.type='button';node.addEventListener('click',action);return node;};
let ids=0;
const style=()=>{
  if(document.getElementById('h3pf-style'))return;
  const node=el('style');node.id='h3pf-style';node.textContent=`
.h3pf{border:0;padding:0;margin:0;min-width:0}.h3pf [hidden]{display:none!important}
.h3pf-tabs{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px}.h3pf-tabs [aria-selected=true]{border-color:#809fcc;background:#293545}
.h3pf-row{padding:10px 0;border-bottom:1px solid #343a46;min-width:0}.h3pf-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(150px,100%),1fr));gap:8px}
.h3pf-field{display:flex;flex-direction:column;gap:4px;margin:6px 0;min-width:0}.h3pf-field>span{font-size:12px;color:var(--h3b-muted,#aab2bf)}
.h3pf :is(input,select,textarea){box-sizing:border-box;width:100%;min-width:0;max-width:100%}.h3pf textarea{resize:vertical}
.h3pf-actions{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.h3pf-error{color:#ffc2bb;white-space:pre-wrap;overflow-wrap:anywhere}
.h3pf :is(input,textarea,select,button):focus-visible{outline:2px solid #8fbcff;outline-offset:2px}.h3pf input[type=checkbox]{width:auto}
`;document.head.append(node);
};

export class PromptFormPanel {
  constructor(editor) {
    style();this.editor=editor;this.root=el('fieldset','h3pf');this.drafts=new Map();this.newRows=[];this.marks=[];
    this.section=null;this.controls=new Map();this.serial=++ids;this.message='';this.sectionStash=new Map();
  }
  tags(){return this.editor.pickedInfo?.().tags??[];}
  hasDrafts(){return this.drafts.size>0;}
  canLeave(){if(!this.hasDrafts())return true;this.message='Finish or discard the unsaved field before leaving this clip.';this.render();return false;}
  discardDrafts(){this.drafts.clear();this.newRows=[];this.message='';this.render();}
  destroy(){for(const mark of this.marks)mark.destroy();this.marks=[];}
  focusSubject(label){this.section='subject_definitions';this.editor.setTab?.('prompt');this.render();this.controls.get(`${label} description`)?.focus?.();}
  field(parent,label,value,onChange,{options=null,multiple=false,area=false,suggestions=null}={}) {
    const wrap=el('label','h3pf-field'),name=el('span',null,label);
    const input=el(options?'select':area?'textarea':'input',options?'h3ct-select':'h3ct-text');
    input.setAttribute('aria-label',label);input.id=`h3pf-${this.serial}-${this.controls.size}`;input.dataset.key=label;
    if(options) {
      input.multiple=multiple;
      if(!multiple)options=[['','Choose…'],...options];
      for(const item of options){const [key,title]=Array.isArray(item)?item:[item,item];const option=el('option',null,title);option.value=String(key);option.selected=multiple?(value??[]).includes(key):key===value;input.append(option);}
    }
    if(!multiple)input.value=String(value??'');if(area)input.rows=3;
    input.addEventListener(options?'change':'input',()=>onChange(multiple?[...input.options].filter(o=>o.selected)
      .map(o=>options.map(item=>Array.isArray(item)?item[0]:item).find(key=>String(key)===o.value)):input.value));
    if(suggestions){const list=el('datalist');list.id=input.id+'-options';for(const s of suggestions){const o=el('option');o.value=s;list.append(o);}input.setAttribute('list',list.id);wrap.append(list);}
    wrap.append(name);
    if(area&&this.editor.mentionHooks){const mark=new MentionLayer(input,this.editor.mentionHooks());this.marks.push(mark);wrap.append(mark.root);}
    else wrap.append(input);
    input.addEventListener('focus',()=>{this.editor.activePromptEl=input;});
    wrap.append();parent.append(wrap);this.controls.set(label,input);return input;
  }
  edit(section,index,key,kind,patch) {
    const source=this.editor.video().prompt;
    if(source!==this.source){this.message='The prompt changed. Reopen this field before editing.';this.render();return;}
    const parsed=readPromptFields(source,{tags:this.tags()});
    const entry=index==null?null:parsed.sections.find(s=>s.key===section)?.entries[index];
    const base=this.drafts.get(key)?.value??entry?.value??this.newRows.find(r=>r.key===key)?.value??{};
    const value=patch===null?null:{...base,...(typeof patch==='function'?patch(base):patch)};
    try {
      if(value===null&&kind==='definition'&&this.editor.box()?.cast?.[entry.value.target])throw new Error('Unlink this subject from Cast before deleting its definition.');
      const next=writePromptField(source,{expectedSource:source,section,kind,entry,value},{tags:this.tags()});
      if(this.editor.applyPrompt(source,next,{structural:index==null||value===null})===false)throw new Error('This prompt is read-only or changed.');
      this.source=next;this.drafts.delete(key);this.message='';
      if(index==null||value===null){this.newRows=this.newRows.filter(r=>r.key!==key);this.render();}
      else {const note=this.note; if(note)note.textContent='';}
    } catch(error){this.drafts.set(key,{value});this.message=error.message;if(this.note)this.note.textContent=this.message;}
  }
  row(parent,section,entry,index,key) {
    const row=el('div','h3pf-row');parent.append(row);
    const kind=entry.kind,value=this.drafts.get(key)?.value??entry.value;
    const edit=patch=>this.edit(section,index,key,kind,patch);
    if(kind==='definition') {
      if(index==null) {
        this.field(row,'Definition type',value.type??'subject',type=>{
          const target=type==='subject'?`<Subject ${Math.max(0,...[...`${this.source} ${this.editor.state.prompt??''}`.matchAll(/<Subject (\d+)>/g)].map(m=>Number(m[1])))+1}>`:'';
          this.drafts.set(key,{value:{...value,type,target}});this.render();
        },{options:[['subject','Subject'],['image','Picture'],['video','Video'],['audio','Audio']]});
        if(value.type&&value.type!=='subject')this.field(row,'Definition target',value.target,target=>edit({target}),{
          options:(this.editor.referenceOptions?.()??[]).filter(r=>r.name.startsWith(value.type)).map(r=>['@'+r.name,r.title||r.name])});
      }
      row.append(el('strong',null,value.target));
      this.field(row,`${value.target} description`,value.description,description=>edit({description}),{area:true});
      for(const [at,source] of (value.sources??[]).entries()) {
        const update=patch=>this.edit(section,index,key,kind,current=>({sources:current.sources.map((s,i)=>i===at?{...s,...patch}:s)}));
        this.field(row,`${value.target} source ${at+1}`,source.slot,slot=>update({slot}),{options:(this.editor.referenceOptions?.()??[]).map(r=>[r.name,r.title||r.name])});
        this.field(row,`${value.target} source ${at+1} role`,source.role,role=>update({role}),{suggestions:['appearance','environment','clothing','style','object','pose']});
      }
      row.append(button('Add source',()=>{this.drafts.set(key,{value:{...value,sources:[...(value.sources??[]),{slot:'',role:''}]}});this.render();}));
      if(this.editor.box()?.cast?.[value.target])row.append(button('Unlink from Cast',async()=>{
        await this.editor.cast.change({action:'apply',bible:this.editor.state.bible,links:{[this.editor.box().id]:{[value.target]:null}}});
      }));
    } else if(kind==='retention') {
      const targets=[...new Set([...(readPromptFields(this.source).sections.find(s=>s.key==='subject_definitions')?.entries??[]).filter(e=>e.kind==='definition').map(e=>e.value.target),
        ...(this.editor.referenceOptions?.()??[]).map(r=>'@'+r.name),value.target].filter(Boolean))];
      this.field(row,'Reference',value.target,target=>edit({target}),{options:targets});
      const numbers=promptShots(this.source).shots.map(s=>Number(/\d+/.exec(s.label)[0]));
      this.field(row,'Appears in shots',value.shots,shots=>edit({shots}),{options:numbers.map(n=>[n,`Shot ${n}`]),multiple:true});
      this.field(row,'Reference role or scope',value.scope,scope=>edit({scope}),{suggestions:['first frame','keyframe','last frame','composition','storyboard','cut and pacing structure']});
      const markers=/^@(?:audio|video_audio)/.test(value.target)?RETENTION_AUDIO:RETENTION_VISUAL;
      this.field(row,'Relationship',value.relationship,relationship=>edit({relationship}),{suggestions:markers});
      if(value.relationship&&!markers.includes(value.relationship))row.append(el('small','h3ct-hint','Custom relationship; outside the expected H3 vocabulary.'));
      this.field(row,'Retention details',value.detail,detail=>edit({detail}),{area:true});
    } else if(kind==='summary') {
      this.field(row,'Task types',value.taskTypes??[],chosen=>this.edit(section,index,key,kind,current=>({taskTypes:[...chosen,...current.taskTypes.filter(t=>!SUMMARY_TASKS.includes(t))]})),{options:SUMMARY_TASKS,multiple:true});
      const custom=(value.taskTypes??[]).filter(t=>!SUMMARY_TASKS.includes(t));
      this.field(row,'Custom task types',custom.join(' + '),text=>this.edit(section,index,key,kind,current=>({taskTypes:[...current.taskTypes.filter(t=>SUMMARY_TASKS.includes(t)),...text.split(/\s*\+\s*/).filter(Boolean)]})));
      this.field(row,'Summary',value.text,text=>edit({text}),{area:true});
    } else {
      this.field(row,entry.shot?`Shot ${entry.shot} description`:section==='overall_soundscape'?'Soundscape':section==='non_diegetic_music'?'Background music':'Existing text',value.text,text=>edit({text}),{area:true});
    }
    if(kind!=='narrative')row.append(button('Remove entry',()=>edit(null)));
  }
  render() {
    this.destroy();const video=this.editor.video?.();if(!video)return;
    const active=document.activeElement,key=this.root.contains(active)?active.dataset?.key:null;
    const selection=key&&typeof active.selectionStart==='number'?[active.selectionStart,active.selectionEnd]:null;
    this.source=video.prompt;this.root.disabled=!!this.editor.readOnly?.length;this.controls.clear();this.root.replaceChildren();
    const parsed=readPromptFields(this.source,{tags:this.tags()});
    const visual=parsed.sections.some(s=>s.key==='detailed_description')?'detailed_description':'integrated_multimodal_description';
    const keys=['subject_definitions','summary','retention_analysis',visual,'overall_soundscape','non_diegetic_music'];
    if(parsed.sections.some(s=>s.key==='existing'||s.key==='alignment'))keys.push('existing');
    this.section??=parsed.sections[0]?.key??visual;if(this.section==='alignment')this.section='existing';
    const tabs=el('div','h3pf-tabs');tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Prompt sections');
    for(const name of keys) {
      const tab=button(SECTION_TITLES[name]??'Existing text',()=>{if(!this.canLeave())return;this.section=name;this.render();});
      tab.setAttribute('title',SECTION_TITLES[name]??'Existing text');
      tab.classList.toggle('empty',!parsed.sections.filter(s=>s.key===name).some(s=>s.entries.some(e=>e.range.before.trim())));
      tab.setAttribute('role','tab');tab.setAttribute('aria-selected',String(name===this.section));tab.tabIndex=name===this.section?0:-1;
      tab.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();
        const at=keys.indexOf(this.section),next=event.key==='Home'?0:event.key==='End'?keys.length-1:(at+(event.key==='ArrowRight'?1:-1)+keys.length)%keys.length;
        if(this.canLeave()){this.section=keys[next];this.render();}});tabs.append(tab);
    }
    this.root.append(tabs);
    this.note=el('p','h3pf-error',this.message);this.note.setAttribute('role','status');this.root.append(this.note);
    if(this.hasDrafts())this.root.append(button('Discard draft',()=>this.discardDrafts()));
    let body=el('div');body.setAttribute('role','tabpanel');body.setAttribute('aria-label',SECTION_TITLES[this.section]??'Existing text');this.root.append(body);
    if(['summary','overall_soundscape','non_diegetic_music'].includes(this.section)) {
      const selected=promptSections(this.source)?.find(s=>s.key===this.section);
      const stashKey=video.id+':'+this.section;
      const block=new SwitchSection('Include in prompt',{onToggle:on=>{
        const current=promptSections(video.prompt)?.find(s=>s.key===this.section);
        if(!current||this.editor.readOnly?.length)return;
        const before=video.prompt.slice(current.bodyStart,current.end);
        if(!on)this.sectionStash.set(stashKey,before);
        const text=on?this.sectionStash.get(stashKey)??before:'\n\n';
        const source=video.prompt,next=replacePromptRanges(source,[{start:current.bodyStart,end:current.end,before,text}]);
        this.editor.applyPrompt(source,next,{structural:true});this.render();
      }});
      block.set(!selected||selected.fields.some(f=>f.value.trim()));
      body.append(block.root);body=block.body;
    }
    const sections=parsed.sections.filter(s=>s.key===this.section||(this.section==='existing'&&s.key==='alignment'));
    let shown=0;
    for(const section of sections)for(const [index,entry] of section.entries.entries()){this.row(body,section.key,entry,index,section.key+':'+index);shown++;}
    for(const draft of this.newRows.filter(r=>r.section===this.section)){this.row(body,draft.section,draft,null,draft.key);shown++;}
    if(!shown)body.append(el('p','h3ct-hint','Empty. Add only the fields this clip needs.'));
    if(this.section==='subject_definitions') {
      if(this.editor.state.bible&&this.editor.cast)body.append(this.editor.cast.scheduleAdd(this.editor.box()));
      else body.append(button('Open Cast',()=>this.editor.cast?.open?.(null)));
    }
    const kind=this.section==='subject_definitions'?'definition':this.section==='retention_analysis'?'retention':this.section==='summary'?'summary':'existing';
    if(this.section!=='existing')body.append(button(kind==='definition'?'Add definition':kind==='retention'?'Add retention':kind==='summary'?'Add summary':'Add text',()=>{
      const max=Math.max(0,...[...`${this.source} ${this.editor.state.prompt??''}`.matchAll(/<Subject (\d+)>/g)].map(m=>Number(m[1])));
      const value=kind==='definition'?{target:`<Subject ${max+1}>`,description:'',sources:[]}:kind==='retention'?{target:'',shots:[],scope:'',relationship:'',detail:''}:kind==='summary'?{taskTypes:[],text:''}:{text:''};
      const draft={section:this.section,kind,key:'new:'+ ++ids,value};this.newRows.push(draft);this.drafts.set(draft.key,{value});this.render();
    }));
    const restored=this.controls.get(key);if(restored){restored.focus?.();if(selection)restored.setSelectionRange?.(...selection);}
  }
}
