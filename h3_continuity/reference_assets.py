"""Optional approved Story reference images and their entity/look/scene scopes."""
import copy
import hashlib
import json
import re

from . import image_recipe, stills, story_bible, timeline as rules

CATEGORIES = ('cast', 'locations', 'props')
ROLES = ('identity', 'appearance', 'location', 'prop', 'scene_layout')
HASH = re.compile(r'[a-f0-9]{64}')
NO_TEXT = 'The image contains no text, letters or numbers.'
CHARACTER_SHEET = ('A character reference sheet on a plain ivory background{look}. Left: a large close-up of the face or head, '
                   'seen from the front. Right: the full body from head to feet in a relaxed neutral stance, seen from the front. '
                   'Even, soft light; no scenery, props or other characters. ' + NO_TEXT + '\nCharacter: ')
LOCATION_GRID = ('A location reference sheet: one image divided into a grid of 2 rows and 2 columns by thin ivory gutters, '
                 'showing the same place from four clearly different camera positions: in row 1, column 1, a wide establishing '
                 'view from the front; in row 1, column 2, the reverse view from the opposite side, looking back the other way; '
                 'in row 2, column 1, a low ground-level view from one side; in row 2, column 2, a high view looking down on the '
                 'whole place. No two panels repeat the same viewpoint. All four panels show one moment: the same time of day, '
                 'lighting, layout and materials. The location is empty: '
                 'no people, characters, animals or creatures appear in any panel. ' + NO_TEXT + '\nLocation: ')
PEOPLE = re.compile(r'\b(characters?|people|persons?|figures?|actors?|crowds?)\b', re.I)


def validate(value):
    if value is None:
        return {'version': 1, 'generate': dict.fromkeys(CATEGORIES, False), 'assets': [], 'requests': []}
    if not isinstance(value, dict) or value.get('version') != 1:
        raise ValueError('Reference preparation needs version 1.')
    flags = value.get('generate', {})
    if not isinstance(flags, dict) or any(k not in CATEGORIES or type(v) is not bool for k,v in flags.items()):
        raise ValueError('Reference preparation switches must be cast, locations or props booleans.')
    rows = value.get('assets', [])
    if not isinstance(rows, list):
        raise ValueError('Reference preparation assets must be a list.')
    keys = set()
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('key'), str) or not row['key']
                or row['key'] in keys or row.get('category') not in CATEGORIES or row.get('role') not in ROLES):
            raise ValueError('Reference asset needs a unique key, category and role.')
        keys.add(row['key'])
        if 'included' in row and type(row['included']) is not bool:
            raise ValueError('Reference asset inclusion must be a boolean.')
        if 'input_fingerprint' in row and not HASH.fullmatch(str(row['input_fingerprint'])):
            raise ValueError('Reference asset design fingerprint is invalid.')
        if 'seed' in row:
            if type(row['seed']) is not int or not 0 <= row['seed'] <= rules.MAX_SEED:
                raise ValueError('Reference seed must be an unsigned 64-bit integer.')
        if not isinstance(row.get('candidates', []), list):
            raise ValueError('Reference candidates must be a list.')
        ids = set()
        for candidate in row.get('candidates', []):
            if (not isinstance(candidate, dict) or not isinstance(candidate.get('id'), str)
                    or candidate['id'] in ids or not HASH.fullmatch(str(candidate.get('sha256', '')))
                    or not HASH.fullmatch(str(candidate.get('input_fingerprint', '')))):
                raise ValueError('Reference candidate identity or hash is invalid.')
            rules.preview_file(candidate.get('file'))
            ids.add(candidate['id'])
        accepted = row.get('approved')
        if accepted is not None and (not isinstance(accepted, dict) or accepted.get('candidate_id') not in ids
                                    or type(accepted.get('revision')) is not int or accepted['revision'] < 1):
            raise ValueError('Reference approval must name a candidate and positive revision.')
    requests = value.get('requests', [])
    if not isinstance(requests, list) or any(not isinstance(r,dict) for r in requests):
        raise ValueError('Reference image requests must be a list of native receipts.')
    result = copy.deepcopy(value)
    result.update(generate={**dict.fromkeys(CATEGORIES, False), **flags}, assets=copy.deepcopy(rows),
                  requests=copy.deepcopy(requests))
    return result


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def scene_start(document, index):
    boxes = document.get('boxes', [])
    while index > 0 and not boxes[index].get('new_scene'):
        index -= 1
    return boxes[index]['id'] if boxes else ''


