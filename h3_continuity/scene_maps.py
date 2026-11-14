"""Scene maps on Studio clips: a top-down plan per clip with an opening and an end layout.

A clip that continues an adjacent clip whose map is on borrows that clip's picture, camera look, markers and end
positions as its opening; web/h3c_scene_maps.mjs makes the same decisions and keeps a copy in the borrowing clip for
when the link breaks. Pure Python: scene_map.py (wording, drawing) is loaded only where it is needed.
"""

import copy
import math
import re

FEATURE = 'scene-map-1'
HEADER = re.compile(r'^(\w+):[ \t]*$', re.M)
SHOT_ONE = re.compile(r'^\[Shot 1\][^\n]*', re.M)
DESCRIPTIONS = ('detailed_description', 'integrated_multimodal_description')
LEGEND_POSITIONS = ('bottom-left', 'bottom-right', 'top-left', 'top-right')
CAMERA_LOOK = {'fov': 55, 'height': 1.5, 'label': 'CAMERA', 'color': '#ffffff'}


def _error(message):
    from . import timeline as rules
    return rules._error(message)


def _number(value, default, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return default
    return min(high, max(low, value))


def _text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) else ''


def _color(value, default):
    if isinstance(value, str) and len(value) == 7 and value[0] == '#':
        try:
            int(value[1:], 16)
            return value.lower()
        except ValueError:
            pass
    return default


def _point(value):
    if (isinstance(value, list) and len(value) == 2
            and all(not isinstance(item, bool) and isinstance(item, (int, float)) and math.isfinite(item) for item in value)):
        return [min(1, max(0, value[0])), min(1, max(0, value[1]))]
    return None


def _place(value):
    if not isinstance(value, dict):
        return None
    keys = ('x', 'y', 'tx', 'ty')
    if any(isinstance(value.get(key), bool) or not isinstance(value.get(key), (int, float)) for key in keys):
        return None
    return {key: min(1, max(0, value[key])) for key in keys}


def _phase(value):
    value = value if isinstance(value, dict) else {}
    markers = value.get('markers') if isinstance(value.get('markers'), dict) else {}
    return {'camera': _place(value.get('camera')),
            'markers': {key: point for key, point in ((str(key), _point(item)) for key, item in markers.items()) if point}}


def validate(raw, n):
    """The box's scene map with every field present, or None when the box has none; raises on what can't be kept."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _error(f'box {n} scene map must be an object')
    from . import timeline as rules
    picture = raw.get('picture')
    if picture is not None and not rules._local_file(picture):
        raise _error(f"box {n} scene map picture must be a file in ComfyUI's input, output or temp folder")
    markers, ids = [], set()
    for item in raw.get('markers') or []:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'].strip():
            raise _error(f'box {n} scene map markers need an id')
        marker_id = item['id'].strip()[:40]
        if marker_id in ids:
            raise _error(f'box {n} scene map markers need unique ids')
        ids.add(marker_id)
        marker = {'id': marker_id, 'label': _text(item.get('label'), 60), 'text': _text(item.get('text'), 3),
                  'icon': item.get('icon') if isinstance(item.get('icon'), str) else 'dot',
                  'color': _color(item.get('color'), '#e0352b'), 'size': _number(item.get('size'), 1, 0.3, 4),
                  'legend': item.get('legend', True) is not False}
        if isinstance(item.get('entity'), str) and item['entity']:
            marker['entity'] = item['entity']
        if item.get('borrowed') is True:
            marker['borrowed'] = True
        markers.append(marker)
    camera = raw.get('camera') if isinstance(raw.get('camera'), dict) else {}
    legend = raw.get('legend') if isinstance(raw.get('legend'), dict) else {}
    size = [raw[key] if type(raw.get(key)) is int and raw[key] > 0 else None for key in ('width', 'height')]
    absent = raw.get('absent') or []
    if not isinstance(absent, list) or any(not isinstance(item, str) for item in absent):
        raise _error(f'box {n} scene map absent must list marker ids')
    return {'on': raw.get('on') is True, 'picture': dict(picture) if picture else None, 'width': size[0], 'height': size[1],
            'markers': markers,
            'camera': {'fov': _number(camera.get('fov'), CAMERA_LOOK['fov'], 5, 170),
                       'height': _number(camera.get('height'), CAMERA_LOOK['height'], 0, 10000),
                       'label': _text(camera.get('label'), 40) or CAMERA_LOOK['label'],
                       'color': _color(camera.get('color'), CAMERA_LOOK['color'])},
            'opening': _phase(raw.get('opening')), 'end': _phase(raw.get('end')), 'absent': list(dict.fromkeys(absent)),
            'legend': {'show': legend.get('show', True) is not False,
                       'position': legend.get('position') if legend.get('position') in LEGEND_POSITIONS else 'bottom-left'},
            'scale': _number(raw.get('scale'), 1, 0.25, 4), 'video_picture': raw.get('video_picture') is True}


def check(timeline, requires):
    """Raises when a box's map is on but the Timeline does not name the feature."""
    for n, scene in enumerate(timeline.scene_maps, 1):
        if scene and scene['on'] and FEATURE not in requires:
            raise _error(f'box {n} has a scene map, which requires {FEATURE}')


