"""Scene maps on Studio clips: a top-down plan per clip with an opening and an end layout.

A clip that continues an adjacent clip whose map is on borrows that clip's picture, camera look, markers and end
positions as its opening; web/h3c_scene_maps.mjs makes the same decisions and keeps a copy in the borrowing clip for
when the link breaks. Pure Python: scene_map.py (wording, drawing) is loaded only where it is needed.
"""

import math

FEATURE = 'scene-map-1'
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
        if marker['id'] not in inherited:
            base['markers'].append(marker)
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