def _source_hashes(document, row, slots, body):
    hashes = dict(row.get('input_sources') or {})
    originals = {}
    for slot in slots:
        descriptor = document.get('reference_replacements', {}).get(slot)
        file = descriptor.get('file') if isinstance(descriptor,dict) else None
        file = file or next((p.get('file') for p in document.get('pictures',[]) if p['slot']==slot),None)
        if file:
            try:
                pin = stills.pin_image(file)
                hashes[slot] = pin['sha256']
                originals[slot] = dict(pin, slot=slot)
            except (ValueError,OSError):hashes[slot] = {'unavailable':file}
        elif slot not in hashes:hashes[slot] = None
    if body and body.get('workflow') and slots:
        parsed = rules.parse(body['timeline'])
        index = next((i for i,b in enumerate(parsed.boxes) if b.id in row['clips']),0)
        for slot in slots:
            if slot in document.get('disabled_refs',[]):continue
            try:
                refs = stills._pixel_references(dict(body,prompt='@'+slot),parsed,index,0,body['workflow']['api'])
                match = next((r for r in refs if r.get('slot')==slot),None)
                hashes[slot] = match.get('sha256', match.get('graph_sha256')) if match else None
                if match and 'file' in match:
                    originals[slot] = {k:match[k] for k in ('slot','file','sha256')}
                else:
                    originals.pop(slot, None)
            except (ValueError,OSError,KeyError) as error:
                hashes[slot] = {'unavailable':str(error)}
                originals.pop(slot, None)
    row['existing_images'] = [originals[s] for s in row['pictures']
                              if s in originals and s not in document.get('disabled_refs', [])]
    return {slot:hashes.get(slot) for slot in slots}


def catalog(document, body=None):
    state = validate(document.get('reference_preparation'))
    saved = {row['key']:row for row in state['assets']}
    boxes = document.get('boxes', [])
    ids = [box['id'] for box in boxes]
    entities = story_bible.entities(document['bible']) if document.get('bible') else []
    disabled = set(document.get('disabled_refs', []))
    rows = []
    for entity in entities:
        category = {'character':'cast', 'place':'locations', 'prop':'props'}[entity['kind']]
        visible = []
        for i,box in enumerate(boxes):
            schedule = box.get('schedule') or {}
            used = {*schedule.get('entities', []), schedule.get('place'), *(box.get('cast') or {}).values()}
            if entity['id'] in used:
                visible.append(i)
        versions = [(None, entity), *[(look['from'],look) for look in entity['looks']]]
        for start,version in versions:
            key = 'entity:' + entity['id'] + (':look:' + start if start else '')
            role = ('appearance' if start else 'identity') if category == 'cast' else ('location' if category == 'locations' else 'prop')
            active = [ids[i] for i in visible if (category=='cast' and start is None)
                      or (entity['looks'][story_bible.look_at(entity,ids,i)-1]['from']
                          if story_bible.look_at(entity,ids,i) else None)==start]
            rows.append({'key':key, 'category':category, 'role':role, 'entity':entity['id'], 'from':start,
                         'name':entity['name'] + (' — from ' + start if start else ''),
                         'description':version['description'], 'pictures':list(version.get('pictures', [])),
                         'identity_pictures':list(entity['pictures']) if category=='cast' else [],
                         'clips':active, 'included':True, 'candidates':[]})
    for index,box in enumerate(boxes):
        if index and not box.get('new_scene'):
            continue
        members = [b for i,b in enumerate(boxes) if scene_start(document,i)==box['id']]
        used = set()
        for member in members:
            schedule = member.get('schedule') or {}
            used.update([*schedule.get('entities', []), schedule.get('place'), *(member.get('cast') or {}).values()])
        sources = [row['key'] for row in rows if row.get('entity') in used
                   and row['category']!='cast' and any(b['id'] in row['clips'] for b in members)]
        rows.append({'key':'scene:'+box['id'], 'category':'locations', 'role':'scene_layout', 'scene':box['id'],
                     'name':'Composed scene — '+box['id'], 'description':'An unoccupied scene with the approved location and objects. '
                     'Keep room geometry, materials, lighting and object placement consistent.',
                     'sources':sources, 'pictures':[], 'clips':[b['id'] for b in members], 'included':False, 'candidates':[]})
    for row in rows:
        stored = saved.pop(row['key'], {})
        for key in ('included','prompt','seed','size','candidates','approved','slot','sources','include_character','input_sources'):
            if key in stored:
                row[key] = copy.deepcopy(stored[key])
        row.setdefault('prompt', row['description'])
        source_pictures = [s for s in row['pictures'] if s!=row.get('slot')]
        identity = row.get('identity_pictures', []) if row['role']=='appearance' else []
        requested = re.sub(r'<image([1-9]\d*)>',lambda m:'@image'+m[1],row['prompt'],flags=re.I)
        prompt_slots = [slot for kind,slot in rules.mentions(requested) if kind=='image'] if row['role']!='scene_layout' else []
        descriptors = _source_hashes(document, row, list(dict.fromkeys([*source_pictures,*identity,*prompt_slots])), body)
        row['input_sources'] = descriptors
        row['input_fingerprint'] = fingerprint({k:row.get(k) for k in ('key','role','description','prompt','clips','sources','include_character')}
                                               | {'pictures':source_pictures,'identity':identity,'files':descriptors,
                                                  'style':story_bible.style(document.get('bible'))})
        accepted = row.get('approved') or {}
        candidate = next((c for c in row['candidates'] if c['id']==accepted.get('candidate_id')), None)
        enabled = [s for s in row['pictures'] if s not in disabled]
        if candidate:
            row['status'] = 'approved' if candidate['input_fingerprint']==row['input_fingerprint'] and row.get('slot') not in disabled else 'outdated'
        elif enabled and (not body or not body.get('workflow') or any(isinstance(descriptors.get(s), str) for s in enabled)):
            row['status'] = 'approved'
        else:
            row['status'] = 'candidates' if row['candidates'] else 'missing'
    by_key = {r['key']:r for r in rows}
    for row in rows:
        if row['role']!='scene_layout':
            continue
        dependencies = []
        for key in row.get('sources', []):
            source = by_key.get(key)
            if source is not None:
                dependencies.append({'key':key,'design':source['input_fingerprint'],'approval':source.get('approved'),
                                     'pictures':source.get('pictures')})
        row['input_fingerprint'] = fingerprint({'design':row['input_fingerprint'],'dependencies':dependencies})
        accepted = row.get('approved') or {}
        candidate = next((c for c in row['candidates'] if c['id']==accepted.get('candidate_id')), None)
        if candidate:
            row['status'] = 'approved' if candidate['input_fingerprint']==row['input_fingerprint'] and row.get('slot') not in disabled else 'outdated'
    rows.extend(dict(copy.deepcopy(row), status='orphan', clips=[]) for row in saved.values())
    return rows