def _map(timeline, index):
    maps = getattr(timeline, 'scene_maps', None) or []
    scene = maps[index] if index < len(maps) else None
    return scene if scene and scene['on'] else None


def source(timeline, index):
    """The clip box `index` borrows its opening from: the adjacent clip it continues, when that clip's map is on."""
    from . import timeline as rules
    if _map(timeline, index) is None or rules.is_fresh(timeline, index):
        return None
    before = rules.previous_index(timeline, index)
    return before if before is not None and _map(timeline, before) is not None else None


def _layout(resolved, camera, look, positions):
    return {'version': 1, 'width': resolved['width'], 'height': resolved['height'], 'scale': resolved['scale'],
            'legend': dict(resolved['legend']),
            'camera': dict(camera, **look) if camera else None,
            'markers': [dict(marker, x=positions[marker['id']][0], y=positions[marker['id']][1])
                        for marker in resolved['markers']]}


def resolve(timeline, index, _memo=None):
    """{"picture", "width", "height", "opening", "end", "source", "owners"} for box `index`, or None when its map is
    off. "opening" and "end" are layouts scene_map.normalize reads; "owners" maps each marker id to the box index whose
    marker list defines it."""
    memo = {} if _memo is None else _memo
    if index in memo:
        return memo[index]
    scene = _map(timeline, index)
    if scene is None:
        return None
    before = source(timeline, index)
    if before is None:
        base = {'picture': scene['picture'], 'width': scene['width'], 'height': scene['height'], 'scale': scene['scale'],
                'legend': scene['legend'], 'look': scene['camera'], 'camera': scene['opening']['camera'],
                'markers': [], 'positions': {}, 'owners': {}}
    else:
        previous = resolve(timeline, before, memo)
        end = previous['end']
        base = {key: previous[key] for key in ('picture', 'width', 'height')}
        base.update(scale=end['scale'], legend=end['legend'], look=previous['look'],
                    camera={key: end['camera'][key] for key in ('x', 'y', 'tx', 'ty')} if end['camera'] else None,
                    markers=[{key: value for key, value in marker.items() if key not in ('x', 'y')}
                             for marker in end['markers'] if marker['id'] not in scene['absent']],
                    owners={key: value for key, value in previous['owners'].items() if key not in scene['absent']})
        base['positions'] = {marker['id']: [marker['x'], marker['y']] for marker in end['markers']}
    inherited = {marker['id'] for marker in base['markers']}
    for marker in scene['markers']:
        # A borrowed marker is the copy kept for when the link breaks; while linked the source decides.
        if marker['id'] not in inherited and not (before is not None and marker.get('borrowed')):
            base['markers'].append({key: value for key, value in marker.items() if key != 'borrowed'})
            base['owners'][marker['id']] = index
            base['positions'][marker['id']] = scene['opening']['markers'].get(marker['id'], [0.5, 0.5])
    opening = base['positions']
    closing = {key: scene['end']['markers'].get(key, point) for key, point in opening.items()}
    resolved = {'picture': base['picture'], 'width': base['width'], 'height': base['height'], 'scale': base['scale'],
                'legend': base['legend'], 'markers': base['markers']}
    end_camera = scene['end']['camera'] or base['camera']
    result = {'picture': base['picture'], 'width': base['width'], 'height': base['height'], 'source': before,
              'owners': base['owners'], 'look': base['look'],
              'opening': _layout(resolved, base['camera'], base['look'], opening),
              'end': _layout(resolved, end_camera if base['camera'] else None, base['look'], closing)}
    memo[index] = result
    return result


# --- video prompt ------------------------------------------------------------------------------------------------------

