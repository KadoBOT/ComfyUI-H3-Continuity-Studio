import {ImageJobClient} from './h3c_image_jobs.mjs?v=441234615008';
// h3_continuity/ph3_image_nodes.py describes the same recipe; keep the two in step.
export const SELF_RECIPE_CLASS = 'H3C_PH3ImageStill';
const SELF_RECIPE = {version:2, adapter:'pixels', label:'P-H3-Image', reference_limit:8, reference_label:'<Picture {index}>'};
const SELF_RECIPES = {[SELF_RECIPE_CLASS]:SELF_RECIPE,
  H3C_MiniMaxH3ImageStill:{...SELF_RECIPE,label:'MiniMax H3 Image'}};
// Resolve explicit local locators against this snapshot, never against saved execution IDs.
export function captureRecipe({workflow, output}, timelineId) {
  const fail = message => {throw new Error(`Still recipe: ${message}`);};
  let link = output?.[String(timelineId)]?.inputs?.still_recipe;
  if (link == null) return null;
  const switches = new Set();
  while (output[link?.[0]]?.class_type === 'LazySwitchKJ') {
    if (!Array.isArray(link) || link.length!==2 || link[1]!==0 || switches.has(link[0])) fail('still_recipe switch connection is invalid or cyclic');
    switches.add(link[0]);
    const inputs=output[link[0]].inputs, controls=new Set();
    let selected=inputs.switch;
    while (Array.isArray(selected)) {
      const node=output[selected[0]];
      if (selected.length!==2 || selected[1]!==0 || node?.class_type!=='PrimitiveBoolean' || controls.has(selected[0])) fail('recipe switch must use a literal boolean or native PrimitiveBoolean control');
      controls.add(selected[0]);
      selected=node.inputs?.value;
    }
    if (typeof selected!=='boolean') fail('recipe switch must use a literal boolean or native PrimitiveBoolean control');
    link=inputs[selected?'on_true':'on_false'];
  }
  // Ready-made image nodes expose their own recipe at slot 1.
  const selfRecipe = SELF_RECIPES[output[link?.[0]]?.class_type];
  const own = Array.isArray(link) && link.length===2 && typeof link[0]==='string' && link[1]===1 && !!selfRecipe;
  if (!own && (!Array.isArray(link) || link.length!==2 || typeof link[0]!=='string' || link[1]!==0)) fail('still_recipe must connect to H3 Still Recipe or P-H3-Image Still or MiniMax H3 Image Still');
  const adapter = output[link[0]];
  if (!own && adapter?.class_type !== 'H3C_StillRecipe') fail('still_recipe must connect to H3 Still Recipe or P-H3-Image Still or MiniMax H3 Image Still');
  const image = own ? [link[0], 0] : adapter.inputs.image;
  if (!Array.isArray(image) || image.length!==2 || typeof image[0]!=='string' || !Number.isInteger(image[1]) || image[1]<0 || !output[image[0]]) fail('image output is missing or muted');
  const definitions = new Map((workflow.definitions?.subgraphs ?? []).map(g=>[g.id,g]));
  function locate(path) {
    let graph = workflow, node;
    for (let i=0;i<path.length;i++) {
      node = graph?.nodes?.find(n=>String(n.id)===String(path[i]));
      if (!node || node.mode === 2 || node.mode === 4) return null;
      if (i < path.length-1) graph = definitions.get(node.type);
    }
    return {node, graph};
  }
  let ownerPath = String(link[0]).split(':'), input = 'image', originPath;
  if (own) {
    if (!locate(ownerPath)) fail('image output is missing or muted');
    originPath = ownerPath;
    ownerPath = [];
  }
  // Native grouping may put the adapter behind one or more subgraph input boundaries.
  while (ownerPath.length) {
    const found = locate(ownerPath);
    const socket = typeof input==='number' ? found?.node.inputs?.[input] : found?.node.inputs?.find(i=>i.name===input);
    const wire = found?.graph.links?.find(l=>String(Array.isArray(l)?l[0]:l.id)===String(socket?.link));
    if (!wire) fail('image connection is missing');
    const origin = Array.isArray(wire)?wire[1]:wire.origin_id;
    if (String(origin)===String(found.graph.inputNode?.id)) {
      ownerPath=ownerPath.slice(0,-1);
      input=Array.isArray(wire)?wire[2]:wire.origin_slot;
    } else {
      originPath=[...ownerPath.slice(0,-1),String(origin)];
      break;
    }
  }
  if (!originPath) fail('image connection is missing');
  const generator = locate(originPath)?.node;
  // The connected subgraph defines the local namespace; a flat recipe uses its containing graph.
  const base = definitions.has(generator?.type) ? originPath : originPath.slice(0,-1);
  let bindings;
  if (own) {
    const self = {node:[originPath.at(-1)]}, at = input => ({...self, input});
    bindings = {...selfRecipe, prompt:at('prompt'), instruction:at('instruction'), seed:at('seed'),
      size:{width:[at('width')], height:[at('height')]},
      references:Array.from({length:SELF_RECIPE.reference_limit}, (_, i)=>at(`images.image_${i+1}`))};
  } else try {bindings=JSON.parse(adapter.inputs.bindings);} catch {fail('bindings must be valid JSON');}
  if (!bindings || typeof bindings !== 'object' || Array.isArray(bindings)) fail('bindings must be an object');
  function resolve(locator, label, isOutput=false) {
    const port = isOutput ? `output ${locator?.output}` : locator?.input;
    const invalid = () => fail(`${label} (${port ?? 'port'}) is missing, muted or invalid`);
    if (!Array.isArray(locator?.node) || !locator.node.length || locator.node.some(id=>!['string','number'].includes(typeof id)||String(id).includes(':'))) invalid();
    const path = [...base,...locator.node.map(String)], id=path.join(':'), live=locate(path);
    if (!live || !output[id] || output[id].class_type!==live.node.type) invalid();
    if (isOutput) {
      if (locator.output!==0) invalid();
      return {node:id,output:0};
    }
    if (typeof port!=='string' || !(Object.hasOwn(output[id].inputs,port) || live.node.inputs?.some(i=>i.name===port))) invalid();
    return {node:id,input:port};
  }
  const list = (value,label) => {
    if (!Array.isArray(value)) fail(`${label} must be a locator array`);
    return value.map((loc,index)=>resolve(loc,`${label}[${index}]`));
  };
  const version=bindings.version ?? 1, kind=bindings.adapter ?? 'h3';
  if (![1,2].includes(version) || !['h3','pixels'].includes(kind)) fail('unsupported recipe version or adapter');
  // P-H3 declares all eight autogrow ports even when ComfyUI only shows the first empty socket.
  const references=own ? bindings.references.map(({input})=>({node:String(image[0]),input})) : list(bindings.references,'references');
  const promptPort=resolve(bindings.prompt,'prompt');
  if(kind==='pixels'&&bindings.reference_label==='Image {index}'&&output[promptPort.node]?.class_type==='TextEncodeQwenImage21')bindings.reference_label='<image{index}>';
  if (version===2 && (!Number.isInteger(bindings.reference_limit) || bindings.reference_limit<0 || bindings.reference_limit>references.length)) fail('reference_limit exceeds declared ports');
  if (version===2 && (typeof bindings.reference_label!=='string' || !bindings.reference_label.includes('{index}'))) fail('reference_label must contain {index}');
  return {version,...(version===2?{adapter:kind,reference_limit:bindings.reference_limit,reference_label:bindings.reference_label,label:bindings.label ?? 'Image generator'}:{}),output:[String(image[0]),image[1]],bindings:{
    prompt:resolve(bindings.prompt,'prompt'),instruction:resolve(bindings.instruction,'instruction'),
    seed:resolve(bindings.seed,'seed'),
    size:{width:list(bindings.size?.width,'size.width'),height:list(bindings.size?.height,'size.height')},
    references,...(bindings.conditioning?{conditioning:resolve(bindings.conditioning,'conditioning',true)}:version===1?{conditioning:resolve(bindings.conditioning,'conditioning',true)}:{}),
    ...(bindings.negative?{negative:resolve(bindings.negative,'negative')}:{}),
  }};
}