def required(document, box_id, body=None):
    flags = validate(document.get('reference_preparation'))['generate']
    return [r['key'] for r in catalog(document,body) if not r.get('from') and r['role'] not in ('appearance','scene_layout')
            and flags[r['category']] and r.get('included', True)
            and box_id in r['clips'] and r['status'] not in ('approved','orphan')]


def _row(document, key, body=None):
    row = next((r for r in catalog(document,body) if r['key']==key), None)
    if not row or row['status']=='orphan':
        raise ValueError('Reference owner was removed; choose a current Story entity or scene.')
    return row


def _approved_pixels(document, row, body):
    if row['status']!='approved':
        raise ValueError('Approve '+row['name']+' before composing the scene.')
    accepted = row.get('approved') or {}
    candidate = next((c for c in row['candidates'] if c['id']==accepted.get('candidate_id')), None)
    if candidate:
        pin = stills.pin_image(candidate['file'])
        if pin['sha256']!=candidate['sha256']:
            raise ValueError('Approved '+row['name']+' image bytes changed.')
        return [dict(pin, roles=[row['role']+': '+row['name']], asset_key=row['key'],
                     approval_revision=accepted['revision'], **({'slot':row['slot']} if row.get('slot') else {}))]
    parsed = rules.parse(body['timeline'])
    selection = dict(body, prompt=' '.join('@'+s for s in row['pictures']))
    index = next((i for i,b in enumerate(parsed.boxes) if b.id in row['clips']), 0)
    return [dict(ref,roles=[row['role']+': '+row['name']],asset_key=row['key'])
            for ref in stills._pixel_references(selection,parsed,index,0,body['workflow']['api'])]