def names(timeline, index, resolved, prompt):
    """{marker id: name} for markers linked to a Cast entity: the clip's <Subject N> label when the prompt uses it,
    else the entity's name. Other markers keep their own label."""
    cast = timeline.story[index].get('cast', {}) if index < len(timeline.story) else {}
    known = {item.get('id'): item for item in (timeline.bible or {}).get('entities', []) if isinstance(item, dict)}
    found = {}
    for marker in resolved['opening']['markers']:
        entity = marker.get('entity')
        if not entity:
            continue
        label = next((label for label, target in cast.items() if target == entity and label in prompt), None)
        name = label or (known.get(entity) or {}).get('name')
        if name:
            found[marker['id']] = name
    return found


def _without(timeline, index):
    """A shallow copy of the Timeline in which box `index` has no map."""
    probe = copy.copy(timeline)
    probe.scene_maps = list(timeline.scene_maps)
    probe.scene_maps[index] = None
    return probe


def base_slots(timeline, index, context=39):
    """box_slots for box `index` as if its map were off."""
    from . import timeline as rules
    return rules.box_slots(_without(timeline, index), index, context)


def _quiet(reason, slot=''):
    return {'blocking': '', 'definition': '', 'retention': '', 'slot': slot, 'reason': reason}


def _gate(timeline, index, resolved):
    """(reason box `index` gets no map text or '', its slots without the map or None)."""
    from . import timeline as rules
    if not rules.is_fresh(timeline, index):
        return 'This clip continues the previous one.', None
    try:
        slots = base_slots(timeline, index)
    except ValueError as error:
        return f'This clip cannot be checked yet: {error}', None
    if slots.first:
        return 'This clip has a start frame, which already shows the opening.', slots
    if slots.mode not in ('t2va', 'ref2va'):
        return 'This clip renders as FLF2VA.', slots
    if not resolved['picture'] or not resolved['width'] or not resolved['height']:
        return 'The map has no picture.', slots
    if not resolved['opening']['camera']:
        return 'The map has no camera, so the video gets no map text.', slots
    return '', slots


def _full(timeline, index, slots):
    """Whether box `index` wants its map picture but already sends as many pictures as H3 takes."""
    from . import timeline as rules
    return (timeline.scene_maps[index]['video_picture'] and slots.mode == 'ref2va'
            and len(slots.image_inputs) >= rules.MAX_REF_IMAGES)


def video_parts(timeline, index):
    """What box `index`'s map adds to its video prompt: {"blocking", "definition", "retention", "slot", "reason"}, or
    None when its map is off. "reason" says why a box with a map gets no text or no picture."""
    from . import timeline as rules
    resolved = resolve(timeline, index)
    if resolved is None:
        return None
    reason, slots = _gate(timeline, index, resolved)
    if reason:
        return _quiet(reason)
    from . import scene_map
    labels = names(timeline, index, resolved, rules.assemble_prompt(_without(timeline, index), index))
    width, height = resolved['width'], resolved['height']
    blocking = ' '.join(part for part in (scene_map.frame_text(resolved['opening'], width, height, labels),
                                          scene_map.motion_text(resolved['opening'], resolved['end'], width, height,
                                                                labels)) if part)
    slot = timeline.scene_map_slots.get(index, '')
    if not slot:
        return {'blocking': blocking, 'definition': '', 'retention': '', 'slot': '',
                'reason': 'This clip already sends 9 pictures, so the map goes in as text only.'
                if _full(timeline, index, slots) else ''}
    return {'blocking': blocking, 'slot': slot, 'reason': '',
            'definition': f'@{slot} is a storyboard reference for [Shot 1]: a top-down plan of this place defining the '
                          'camera viewpoint and where each subject starts.',
            'retention': f'@{slot} ([Shot 1] storyboard): weak_reference - only the camera viewpoint and where each '
                         "subject starts are followed; the plan's view, symbols, arrow, labels and legend are not "
                         'reproduced.'}


# --- map picture -------------------------------------------------------------------------------------------------------

def _taken(timeline):
    """Every image slot number the Timeline names anywhere, so a map picture never reuses one."""
    from . import timeline as rules
    named = [picture['slot'] for picture in timeline.pictures] + [ref['slot'] for ref in timeline.refmods]
    named += list(timeline.reference_replacements) + list(timeline.disabled_refs)
    for text in [timeline.prompt] + [box.prompt for box in timeline.boxes]:
        named += [name for kind, name in rules.mentions(text) if kind == 'image']
    return {len(rules.IMAGE_SLOTS)} | {rules.slot_number(name) for name in named if rules.is_picture_slot(name)}