// Root IDs are direct; shared nested definitions need an unambiguous current instance.
export function captureTimelineId(snapshot, nodeId, {root = false} = {}) {
  const local=String(nodeId),output=snapshot.output ?? {};
  if (root) {
    if (output[local]?.class_type!=='H3C_Timeline') throw new Error('Still Timeline instance is missing or muted.');
    return local;
  }
  const candidates=Object.keys(output).filter(id=>id.endsWith(':'+local)&&output[id]?.class_type==='H3C_Timeline');
  if (candidates.length!==1) throw new Error(`Still Timeline instance is ${candidates.length?'ambiguous across copied native groups':'missing or muted'}.`);
  return candidates[0];
}

export function captureStillBody(snapshot, timelineId, request) {
  return {...stillTimelineBody(snapshot,timelineId,request),
    workflow:{ui:structuredClone(snapshot.workflow),api:structuredClone(snapshot.output),timeline_node:timelineId}};
}

// The request with the Timeline's literal name, text and context frames, without a copy of the workflow.
export function stillTimelineBody(snapshot, timelineId, request) {
  const inputs=snapshot.output[timelineId].inputs;
  const scalar=name=>{
    const fail=()=>{throw new Error(`Still Timeline ${name} must use a literal value or a native primitive control with a literal value.`);};
    let value=inputs[name];
    if (Array.isArray(value)) {
      const producer=snapshot.output[value[0]];
      if (value.length!==2 || value[1]!==0 || !/^Primitive(Int|Float|Boolean|String|StringMultiline)$/.test(producer?.class_type ?? '')) fail();
      value=producer.inputs?.value;
    }
    if (value==null || typeof value==='object') fail();
    return value;
  };
  const settings={context_frames:scalar('context_frames')};
  return {...structuredClone(request),name:scalar('name'),timeline:scalar('timeline'),settings};
}