def prepare(body):
    try:
        recipe = body['recipe']
        if recipe.get('version')!=2 or recipe.get('adapter')!='pixels':
            raise ValueError('Reference generation needs a connected version-2 pixel recipe. Import images or connect an image generator.')
        document = json.loads(body['timeline'])
        parsed = rules.parse(body['timeline'])
        row = _row(document, body['asset_key'], body)
        for slot,value in row['input_sources'].items():
            if isinstance(value,dict) and 'unavailable' in value:
                raise ValueError('Reference @'+slot+' is unavailable: '+str(value['unavailable']))
        if row['input_fingerprint']!=body.get('input_fingerprint'):
            raise ValueError('Reference design changed; refresh preparation before generating.')
        if not isinstance(body.get('prompt'),str) or not body['prompt'].strip():
            raise ValueError('Write a still-image reference prompt before generating.')
        refs = []
        prompt = body['prompt']
        if row['role']=='scene_layout':
            for key in row['sources']:
                source = _row(document,key,body)
                if source['category']=='cast' and not row.get('include_character'):
                    continue
                refs.extend(_approved_pixels(document,source,body))
            if not refs:
                raise ValueError('Choose and approve location/object references before composing the scene.')
            if not row.get('include_character'):
                prompt = 'An unoccupied location, with no people. '+prompt
        elif row['category']=='locations':
            prompt = LOCATION_GRID+prompt
        else:
            # Only explicit asset inputs: never shot anchors, prior frames or video memory.
            identity = row['identity_pictures'] if row['role']=='appearance' else []
            requested = re.sub(r'<image([1-9]\d*)>',lambda m:'@image'+m[1],prompt,flags=re.I)
            selection = dict(body,prompt=' '.join('@'+s for s in identity)+' '+requested)
            index = next((i for i,b in enumerate(parsed.boxes) if b.id in row['clips']),0)
            refs = stills._pixel_references(selection,parsed,index,0,body['workflow']['api'])
            for ref in refs:
                ref['roles'] = ['identity' if ref['slot'] in identity else 'reference for '+row['name']]
            if row['role']=='appearance':
                if not identity:
                    base = _row(document,'entity:'+row['entity'],body)
                    refs = _approved_pixels(document,base,body)+refs
                if not refs:
                    raise ValueError('Import or approve the original identity image for '+row['name']+' first.')
                prompt = CHARACTER_SHEET.format(look=' of the same character as the identity reference, wearing the '
                                                'appearance described below')+prompt
            elif row['category']=='cast':
                prompt = CHARACTER_SHEET.format(look='')+prompt
        style = _style(document, row)
        if style:
            prompt += '\nVisual style: '+style
        if row['role']=='location':
            prompt += '\nThe place is empty in every panel.'
        planned = dict(body,prompt=prompt,frame=0)
        return image_recipe.prepare(recipe,body['workflow'],planned,refs)
    except (ValueError,OSError,KeyError,TypeError) as error:
        return {'ok':False,'error':str(error)}


def _style(document, row):
    """The Story style without sentences that would paint another character, or any figure into an empty place."""
    bible = document.get('bible')
    style = story_bible.style(bible)
    if not style or row.get('include_character'):
        return style
    names = [e['name'].strip() for e in story_bible.entities(bible) if e['kind']=='character' and e['id']!=row.get('entity')]
    patterns = [re.compile(r'(?<!\w)'+re.escape(name)+r'(?!\w)', re.I) for name in names if name]
    if row['category']!='cast':
        patterns.append(PEOPLE)
    sentences = re.split(r'(?<=[.!?])\s+', style.strip())
    return ' '.join(s for s in sentences if not any(p.search(s) for p in patterns))


def result(body):
    answer = stills.result(body)
    if answer.get('ok') and answer.get('state')=='complete':
        try:
            answer['images'] = [dict(image, **stills.pin_image(image['file'])) for image in answer['images']]
        except (ValueError,OSError) as error:
            return {'ok':False,'error':str(error)}
    return answer


def require_ready(document, box_id, body=None):
    missing = required(document,box_id,body)
    if missing:
        rows = {r['key']:r for r in catalog(document,body)}
        raise ValueError('Prepare and approve references before generating this still: '+', '.join(rows[k]['name'] for k in missing)+'. Or disable their preparation requirement.')


def _candidate(row):
    accepted = row.get('approved') or {}
    return next((c for c in row.get('candidates',[]) if c['id']==accepted.get('candidate_id')),None)


def references(document, box_id, body=None):
    if not document.get('reference_preparation') and body is None:
        return []
    disabled = document.get('disabled_refs', [])
    refs = []
    rows = catalog(document)
    for row in rows:
        candidate = _candidate(row)
        if not candidate or box_id not in row['clips'] or row.get('slot') in disabled:
            continue
        pin = stills.pin_image(candidate['file'])
        if pin['sha256']!=candidate['sha256']:
            raise ValueError('Approved '+row['name']+' image bytes changed.')
        refs.append(dict(pin,roles=[row['role']+': '+row['name']],slot=row['slot'],asset_key=row['key'],
                         approval_revision=row['approved']['revision']))
    if body is not None:
        owners = [(row, slot) for row in rows if box_id in row['clips'] for slot in row.get('pictures', [])
                  if slot != row.get('slot') and slot not in disabled]
        if owners:
            parsed = rules.parse(body['timeline'])
            index = next(i for i, box in enumerate(parsed.boxes) if box.id == box_id)
            selection = dict(body, prompt=' '.join('@'+slot for _,slot in owners))
            pixels = {r['slot']:r for r in stills._pixel_references(selection, parsed, index, body.get('frame', 0), body['workflow']['api'])}
            for row,slot in owners:
                refs.append(dict(copy.deepcopy(pixels[slot]), roles=[row['role']+': '+row['name']], asset_key=row['key']))
    return refs


