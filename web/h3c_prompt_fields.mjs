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
const descriptor=(key,prefix,rank,advanced=true,suggestions=[],repeatable=false)=>({key,prefix,rank,advanced,suggestions,repeatable});
export const SHOT_FIELDS=[
  descriptor('style','Style',0,false,['Cinematic','Live-action','2D animation','3D CG','Claymation','Watercolor','Vintage film']),
  descriptor('composition','Composition',10,false,['Wide shot','Medium shot','Close-up','Extreme close-up']),
  descriptor('initial_state','Initial state',20),descriptor('trigger','Trigger',30),descriptor('action','Action',40,false,[],true),
  descriptor('contact','Contact',50),descriptor('reaction','Reaction',60),descriptor('shot_size','Shot size',70,true,['Wide','Medium','Close-up','Extreme close-up']),
  descriptor('camera_position','Camera position',80),
  descriptor('camera_movement','Camera movement',90,false,['Zoom In','Zoom Out','Push In','Pull Out','Pan Left','Pan Right','Truck Left','Truck Right','Tilt Up','Tilt Down','Pedestal Up','Pedestal Down','Arc Shot','Tracking Shot','Static Shot','Shake Slightly','Shake Strongly','POV','Roll Clockwise','Roll Counterclockwise','Orbit','Swoop','Whip-pan','Dive','Barrel roll','Handheld']),
  descriptor('camera_direction','Camera direction',100),descriptor('camera_speed','Camera speed',110,false,['Slow','Normal','Fast']),
  descriptor('camera_amplitude','Camera amplitude',120,false,['Small','Normal','Large']),descriptor('camera_subject','Camera subject',130),descriptor('focus','Focus',140),
  descriptor('effect_trigger','Effect N trigger',150),descriptor('effect','Effect N',160,true,['Sparks','Smoke','Dust','Debris','Water','Energy','Explosion','Lightning']),
  descriptor('effect_motion','Effect N motion',170),descriptor('effect_response','Effect N response',180),descriptor('physical_response','Physical response',180),
  descriptor('lighting','Lighting',190,true,['Warm','Cool','Side light','Backlight','Haze','Shallow focus']),descriptor('light_direction','Light direction',200),
  descriptor('colour_contrast','Colour and contrast',210),descriptor('reflections','Reflections',220),descriptor('atmosphere','Atmosphere',230),
  descriptor('materials','Materials',240),descriptor('depth_of_field','Depth of field',250),descriptor('gaze','Gaze',260),descriptor('expression','Expression',270),
  descriptor('breathing','Breathing',280),descriptor('posture','Posture',290),descriptor('hands','Hands',300),descriptor('continuity','Continuity',310),
  descriptor('recovery','Recovery',320),descriptor('end_state','End state',330),descriptor('scene_sound','Scene sound',350,false),
];
const escape=text=>text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const cueRank=value=>{
  const field=SHOT_FIELDS.find(f=>f.key===value.key);
  return field.prefix.includes(' N')?150+(value.index??1)/100+field.rank/100000:field.rank+(value.index??0)/1000;
};
function shotFields(source,part,shot) {
  const masked=withoutDialogue(source),matches=[];
  for(const field of SHOT_FIELDS) {
    let pattern=escape(field.prefix).replace(' N',' ([1-9]\\d*)');
    if(field.repeatable)pattern+='(?: ([1-9]\\d*))?';
    for(const match of masked.slice(part.start,part.end).matchAll(new RegExp('^'+pattern+':[ \\t]*','gm')))
      matches.push({start:part.start+match.index,body:part.start+match.index+match[0].length,field,index:match[1]?Number(match[1]):null});
  }
  matches.sort((a,b)=>a.start-b.start);
  if(!matches.length)return [entryOf(source,part,'narrative',{text:part.value.replace(/^At \d+:[0-5]\d\.\d{3},\s*/i,'')},shot)];
  const entries=[],end=source.slice(0,matches[0].start).trimEnd().length;
  entries.push({kind:'narrative',shot,range:range(source,part.entryStart??part.start,end),
    value:{text:source.slice(part.start,end).replace(/^At \d+:[0-5]\d\.\d{3},\s*/i,'')}});
  matches.forEach((m,i)=>{
    const end=source.slice(0,matches[i+1]?.start??part.end).trimEnd().length;
    const duplicate=matches.filter(other=>other.field.key===m.field.key&&other.index===m.index).length>1;
    entries.push({kind:duplicate?'existing':'cue',shot,range:range(source,m.start,end),
      value:duplicate?{text:source.slice(m.start,end)}:{key:m.field.key,index:m.index,text:source.slice(m.body,end).replace(/\r?\n {2}/g,'\n')}});
  });
  return entries;
}