const sameTarget = (a,b) => a?.kind===b?.kind && a?.shot===b?.shot;

export class StillClient extends ImageJobClient {
  constructor({request,read,write,capture,context}) {
    super({request,capture,context,receipts:()=>read().still_requests??[],
      identify:prepared=>({box:prepared.request.box,target:structuredClone(prepared.request.target)})});
    Object.assign(this,{read,write});
  }
  async save(receipt,context=this.context?.()) {
    if(context!==this.context?.())throw Error("The generation changed while processing this still.");
    const state=structuredClone(this.read());
    const receipts=state.still_requests??=[];
    const index=receipts.findIndex(item=>item.request_id===receipt.request_id && item.prompt_id===receipt.prompt_id);
    if(index<0) receipts.push(structuredClone(receipt));else receipts[index]={...receipts[index],...structuredClone(receipt)};
    if(receipt.state==='complete') {
      const box=state.boxes.find(box=>box.id===receipt.box);
      if(box) {
        let preview=box.previews?.find(item=>sameTarget(item.target ?? (item.shot===1?{kind:'first'}:{kind:'shot',shot:item.shot}),receipt.target));
        if(!preview) (box.previews??=[]).push(preview={target:structuredClone(receipt.target),frame:receipt.provenance.frame});
        const images=preview.images??=[];
        for(const image of receipt.images??[]) if(!images.some(item=>item.prompt_id===image.prompt_id && item.batch_index===image.batch_index)) images.push(structuredClone(image));
      }
    }
    await this.write(state);
    return receipt;
  }

}

export function isolateVideoPrompt(snapshot,timelineId,outputs) {
  const copy=structuredClone(snapshot),graph=copy.output,keep=new Set();
  // Validation follows raw/lazy links too, so detach before walking dependencies.
  for(const node of Object.values(graph)) if(node.class_type==='H3C_Timeline') delete node.inputs.still_recipe;
  function visit(id) {
    if(keep.has(id)) return;
    if(!graph[id]) throw new Error(`Video input ${id} is missing.`);
    keep.add(id);
    for(const value of Object.values(graph[id].inputs??{})) if(Array.isArray(value)&&value.length===2&&typeof value[0]==='string'&&Number.isInteger(value[1])) visit(value[0]);
  }
  outputs.forEach(visit);
  if(!keep.has(timelineId)) throw new Error('No video output is connected to this Timeline.');
  for(const id of keep) {
    const node=graph[id];
    if(node.class_type!=='H3LabSaveSegment' || node.inputs.segment?.[0]!==timelineId) continue;
    const enabled=node.inputs.enabled;
    const operation=Array.isArray(enabled)&&enabled[1]===2?graph[enabled[0]]:null;
    if(enabled===false || (operation?.class_type==='H3LabOperation' && operation.inputs.operation!=='Generate next / selected'))
      throw new Error('Set the H3 Lab operation to "Generate next / selected" to save this clip in the Timeline.');
  }
  copy.output=Object.fromEntries(Object.entries(graph).filter(([id])=>keep.has(id)));
  return copy;
}

