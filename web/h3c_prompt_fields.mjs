import {promptSections,replacePromptRanges} from './h3c_prompt_sections.mjs';

export const RETENTION_VISUAL=['fully_preserved','partially_preserved','attribute_transfer','weak_reference'];
export const RETENTION_AUDIO=['fully_copy','partially_copy','reference','weak_reference'];
export const SUMMARY_TASKS=['keyframe completion','reference generation','video editing','video continuation','audio reuse','audio reference'];
export const SECTION_TITLES={subject_definitions:'Subjects & references',summary:'Summary',retention_analysis:'Reference retention',
  integrated_multimodal_description:'Shots',detailed_description:'Shots',overall_soundscape:'Soundscape',non_diegetic_music:'Background music'};
const ORDER=['subject_definitions','summary','retention_analysis','integrated_multimodal_description','detailed_description','overall_soundscape','non_diegetic_music'];
export const withoutDialogue=text=>text.replace(/<d>[\s\S]*?(?:<\/d>|$)/g,m=>' '.repeat(m.length));
const labelPattern='(?:<(?:Subject|Picture|Video|Audio) [1-9]\\d*>|@(?:image|video_audio|video|audio)[1-9]\\d*)';
const targetOf=(target,tags)=>target.startsWith('<Subject ')||target.startsWith('@')?target:
  tags.filter(t=>t.tag===target).length===1?'@'+tags.find(t=>t.tag===target).name:null;
const range=(source,start,end)=>({start,end,before:source.slice(start,end)});
const entryOf=(source,part,kind,value,shot=null)=>({kind,shot,range:range(source,part.entryStart??part.start,part.entryEnd??part.end),value});

export function readPromptFields(source,{tags=[]}={}) {
  const parsed=promptSections(source);
  if(!parsed)return {source,problems:[],sections:source.trim()?[{key:'integrated_multimodal_description',entries:[{kind:'existing',shot:null,range:range(source,0,source.length),value:{text:source}}]}]:[]};
  const sections=parsed.map(section=>({key:section.key,entries:section.fields.map(part=>{
    const raw=source.slice(part.entryStart??part.start,part.entryEnd??part.end);
    const definition=new RegExp(`^(${labelPattern})\\s+is\\s+([\\s\\S]+)$`).exec(raw);
    if(section.key==='subject_definitions'&&definition) {
      const target=targetOf(definition[1],tags);
      if(target) {
        let description=definition[2],sources=[],match;
        while((match=/; (?:([^;\r\n]*?) )?reference: @((?:image|video_audio|video|audio)\d+)$/.exec(description))) {
          sources.unshift({slot:match[2],role:match[1]??''});description=description.slice(0,match.index);
        }
        return entryOf(source,part,'definition',{target,description,sources});
      }
    }
    const retention=new RegExp(`^(${labelPattern})\\s*(?:\\(([^)]*)\\))?\\s*:\\s*([^\\n]+?)(?:\\s+-\\s+([\\s\\S]*))?$`).exec(raw);
    if(section.key==='retention_analysis'&&retention) {
      const target=targetOf(retention[1],tags);
      const scope=retention[2]??'';
      if(target)return entryOf(source,part,'retention',{target,shots:[...scope.matchAll(/\[Shot (\d+)\]/g)].map(m=>Number(m[1])),
        scope:scope.replace(/appears in\s*/,'').replace(/\[Shot \d+\](?:,\s*)?/g,'').trim(),relationship:retention[3],detail:retention[4]??''});
    }
    if(section.key==='summary') {
      const prefix=/^\[([^\]]*)\]\s*/.exec(part.value);
      return entryOf(source,part,'summary',{taskTypes:prefix?prefix[1].split(/\s*\+\s*/):[],text:prefix?part.value.slice(prefix[0].length):part.value});
    }
    const shot=/^\[Shot (\d+)\]$/.exec(part.label);
    return entryOf(source,part,shot?'narrative':'existing',{text:part.value},shot?Number(shot[1]):null);
  })}));
  return {source,sections,problems:[]};
}

function serialize(kind,value) {
  if(kind==='definition') {
    if(!value.target||!value.description?.trim())throw new Error('Choose a target and describe it first.');
    if((value.sources??[]).some(s=>!s.slot))throw new Error('Choose the source for this reference.');
    return `${value.target} is ${value.description}`+(value.sources??[]).map(s=>`; ${s.role?s.role+' ':''}reference: @${s.slot.replace(/^@/,'')}`).join('');
  }
  if(kind==='retention') {
    if(!value.target||!value.relationship?.trim())throw new Error('Choose a reference and relationship first.');
    const shots=[...new Set(value.shots??[])].sort((a,b)=>a-b).map(n=>`[Shot ${n}]`).join(', ');
    const where=shots?`${value.target.startsWith('<Subject ')?'appears in ':''}${shots}${value.scope?' '+value.scope:''}`:value.scope;
    return `${value.target}${where?` (${where})`:''}: ${value.relationship}${value.detail?' - '+value.detail:''}`;
  }
  if(kind==='summary')return `${value.taskTypes?.length?'['+value.taskTypes.join(' + ')+'] ':''}${value.text??''}`;
  return value.text??'';
}

function addSection(source,key,text) {
  const sections=promptSections(source);
  if(!sections&&source.trim()) {
    const visual=['subject_definitions','summary','retention_analysis'].includes(key)?'detailed_description':'integrated_multimodal_description';
    source=`${visual}:\n${source}`;
  }
  const parsed=promptSections(source)??[];
  if(new RegExp(`^\\s*${key}:`,'m').test(withoutDialogue(source)))throw new Error('Resolve duplicate or ambiguous sections in Existing text first.');
  const next=parsed.find(s=>ORDER.indexOf(s.key)>ORDER.indexOf(key)&&ORDER.includes(s.key));
  const at=next?.headerStart??source.length;
  return source.slice(0,at)+(at&&source[at-1]!=='\n'?'\n\n':'')+`${key}:\n${text}`+(at<source.length?'\n\n':'')+source.slice(at);
}

export function writePromptField(source,edit,{tags=[]}={}) {
  if(source!==edit.expectedSource)throw new Error('The prompt changed. Reopen this field before editing.');
  const {entry,kind,value,section}=edit;
  if(value===null) {
    if(!entry)return source;
    if(kind==='definition') {
      const rest=source.slice(0,entry.range.start)+source.slice(entry.range.end);
      if(withoutDialogue(rest).includes(entry.value.target))throw new Error('This subject/reference is still used in the prompt. Remove those uses first.');
    }
    return replacePromptRanges(source,[{...entry.range,text:''}]);
  }
  let text=serialize(kind,value);
  if(entry) {
    if(kind==='narrative') {
      // Existing shot labels and their original boundary remain owned by the shot editor.
      const label=/^\[Shot \d+\]\s*/.exec(entry.range.before);
      if(label)text=label[0]+text;
    }
    return replacePromptRanges(source,[{...entry.range,text}]);
  }
  if(!text.trim())return source;
  const parsed=promptSections(source),existing=parsed?.find(s=>s.key===section);
  if(!existing)return addSection(source,section,text);
  const end=existing.end??source.length,empty=existing.fields.every(f=>!f.value.trim());
  const at=empty?end:source.slice(0,end).trimEnd().length;
  return replacePromptRanges(source,[{start:at,end:at,before:'',text:(source[at-1]==='\n'?'':'\n')+text}]);
}
