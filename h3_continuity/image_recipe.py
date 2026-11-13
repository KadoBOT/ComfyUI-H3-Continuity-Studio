"""Invoke a native pixel recipe using pinned files or compiled IMAGE outputs."""
import copy
import hashlib
import json
import re
import uuid

from . import timeline as rules, timeline_prepare

PH3_IMAGE_CLASS = 'H3C_PH3ImageStill'
MINIMAX_IMAGE_CLASS = 'H3C_MiniMaxH3ImageStill'

REFERENCE_USE = {
    'identity': 'Use this for the named person identity only; ignore its background and clothing unless requested.',
    'additional identity': 'Use this additional view to reinforce the matching subject identity. Do not introduce another person or copy its pose, clothing or background; follow the requested scene.',
    'appearance': 'Use this for the named wardrobe and appearance; ignore its background.',
    'location': 'Use this as the authoritative room layout and environment geometry, furniture placement, materials and lighting. Preserve this world layout across camera views.',
    'prop': 'Use this for the named object or garment design only; ignore its background and any unrelated people.',
    'scene_layout': 'Use this as the approved environment arrangement and prop placement.',
    'scene anchor': 'Use this for established scene composition; keep the approved location geometry and apply the requested camera and wardrobe.',
    'current action state': 'Use this for pose and action progression; do not override the approved location layout or requested wardrobe.',
}

QWEN_REFERENCE_USE = {
    **REFERENCE_USE,
    'identity': 'Use this for the named person identity. Reconstruct their pose, expression and lighting for the requested frame; the reference pose and background are not constraints.',
    'location': 'Use this for the authoritative environment geometry, landmarks, furniture placement and materials. Any separate panels show the same place from different cameras. Rebuild the place from the requested camera with the requested lighting; preserve the world layout.',
    'scene anchor': 'Use this for established scene layout and visual continuity, with composition adapted to the requested camera.',
    'current action state': 'Use this for applicable action-state details; the requested pose and moment take precedence over its earlier pose and framing.',
}


def _roles(ref):
    return {role.split(':', 1)[0].strip() for role in ref['roles']}


def _scene_prompt(prompt, descriptions, environment):
    operation = ('The target image is a new still of the requested visible state, composed for the requested camera; '
                 'it is not an edit, restyle or copy of any reference picture. The reference pictures only supply what is assigned to them. '
                 'No reference picture contributes its framing, crop, panel grid, gutters, borders, lettering, color grading or rendering: '
                 'the target image is one continuous full-frame view whose lighting and colors follow the requested scene. ')
    if environment:
        operation += (f'The place shown in {environment} is rebuilt from the requested viewpoint, '
                      'keeping its world geometry, landmarks, materials and arrangement. ')
    else:
        operation += 'The scene is composed from the referenced subjects or objects and the requested setting. '
    operation += ('Preserve the assigned identity and designs while adapting pose, expression, wardrobe and lighting to the requested frame. '
                  'Render subjects and environment together with consistent perspective, scale, illumination direction and color, '
                  'reflected light, cast and contact shadows, depth of field and physically plausible occlusion. '
                  'Use each reference only for its assigned role.\n\nReference roles:\n')
    return operation + '\n'.join(descriptions) + '\n\nRequested visible state:\n' + prompt


def _link(value):
    return isinstance(value, (tuple, list)) and len(value) == 2 and isinstance(value[0], str) and type(value[1]) is int and value[1] >= 0


def _ancestry(graph, output):
    found = {}
    def visit(node):
        if node in found:
            return
        if node not in graph:
            raise ValueError(f'H3 still recipe dependency {node!r} is missing')
        found[node] = graph[node]
        for value in graph[node].get('inputs', {}).values():
            if _link(value):
                visit(value[0])
    visit(output[0])
    return found


def _scalar(graph, value):
    if _link(value):
        producer = graph[value[0]]
        if producer['class_type'] not in ('PrimitiveInt', 'PrimitiveFloat', 'PrimitiveString', 'PrimitiveStringMultiline'):
            raise ValueError('H3 still settings need a literal or native primitive value')
        return producer['inputs']['value']
    return value