def identity_slots(document, box_id):
    if not document.get('reference_preparation'):
        return []
    return list(dict.fromkeys(slot for row in catalog(document) if row['role']=='appearance' and _candidate(row)
                             and box_id in row['clips'] and row.get('slot') not in document.get('disabled_refs',[])
                             for slot in row['identity_pictures']))


def _free_slot(document):
    used = set()
    def visit(value):
        if isinstance(value,dict):
            for key,child in value.items():
                visit(key);visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
        elif isinstance(value,str):
            used.update(int(n) for n in re.findall(r'(?<![\w])@?image([1-9]\d*)(?!\w)',value))
    visit(document)
    number = 17
    while number in used:number+=1
    return 'image'+str(number)


def approve(document, asset_key, candidate_id, expected_revision, body=None):
    row = _row(document,asset_key,body)
    current = (row.get('approved') or {}).get('revision',0)
    if type(expected_revision) is not int or current!=expected_revision:
        raise ValueError('Reference approval changed; review the current candidates again.')
    candidate = next((c for c in row['candidates'] if c['id']==candidate_id),None)
    if not candidate or candidate['input_fingerprint']!=row['input_fingerprint']:
        raise ValueError('Reference design changed; generate or upload a current candidate.')
    pin = stills.pin_image(candidate['file'])
    if pin['sha256']!=candidate['sha256']:
        raise ValueError('Reference candidate image bytes changed.')
    for source in candidate.get('provenance',{}).get('references',[]):
        if source.get('file') and stills.pin_image(source['file'])['sha256']!=source['sha256']:
            raise ValueError('A source reference image changed since this candidate was generated.')
    result = copy.deepcopy(document)
    state = validate(result.get('reference_preparation'))
    result['reference_preparation'] = state
    stored = next(a for a in state['assets'] if a['key']==asset_key)
    slot = stored.get('slot') or _free_slot(result)
    picture = {'slot':slot,'file':copy.deepcopy(candidate['file']),'title':row['name']}
    existing = next((i for i,p in enumerate(result.get('pictures',[])) if p['slot']==slot),None)
    if existing is None:result.setdefault('pictures',[]).append(picture)
    else:result['pictures'][existing]=picture
    if row.get('entity'):
        bible = copy.deepcopy(result['bible'])
        entity = next(e for e in bible['entities'] if e['id']==row['entity'])
        owner = next(look for look in entity['looks'] if look['from']==row['from']) if row.get('from') else entity
        owner['pictures'] = [s for s in owner.get('pictures',[]) if s!=stored.get('slot')]+[slot]
        answer = story_bible.apply(result,bible)
        result['bible'] = answer['bible']
        for box in result.get('boxes',[]):
            for field,mapping in (('prompt','prompts'),('cast','casts'),('source','sources')):
                if box['id'] in answer[mapping]:box[field]=answer[mapping][box['id']]
    stored.update(input_sources=copy.deepcopy(row['input_sources']),slot=slot,approved={'candidate_id':candidate_id,'revision':current+1})
    rules.parse(json.dumps(result))
    return result


def native_prompt(parsed, index):
    """Deliver approved scoped assets through the existing H3 mention/transport path."""
    if not parsed.reference_preparation:return ''
    document = {'bible':parsed.bible,'reference_preparation':parsed.reference_preparation,
                'pictures':parsed.pictures,'reference_replacements':parsed.reference_replacements,
                'disabled_refs':parsed.disabled_refs,'boxes':[
                    {'id':box.id,'new_scene':box.new_scene,**parsed.story[i]} for i,box in enumerate(parsed.boxes)]}
    labels=[]
    for row in catalog(document):
        if _candidate(row) and parsed.boxes[index].id in row['clips'] and row.get('slot') not in parsed.disabled_refs:
            role='scene layout' if row['role']=='scene_layout' else row['role']
            labels.append('@'+row['slot']+' is the approved '+role+' reference for '+row['name']+'.')
    return '\n'.join(labels)