export function readPromptFields(source,{tags=[]}={}) {
  let parsed=promptSections(source);
  if(!parsed) {
    const markers=[...withoutDialogue(source).matchAll(/^[ \t]*(\[Shot ([1-9]\d*)\])(?=\s|$)/gm)];
    if(!markers.length)return {source,problems:[],sections:source.trim()?[{key:'integrated_multimodal_description',entries:[{kind:'existing',shot:null,range:range(source,0,source.length),value:{text:source}}]}]:[]};
    const fields=[];
    if(source.slice(0,markers[0].index).trim())fields.push({start:0,end:markers[0].index,value:source.slice(0,markers[0].index),label:'Existing text'});
    markers.forEach((m,i)=>{const start=m.index+m[0].length,body=start+source.slice(start).match(/^\s*/)[0].length,end=source.slice(0,markers[i+1]?.index??source.length).trimEnd().length;
      fields.push({entryStart:m.index,entryEnd:end,start:body,end,label:m[1],value:source.slice(body,end)});});
    parsed=[{key:'integrated_multimodal_description',fields}];
  }
  const sections=parsed.map(section=>({key:section.key,entries:section.fields.flatMap(part=>{
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
    return shot?shotFields(source,part,Number(shot[1])):entryOf(source,part,'existing',{text:part.value});
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
  if(entry&&value&&JSON.stringify(entry.value)===JSON.stringify(value))return source;
  if(kind==='cue') {
    if(value===null||!value.text?.trim())return entry?replacePromptRanges(source,[{...entry.range,text:''}]):source;
    const field=SHOT_FIELDS.find(f=>f.key===value.key);
    if(!field||field.prefix.includes(' N')&&(!Number.isInteger(value.index)||value.index<1))throw new Error('Choose a valid detail and positive item number.');
    const prefix=field.prefix.replace(' N',' '+value.index)+(field.repeatable&&value.index?' '+value.index:'');
    const text=prefix+': '+value.text.replace(/\r?\n/g,'\n  ');
    if(entry)return replacePromptRanges(source,[{...entry.range,text}]);
    const entries=readPromptFields(source,{tags}).sections.find(s=>s.key===section)?.entries.filter(e=>e.shot===edit.shot)??[];
    if(!entries.length)throw new Error('Add a shot before adding details.');
    const cues=entries.filter(e=>e.kind==='cue'),singleton=cues.find(e=>e.value.key===value.key&&e.value.index===null);
    const patches=[];
    if(field.repeatable&&value.index&&singleton)patches.push({...singleton.range,text:field.prefix+' 1: '+singleton.value.text.replace(/\r?\n/g,'\n  ')});
    const next=cues.find(e=>cueRank(e.value)>cueRank(value));
    const at=next?.range.start??Math.max(...entries.map(e=>e.range.end));
    patches.push({start:at,end:at,before:'',text:(source[at-1]==='\n'?'':'\n')+text+(next?'\n':'')});
    return replacePromptRanges(source,patches);
  }
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
      const clock=/^At \d+:[0-5]\d\.\d{3},\s*/i.exec(entry.range.before.slice(label?.[0].length??0));
      if(label)text=label[0]+(clock?.[0]??'')+text;
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