def _image_port(graph,loc):
    import nodes
    cls=nodes.NODE_CLASS_MAPPINGS.get(graph[loc['node']]['class_type'])
    if cls is None:raise ValueError('Still recipe reference node is not registered: '+graph[loc['node']]['class_type'])
    schema=cls.INPUT_TYPES();inputs={**schema.get('required',{}),**schema.get('optional',{})};port=loc['input']
    item=inputs.get(port)
    if item is not None and item[0]=='IMAGE':return
    parent,_,child=port.partition('.')
    item=inputs.get(parent)
    if item and item[0]=='COMFY_AUTOGROW_V3':
        template=item[1].get('template',{});spec=template.get('input',{});members={**spec.get('required',{}),**spec.get('optional',{})}
        if child in template.get('names',[]) and len(members)==1 and next(iter(members.values()))[0]=='IMAGE':return
    raise ValueError(f'Still reference port {loc["node"]}.{port} must be a native IMAGE input')

def prepare(recipe, workflow, request, references):
    body = dict(request, recipe=recipe, workflow=workflow)
    frame = request.get("frame", 0)
    # Normalize source-slot notation before reference discovery. Transport ordinals are assigned later.
    original_prompt=body.get('prompt')
    body=copy.deepcopy(body)
    if isinstance(body.get('prompt'),str):
        body['prompt']=re.sub(r'<image([1-9]\d*)>',lambda m:'@image'+m[1],body['prompt'],flags=re.I)
    recipe=body['recipe']; bindings=recipe['bindings']; graph=copy.deepcopy(body['workflow']['api'])
    clip_request = bool(body.get('box')) and not body.get('asset_key')
    output=recipe['output']
    if not _link(output) or output[0] not in graph:
        raise ValueError('Still recipe IMAGE output is missing')
    ports=bindings.get('references',[])
    keys=[(loc.get('node'),loc.get('input')) for loc in ports]
    if len(set(keys))!=len(keys):
        raise ValueError('Still recipe has duplicate reference ports')
    controls=[bindings.get(key) for key in ('prompt','instruction','seed','negative')]+[loc for group in bindings.get('size',{}).values() for loc in group]
    scalar_ports={(loc.get('node'),loc.get('input')) for loc in controls if isinstance(loc,dict)}
    if scalar_ports.intersection(keys):raise ValueError('Still reference IMAGE ports collide with scalar controls')
    for loc in ports:
        if loc.get('node') not in graph or not isinstance(loc.get('input'),str):raise ValueError('Still reference IMAGE port is missing')
        _image_port(graph,loc)
    owners={loc['node'] for loc in ports}
    for ref in references:
        if 'output' not in ref:
            continue
        if not _link(ref['output']):
            raise ValueError('Still computed reference IMAGE output is missing')
        if owners.intersection(_ancestry(graph,ref['output'])):
            raise ValueError(f'Still reference @{ref.get("slot", "computed")} depends on the generator reference inputs; connect an independent image source.')
    limit=recipe.get('reference_limit')
    if type(limit) is not int or not 0<=limit<=len(ports):
        raise ValueError('Still recipe reference capacity exceeds declared ports')
    label=recipe.get('reference_label')
    if not isinstance(label,str) or '{index}' not in label:
        raise ValueError('Still recipe reference label must contain {index}')
    def bind(loc,value,optional=False):
        node,port=loc.get('node'),loc.get('input')
        if node not in graph or not isinstance(port,str) or not port or (not optional and port not in graph[node]['inputs']):
            raise ValueError(f'Still recipe port {node}.{port} is missing')
        graph[node]['inputs'][port]=value
    if not isinstance(body.get('prompt'),str):
        raise ValueError('Still prompt must be text')
    for loc in ports:
        if loc.get('node') not in graph or not isinstance(loc.get('input'),str):
            raise ValueError('Still recipe reference port is invalid')
        graph[loc['node']]['inputs'].pop(loc['input'],None)
    if body.get('seed') is not None:
        if type(body['seed']) is not int or not 0<=body['seed']<=rules.MAX_SEED:
            raise ValueError('Still seed must be an unsigned 64-bit integer')
        bind(bindings['seed'],body['seed'])
    size=body.get('size')
    if size is not None and (not isinstance(size,dict) or set(size)!={'width','height'}):
        raise ValueError('Still size needs width and height')
    for dimension in ('width','height'):
        if not bindings['size'].get(dimension):
            raise ValueError(f'Still recipe {dimension} binding is missing')
        if size:
            value=timeline_prepare.setting(dimension,size[dimension])
            for loc in bindings['size'][dimension]: bind(loc,value)
    refs=copy.deepcopy(references)
    # Files share byte identity; computed references share an output in this snapshot.
    unique=[]
    for ref in refs:
        if ref.get('asset_key'):
            ref['assets']=[{'key':ref['asset_key'],'revision':ref.get('approval_revision')}]
        match=next((other for other in unique if other.get('sha256')==ref.get('sha256') and other.get('output')==ref.get('output') and other.get('pin',{}).get('moment')==ref.get('pin',{}).get('moment')),None)
        if match:
            match['roles'].extend(role for role in ref['roles'] if role not in match['roles'])
            match.setdefault('slots',[]).extend([ref['slot']] if ref.get('slot') else [])
            for key in ('title', 'description'):
                if ref.get(key) and ref[key] not in match.get(key, ''):
                    match[key] = '\n'.join(filter(None, [match.get(key), ref[key]]))
            for asset in ref.get('assets',[]):
                if asset not in match.setdefault('assets',[]):match['assets'].append(asset)
        else:
            ref['slots']=[ref['slot']] if ref.get('slot') else []; unique.append(ref)
    if len(unique)>limit:
        raise ValueError(f'Still reference capacity {limit} cannot fit {len(unique)} required references: '+', '.join('/'.join(ref['roles']) for ref in unique))
    qwen = any(graph[loc['node']]['class_type'] == 'TextEncodeQwenImage21' for loc in ports)
    ph3 = any(graph[loc['node']]['class_type'] == PH3_IMAGE_CLASS for loc in ports)
    minimax = any(graph[loc['node']]['class_type'] == MINIMAX_IMAGE_CLASS for loc in ports)
    scene = qwen or ph3 or minimax
    environment = None
    if scene:
        owner = 'Qwen' if qwen else 'MiniMax H3 Image' if minimax else 'P-H3-Image'
        if len({loc['node'] for loc in ports}) != 1:
            raise ValueError(owner + ' scene references must bind directly to one ' + ('TextEncodeQwenImage21' if qwen else MINIMAX_IMAGE_CLASS if minimax else PH3_IMAGE_CLASS) + ' node')
        undeclared = [name for name, value in graph[ports[0]['node']]['inputs'].items()
                      if name.startswith('images.image_') and value is not None]
        if undeclared:
            raise ValueError(owner + ' recipe has undeclared reference inputs: ' + ', '.join(undeclared) + '; add them to the recipe reference bindings')
        ports = sorted(ports, key=lambda loc: int(loc['input'].rsplit('_', 1)[-1]))
        if qwen:
            label = '<image{index}>'
        environment = next((ref for role in ('scene_layout', 'location', 'scene anchor', 'current action state') for ref in unique if role in _roles(ref)), None)
        priority = {'scene_layout': 0, 'location': 1, 'identity': 2, 'additional identity': 2, 'appearance': 3, 'prop': 4,
                    'scene anchor': 5, 'current action state': 6}
        unique.sort(key=lambda ref: (ref is not environment, min((priority.get(role, 7) for role in _roles(ref)), default=7)))
    if ph3 and not size:
        node = 'h3c_ph3_size'
        if node in graph:
            raise ValueError('Still recipe collides with invocation size node')
        graph[node] = {'class_type': 'H3C_PH3StillSize', 'inputs': {
            dimension: copy.deepcopy(graph[bindings['size'][dimension][-1]['node']]['inputs'][bindings['size'][dimension][-1]['input']])
            for dimension in ('width', 'height')}}
        resolution = graph[ports[0]['node']]['inputs'].get('studio_resolution')
        if resolution is not None:
            graph[node]['inputs']['resolution'] = copy.deepcopy(resolution)
        for slot, dimension in enumerate(('width', 'height')):
            for loc in bindings['size'][dimension]:
                bind(loc, [node, slot])
    tags={}; descriptions=[]
    width=graph[bindings['size']['width'][-1]['node']]['inputs'][bindings['size']['width'][-1]['input']]
    height=graph[bindings['size']['height'][-1]['node']]['inputs'][bindings['size']['height'][-1]['input']]
    for at,ref in enumerate(unique):
        if 'output' in ref:
            image=ref['output']
            if not _link(image) or image[0] not in graph:
                raise ValueError('Still computed reference IMAGE output is missing')
        else:
            node=f'h3c_still_source_{at}'
            if node in graph: raise ValueError('Still recipe collides with invocation image source')
            source=copy.deepcopy(ref)
            inputs={'source':json.dumps(source)}
            # Keep calculated dimensions in native inputs so the scheduler evaluates their ancestry.
            if at==0 and not (ph3 or minimax): inputs.update(width=copy.deepcopy(width),height=copy.deepcopy(height))
            graph[node]={'class_type':'H3C_StillImageSource','inputs':inputs}
            image=[node,0]
        bind(ports[at],image,True)
        ref['port']=copy.deepcopy(ports[at]); ref['label']=label.replace('{index}',str(at+1))
        text_label = 'the reference image' if qwen and len(unique) == 1 else ref['label']
        tags.update({slot:text_label for slot in ref['slots']})
        roles=['visual reference' if re.fullmatch(r'image[1-9]\d*',role) else role for role in ref['roles']]
        reference_use = QWEN_REFERENCE_USE if scene else REFERENCE_USE
        usage = list(dict.fromkeys(reference_use[role.split(':',1)[0].strip()] for role in roles
                                   if role.split(':',1)[0].strip() in reference_use))
        context = '. '.join(str(ref[key]) for key in ('title', 'description') if ref.get(key))
        descriptions.append(text_label+': '+', '.join(roles)+('. '+' '.join(usage) if usage else '')+('. '+context if context else ''))
    prompt=body['prompt']
    if descriptions and not clip_request:
        if scene:
            named = ('the reference image' if qwen and len(unique) == 1 else environment['label']) if environment else None
            prompt = _scene_prompt(prompt, descriptions, named)
            # PH3ImageConditioning prepends this to any prompt that does not start with it.
            if ph3:
                prompt = 'Edit <Picture 1>. ' + prompt
        else:
            prompt='Reference roles:\n'+'\n'.join(descriptions)+'\nUse each reference only for its assigned role. Follow the requested camera, pose and action; preserve the approved environment across viewpoints.\n\nRequested frame:\n'+prompt
    # Translate the authored prose and reference context together, without visiting inserted native tokens.
    prompt=re.sub(r'@(image[1-9]\d*|still[1-9]\d*)\b|(?<![\w@<>])(image[1-9]\d*)(?![\w>])',
                  lambda m:tags.get((m[1] or m[2]).lower(),m[0]),prompt,flags=re.I)
    if clip_request and bindings.get('instruction'):
        bind(bindings['instruction'], '')
    bind(bindings['prompt'],prompt)
    if bindings.get('negative') and 'negative' in body: bind(bindings['negative'],body['negative'])
    graph=_ancestry(graph,output)
    for ref in unique:
        if ref['port']['node'] not in graph:raise ValueError('Still reference IMAGE port does not reach the recipe output')
    digest=hashlib.sha256(json.dumps(graph,sort_keys=True).encode()).hexdigest()
    if 'h3c_still_output' in graph: raise ValueError('Still recipe collides with owned output')
    graph['h3c_still_output']={'class_type':'SaveImage','inputs':{'images':list(output),'filename_prefix':'h3_previews/still_'+str(uuid.uuid4())}}
    provenance={key:copy.deepcopy(body.get(key)) for key in ('request_id','box','target','prompt','source','size','asset_key','input_fingerprint')}
    provenance['prompt']=original_prompt
    provenance.update(recipe_sha256=digest,adapter='pixels',generator=recipe.get('label','Image generator'),frame=frame,
                      effective_prompt=prompt,seed=_scalar(graph,graph[bindings['seed']['node']]['inputs'][bindings['seed']['input']]),width=width,height=height,references=unique)
    if clip_request:
        provenance['prompt_policy'] = 'clip-verbatim-v1'
    elif scene and unique:
        provenance.update(prompt_policy='qwen-image-2.1-scene-v2' if qwen else 'p-h3-image-scene-v2',
                          environment_reference=environment['label'] if environment else None)
    if minimax and unique:
        from .minimax_image_nodes import REFERENCE_MEGAPIXELS
        provenance['reference_resize_megapixels'] = REFERENCE_MEGAPIXELS
    return {'ok':True,'prompt_id':str(uuid.uuid4()),'prompt':graph,'outputs':['h3c_still_output'],'provenance':provenance}