def attach(timeline):
    """Adds a Studio picture for each box that sends its map picture to H3, numbered after every slot in use."""
    import hashlib
    import json
    timeline.scene_map_slots = {}
    taken = None
    for index, scene in enumerate(timeline.scene_maps):
        if not scene or not scene['on'] or not scene['video_picture']:
            continue
        resolved = resolve(timeline, index)
        reason, slots = _gate(timeline, index, resolved)
        if reason or slots.mode != 'ref2va' or _full(timeline, index, slots):
            continue
        taken = _taken(timeline) if taken is None else taken
        number = max(taken) + 1
        taken.add(number)
        slot = f'image{number}'
        digest = hashlib.sha1(json.dumps([resolved['opening'], resolved['picture']], sort_keys=True)
                              .encode('utf-8')).hexdigest()[:20]
        timeline.pictures.append({'slot': slot, 'title': 'Scene map',
                                  'file': {'type': 'input', 'subfolder': 'h3c_scene_maps', 'filename': digest + '.png'},
                                  'scene_map': {'box': timeline.boxes[index].id, 'number': index + 1,
                                                'layout': resolved['opening'], 'picture': resolved['picture']}})
        timeline.scene_map_slots[index] = slot


def digest(timeline, index):
    """The content name of the map picture box `index` sends, or None."""
    slot = timeline.scene_map_slots.get(index)
    picture = next((picture for picture in timeline.pictures if picture['slot'] == slot), None) if slot else None
    return picture['file']['filename'].rsplit('.', 1)[0] if picture else None


def ensure(picture):
    """The path of a map picture's file, drawn from its base picture at 1 MP when missing or older than the base."""
    import os
    import folder_paths
    from PIL import Image, ImageOps
    from . import scene_map, studio_pictures
    info, file = picture['scene_map'], picture['file']
    base = studio_pictures.path(info['picture'])
    if base is None:
        raise _error(f"box {info['number']} uses a scene map picture ({info['picture']['filename']}), but the file is "
                     f"missing from ComfyUI's {info['picture']['type']} folder")
    folder = os.path.join(folder_paths.get_directory_by_type(file['type']), file['subfolder'])
    found = os.path.join(folder, file['filename'])
    if not os.path.isfile(found) or os.path.getmtime(found) < os.path.getmtime(base):
        with Image.open(base) as opened:
            made = scene_map.render(scene_map.resize(ImageOps.exif_transpose(opened).convert('RGB'), 1.0), info['layout'])
        os.makedirs(folder, exist_ok=True)
        partial = found + '.partial.png'
        made.save(partial)
        os.replace(partial, found)
    return found


def preview(text, box_id):
    """What the Studio panel shows for a clip's map: {"video": {"mode", "parts", "reason"}, "stills": {...}}."""
    from . import timeline as rules
    parsed = rules.parse(text)
    index = next((number for number, box in enumerate(parsed.boxes) if box.id == box_id), None)
    if index is None:
        raise _error(f'there is no clip {box_id!r}')
    parts = video_parts(parsed, index)
    try:
        mode = rules.box_slots(parsed, index).mode
    except ValueError:
        mode = ''
    return {'video': {'mode': mode, 'parts': parts, 'reason': parts['reason'] if parts else ''}, 'stills': {}}


def _sections(prompt):
    """{name: (body start, body end)} of each `name:` section, the end before trailing blank lines."""
    headers = list(HEADER.finditer(prompt))
    found = {}
    for number, header in enumerate(headers):
        start = header.end()
        end = headers[number + 1].start() if number + 1 < len(headers) else len(prompt)
        while end > start and prompt[end - 1] in ' \t\r\n':
            end -= 1
        found.setdefault(header.group(1), (start, end))
    return found


def _close(prompt, section, text):
    """`text` as a new last line of the section, or as a final paragraph without it."""
    span = _sections(prompt).get(section)
    if span is None:
        return prompt.rstrip() + '\n\n' + text if prompt.strip() else text
    return prompt[:span[1]] + '\n' + text + prompt[span[1]:]


def insert(prompt, parts):
    """The prompt with the map's lines in place: the definition closes subject_definitions, the retention line closes
    retention_analysis, and the blocking text ends the description's [Shot 1] line."""
    if not parts:
        return prompt
    if parts.get('definition'):
        prompt = _close(prompt, 'subject_definitions', parts['definition'])
    if parts.get('retention'):
        prompt = _close(prompt, 'retention_analysis', parts['retention'])
    if parts.get('blocking'):
        sections = _sections(prompt)
        name = next((name for name in DESCRIPTIONS if name in sections), None)
        shot = SHOT_ONE.search(prompt, *sections[name]) if name else None
        if shot:
            prompt = prompt[:shot.end()] + ' ' + parts['blocking'] + prompt[shot.end():]
        else:
            prompt = _close(prompt, name or '', parts['blocking'])
    return prompt