export function videoOutputs(snapshot,timelineId,definitions) {
  const graph=snapshot.output;
  function depends(id,seen=new Set()) {
    if(id===timelineId) return true;
    if(seen.has(id)) return false;seen.add(id);
    return Object.values(graph[id]?.inputs??{}).some(value=>Array.isArray(value)&&value.length===2&&typeof value[0]==='string'&&depends(value[0],seen));
  }
  return Object.keys(graph).filter(id=>definitions[graph[id].class_type]?.output_node && depends(id));
}

export function recipeControls(snapshot,recipe) {
  function value(locator,computed=false) {
    let value=snapshot.output[locator.node].inputs[locator.input];
    const seen=new Set();
    while(Array.isArray(value)) {
      const node=snapshot.output[value[0]];
      if(value[1]!==0 || seen.has(value[0]) || !/^Primitive(Int|Float|Boolean|String|StringMultiline)$/.test(node?.class_type??'')) {
        if(computed)return undefined;
        throw new Error('Still controls must use native primitive values.');
      }
      seen.add(value[0]);
      value=node.inputs.value;
    }
    return value;
  }
  const additionalReferences=[],sceneMaps=[];
  if(recipe.adapter==='pixels') (recipe.bindings.references??[]).forEach((locator,index)=>{
    const link=snapshot.output[locator.node]?.inputs[locator.input];
    if(!(Array.isArray(link)&&link.length===2&&typeof link[0]==='string'&&Number.isInteger(link[1])&&link[1]>=0&&snapshot.output[link[0]]))return;
    (snapshot.output[link[0]].class_type==='H3C_SceneMap'&&link[1]===0?sceneMaps:additionalReferences).push(`@still${index+1}`);
  });
  return {instruction:String(value(recipe.bindings.instruction)??''),seed:value(recipe.bindings.seed),...(recipe.version===2?{width:value(recipe.bindings.size.width.at(-1),true),height:value(recipe.bindings.size.height.at(-1),true),label:recipe.label??'Image generator',adapter:recipe.adapter??'h3',referenceLabel:recipe.reference_label}:{}),...(additionalReferences.length?{additionalReferences}:{}),...(sceneMaps.length?{sceneMaps}:{})};
}

// The wiring a compiled prompt follows, read from the live graph: serializing the workflow instead takes several ms on
// a large one, and the Studio asks on every redraw. nested: the graph holds a subgraph instance.
export function graphWiring(graph){
 const nodes=graph=>[...(graph?.nodes??graph?._nodes??[])];
 const links=graph=>[...(graph?.links?.values?.()??Object.values(graph?.links??{}))]
  .map(link=>Array.isArray(link)?link.slice(0,5):[link.id,link.origin_id,link.origin_slot,link.target_id,link.target_slot]);
 const ports=node=>[node.id,node.type,node.mode,node.inputs?.map(port=>port.link),node.outputs?.map(port=>port.links)];
 const groups=[...(graph?.subgraphs?.values?.()??[])],ids=new Set(groups.map(group=>group.id));
 return {nested:nodes(graph).some(node=>ids.has(node.type)),
  signature:JSON.stringify([graph?.id,nodes(graph).map(ports),links(graph),groups.map(group=>[group.id,nodes(group).map(ports),links(group)])])};
}

// Graph capability, including native nested instances after graphToPrompt compilation.
export function hasVideoOutput({output},timelineId){
 const depends=(id,seen=new Set())=>{
  if(String(id)===String(timelineId))return true;
  if(seen.has(id))return false;seen.add(id);
  return Object.values(output?.[id]?.inputs??{}).some(v=>Array.isArray(v)&&v.length===2&&typeof v[0]==='string'&&depends(v[0],seen));
 };
 return Object.entries(output??{}).some(([id,node])=>['H3C_SaveSegment','SaveVideo','VHS_VideoCombine','SaveAnimatedPNG','SaveAnimatedWEBP'].includes(node.class_type)&&depends(id));
}
