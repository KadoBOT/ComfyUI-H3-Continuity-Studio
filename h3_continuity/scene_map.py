"""H3 Scene Map: a top-down map with markers, a legend and a camera arrow baked in, used as one more still reference.

The camera is drawn only as an arrow whose tip is the lens. MiniMax H3 Image redrew a drawn camera body and a
field-of-view cone as objects in the picture, while markers, labels, the legend and the arrow stayed on the plan, so
the field of view is given only in text. web/h3c_scene_map_draw.mjs draws the same picture in the editor; keep the
two in step.
"""

import hashlib
import json
import math
import os
from functools import cache
from pathlib import Path

import folder_paths
from comfy_api.latest import io

CATEGORY = 'H3 Continuity'
NODE_CLASS = 'H3C_SceneMap'
ICON_FILE = Path(__file__).resolve().parent.parent / 'web' / 'h3c_scene_map_icons.mjs'
# MiniMax H3 Image Still resizes a reference to this many megapixels instead of its usual 4 when the IMAGE carries it.
REFERENCE_ATTRIBUTE = 'h3c_reference_megapixels'
LEGEND_POSITIONS = ('bottom-left', 'bottom-right', 'top-left', 'top-right')
MARKER_RADIUS = 0.017
DEFAULT_LAYOUT = '{"version":1,"markers":[],"camera":null,"legend":{"show":true,"position":"bottom-left"},"scale":1}'
FONTS = ('segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf', 'LiberationSans-Bold.ttf')
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')


@cache
def icons():
    text = ICON_FILE.read_text(encoding='utf-8')
    return json.loads(text.split('export const ICONS =', 1)[1].strip().rstrip(';'))


# --- layout ----------------------------------------------------------------------------------------------------------

def _number(value, default, low, high):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(value) else min(high, max(low, value))


def _color(value, default):
    if isinstance(value, str) and len(value) == 7 and value[0] == '#':
        try:
            int(value[1:], 16)
            return value.lower()
        except ValueError:
            pass
    return default


def _text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) else ''


def normalize(value):
    """The layout as saved by the editor, with every field present and in range."""
    try:
        data = json.loads(value) if isinstance(value, str) else value
    except ValueError as error:
        raise ValueError(f'H3 Scene Map layout is not valid JSON: {error}') from None
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError('H3 Scene Map layout must be a JSON object')
    markers = []
    for item in data.get('markers') or []:
        if not isinstance(item, dict):
            continue
        markers.append({'id': _text(item.get('id'), 40) or f'm{len(markers) + 1}',
                        'x': _number(item.get('x'), 0.5, 0, 1), 'y': _number(item.get('y'), 0.5, 0, 1),
                        'icon': item.get('icon') if item.get('icon') in icons() else 'dot',
                        'color': _color(item.get('color'), '#e0352b'), 'size': _number(item.get('size'), 1, 0.3, 4),
                        'label': _text(item.get('label'), 60), 'text': _text(item.get('text'), 3),
                        'legend': item.get('legend', True) is not False})
    camera = data.get('camera')
    if isinstance(camera, dict):
        camera = {'x': _number(camera.get('x'), 0.5, 0, 1), 'y': _number(camera.get('y'), 0.8, 0, 1),
                  'tx': _number(camera.get('tx'), 0.5, 0, 1), 'ty': _number(camera.get('ty'), 0.4, 0, 1),
                  'fov': _number(camera.get('fov'), 55, 5, 170), 'height': _number(camera.get('height'), 1.5, 0, 10000),
                  'label': _text(camera.get('label'), 40) or 'CAMERA', 'color': _color(camera.get('color'), '#ffffff')}
        if camera['x'] == camera['tx'] and camera['y'] == camera['ty']:
            camera['ty'] = max(0.0, camera['y'] - 0.1) if camera['y'] > 0 else 0.1
    else:
        camera = None
    legend = data.get('legend') if isinstance(data.get('legend'), dict) else {}
    size = [int(data[key]) if isinstance(data.get(key), (int, float)) and data[key] > 0 else None
            for key in ('width', 'height')]
    return {'version': 1, 'width': size[0], 'height': size[1], 'scale': _number(data.get('scale'), 1, 0.25, 4),
            'legend': {'show': legend.get('show', True) is not False,
                       'position': legend.get('position') if legend.get('position') in LEGEND_POSITIONS else 'bottom-left'},
            'camera': camera, 'markers': markers}


def legend_rows(layout):
    """(kind, icon, color, text, label) for each legend row: one per distinct labelled marker, then the camera."""
    rows, seen = [], set()
    for marker in layout['markers']:
        key = (marker['icon'], marker['color'], marker['label'], marker['text'])
        if marker['legend'] and marker['label'] and key not in seen:
            seen.add(key)
            rows.append(('marker', marker['icon'], marker['color'], marker['label'], marker['text']))
    camera = layout['camera']
    if camera:
        rows.append(('camera', None, camera['color'], f"{camera['label']} · tip = lens, {_metres(camera['height'])} above "
                     f"ground, {_degrees(camera['fov'])} view", ''))
    return rows


def _metres(value):
    return f'{value:g} m'


def _degrees(value):
    return f'{round(value):d}°'


# --- what the camera sees ----------------------------------------------------------------------------------------------

def _place(x, y):
    rows, cols = ('top', 'middle', 'bottom'), ('left', 'centre', 'right')
    row, col = rows[min(2, int(y * 3))], cols[min(2, int(x * 3))]
    return {('middle', 'centre'): 'in the centre', ('middle', 'left'): 'on the left side',
            ('middle', 'right'): 'on the right side'}.get((row, col), f'at the {row} {col}')


def _direction(heading):
    names = ('right', 'bottom right', 'bottom', 'bottom left', 'left', 'top left', 'top', 'top right')
    return names[round(math.degrees(heading) / 45) % 8]


def _name(marker):
    return marker['label'] or (f"the marker {marker['text']}" if marker['text'] else
                               f"a {icons()[marker['icon']]['name'].lower()} marker")


def view(layout, width, height):
    """The markers inside the camera's field of view, left to right in the frame, as (marker, offset, distance):
    offset from -1 (left edge) to 1 (right edge), distance in pixels. None without a camera."""
    camera = layout['camera']
    if not camera:
        return None
    px, py = camera['x'] * width, camera['y'] * height
    heading = math.atan2(camera['ty'] * height - py, camera['tx'] * width - px)
    half = math.radians(camera['fov']) / 2
    seen = []
    for marker in layout['markers']:
        dx, dy = marker['x'] * width - px, marker['y'] * height - py
        distance = math.hypot(dx, dy)
        if distance == 0:
            continue
        # Screen y points down, so a positive angle is clockwise: to the camera's right.
        angle = math.atan2(math.sin(math.atan2(dy, dx) - heading), math.cos(math.atan2(dy, dx) - heading))
        if abs(angle) <= half:
            seen.append((marker, angle / half, distance))
    return sorted(seen, key=lambda item: item[1])


def describe(layout, width, height):
    """Where the camera stands and what it sees, in words, or '' without a camera."""
    camera = layout['camera']
    if not camera:
        return ''
    heading = math.atan2((camera['ty'] - camera['y']) * height, (camera['tx'] - camera['x']) * width)
    text = (f"The camera stands {_place(camera['x'], camera['y'])} of the map, about {_metres(camera['height'])} above "
            f"the ground, and looks towards the {_direction(heading)} of the map with a {round(camera['fov'])} degree "
            "horizontal field of view.")
    seen = view(layout, width, height)
    if seen:
        far = max(distance for _, _, distance in seen)
        near = min(distance for _, _, distance in seen)
        parts = []
        for marker, offset, distance in seen:
            side = ('in the centre' if abs(offset) < 0.2 else
                    ('just left of centre' if offset < 0 else 'just right of centre') if abs(offset) < 0.55 else
                    'on the far left' if offset < 0 else 'on the far right')
            depth = ('close to the camera' if distance < far * 0.45 else
                     'in the middle distance' if distance < far * 0.8 else 'in the distance')
            extra = ''
            if len(seen) > 1 and distance == near:
                extra = ', nearest to the camera'
            elif len(seen) > 1 and distance == far:
                extra = ', farthest from the camera'
            parts.append(f'{_name(marker)} {side}, {depth}{extra}')
        text += ' In frame, from left to right: ' + '; '.join(parts) + '.'
    hidden = [_name(marker) for marker in layout['markers'] if marker not in [item[0] for item in seen or []]]
    if hidden:
        text += ' Out of frame: ' + ', '.join(hidden) + '.'
    return text


def reference_text(name, layout, width, height):
    """What the model is told about the map when it is the reference called `name`."""
    text = f'{name} is a top-down blocking map of this place, a plan for the shot and not part of the picture.'
    if layout['camera']:
        text += (' The arrow on it marks the camera: the tip of the arrow is where the lens stands, and the arrow '
                 'points the way the camera looks.')
    if layout['markers']:
        text += ' The round markers show where each character or object stands.'
    description = describe(layout, width, height)
    if description:
        text += ' ' + description
    marks = ['arrow', 'camera'] if layout['camera'] else []
    marks += ['marker', 'label', 'legend'] if layout['markers'] else ['label', 'legend']
    return (text + ' Everything drawn on the map is a mark on the plan only: no ' + ', '.join(marks[:-1]) +
            f' or {marks[-1]} appears in the picture.')


# --- drawing ---------------------------------------------------------------------------------------------------------

def _rgb(value, alpha=255):
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16), alpha


def _light(value):
    r, g, b, _ = _rgb(value)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.62


@cache
def _font_file():
    roots = [os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'), '/usr/share/fonts/truetype/dejavu',
             '/usr/share/fonts/truetype/liberation', '/Library/Fonts', '/System/Library/Fonts/Supplemental']
    try:
        import matplotlib
        roots.append(os.path.join(os.path.dirname(matplotlib.__file__), 'mpl-data', 'fonts', 'ttf'))
    except ImportError:
        pass
    for name in FONTS:
        for root in roots:
            if os.path.isfile(os.path.join(root, name)):
                return os.path.join(root, name)
    return None


@cache
def font(size):
    from PIL import ImageFont
    path = _font_file()
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)


def _tile(overlay, box, paint, budget=40e6):
    """Draws `paint` supersampled over `box` (x0, y0, x1, y1) and composites it onto `overlay`."""
    from PIL import Image, ImageDraw
    x0, y0 = max(0, math.floor(box[0])), max(0, math.floor(box[1]))
    x1, y1 = min(overlay.width, math.ceil(box[2])), min(overlay.height, math.ceil(box[3]))
    if x1 <= x0 or y1 <= y0:
        return
    w, h = x1 - x0, y1 - y0
    ss = max(1, min(4, int(math.sqrt(budget / (w * h)))))
    layer = Image.new('RGBA', (w * ss, h * ss), (0, 0, 0, 0))
    paint(ImageDraw.Draw(layer), lambda x, y: ((x - x0) * ss, (y - y0) * ss), ss)
    overlay.alpha_composite(layer.resize((w, h), Image.LANCZOS), (x0, y0))


def _glyph(d, at, ss, cx, cy, k, icon, fg, cut):
    def point(x, y):
        return at(cx + (x - 12) * k, cy + (y - 12) * k)
    for shape in icons()[icon]['shapes']:
        fill = cut if shape.get('cut') else fg
        if 'circle' in shape or 'ring' in shape:
            x, y, r = shape.get('circle') or shape.get('ring')
            (px, py), pr = point(x, y), r * k * ss
            if 'circle' in shape:
                d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=fill)
            else:
                d.ellipse([px - pr, py - pr, px + pr, py + pr], outline=fill, width=max(1, round(shape['w'] * k * ss)))
        elif 'poly' in shape:
            p = shape['poly']
            d.polygon([point(p[i], p[i + 1]) for i in range(0, len(p), 2)], fill=fill)
        elif 'line' in shape:
            p = shape['line']
            points = [point(p[i], p[i + 1]) for i in range(0, len(p), 2)]
            width = max(1, round(shape['w'] * k * ss))
            d.line(points, fill=fill, width=width, joint='curve')
            for px, py in (points[0], points[-1]):
                d.ellipse([px - width / 2, py - width / 2, px + width / 2, py + width / 2], fill=fill)


def badge(overlay, cx, cy, r, icon, color, text=''):
    """A round marker: dark rim, white ring, colored disc and a white (or black on light colors) glyph."""
    fg = (20, 20, 22, 255) if _light(color) else (255, 255, 255, 255)

    def paint(d, at, ss):
        def disc(x, y, radius, fill):
            (px, py), pr = at(x, y), radius * ss
            d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=fill)
        disc(cx + r * 0.06, cy + r * 0.1, r * 1.12, (0, 0, 0, 110))
        disc(cx, cy, r * 1.08, (20, 20, 22, 235))
        disc(cx, cy, r, (255, 255, 255, 255))
        disc(cx, cy, r * 0.86, _rgb(color))
        if icon == 'text':
            if text:
                size = r * (1.0 if len(text) == 1 else 0.82 if len(text) == 2 else 0.62)
                d.text(at(cx, cy), text, font=font(max(1, round(size * ss))), fill=fg, anchor='mm')
        else:
            _glyph(d, at, ss, cx, cy, r * 0.86 * 0.82 / 12, icon, fg, _rgb(color))

    pad = r * 1.3
    _tile(overlay, (cx - pad, cy - pad, cx + pad, cy + pad), paint)


def arrow(overlay, tip, heading, length, width, color):
    """A flat arrow along `heading` whose point is at `tip`."""
    c, s = math.cos(heading), math.sin(heading)
    head_length, shaft = width * 1.5, width * 0.42
    local = [(0, 0), (-head_length, -width / 2), (-head_length, -shaft / 2), (-length, -shaft / 2),
             (-length, shaft / 2), (-head_length, shaft / 2), (-head_length, width / 2)]
    shape = [(tip[0] + x * c - y * s, tip[1] + x * s + y * c) for x, y in local]

    def paint(d, at, ss):
        points = [at(*p) for p in shape]
        d.line(points + points[:1], fill=(18, 18, 20, 235), width=max(1, round(width * 0.16 * ss)), joint='curve')
        d.polygon(points, fill=_rgb(color))

    pad = width * 0.4
    xs, ys = [p[0] for p in shape], [p[1] for p in shape]
    _tile(overlay, (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad), paint)


def _label(draw, x, y, text, size, anchor='lm'):
    draw.text((x, y), text, font=font(max(1, round(size))), fill=(255, 255, 255, 255), anchor=anchor,
              stroke_width=max(2, round(size * 0.16)), stroke_fill=(18, 18, 20, 255))


def _legend(overlay, draw, layout, unit):
    rows = legend_rows(layout)
    if not rows or not layout['legend']['show']:
        return
    big, small = font(max(1, round(unit * 0.72))), font(max(1, round(unit * 0.56)))
    rl, row_h, gap = unit * 0.62, unit * 1.7, unit * 0.5
    swatch = rl * 2.6
    width = gap + swatch + gap * 0.8 + max(draw.textlength(row[3], font=big) for row in rows) + gap * 1.2
    height = gap * 0.9 + unit * 0.9 + len(rows) * row_h + gap * 0.4
    margin = unit * 0.8
    position = layout['legend']['position']
    x = margin if position.endswith('left') else overlay.width - width - margin
    y = margin if position.startswith('top') else overlay.height - height - margin
    draw.rounded_rectangle([x, y, x + width, y + height], radius=unit * 0.4, fill=(16, 16, 18, 205),
                           outline=(255, 255, 255, 60), width=max(1, round(unit * 0.06)))
    draw.text((x + gap, y + gap * 0.9), 'LEGEND', font=small, fill=(255, 255, 255, 170), anchor='lt')
    for index, (kind, icon, color, text, mark) in enumerate(rows):
        cy = y + gap * 0.9 + unit * 0.9 + row_h * (index + 0.5)
        if kind == 'marker':
            badge(overlay, x + gap + swatch / 2, cy, rl, icon, color, mark)
        else:
            arrow(overlay, (x + gap + swatch, cy), 0.0, swatch, unit * 0.75, color)
        draw.text((x + gap + swatch + gap * 0.8, cy), text, font=big, fill=(255, 255, 255, 255), anchor='lm')


def render(picture, layout):
    """`picture` (PIL) with the layout's markers, labels, camera arrow and legend drawn on it, as RGB."""
    from PIL import Image, ImageDraw
    base = picture.convert('RGBA')
    width, height = base.size
    unit = MARKER_RADIUS * max(width, height) * layout['scale']
    overlay = Image.new('RGBA', base.size, (0, 0, 0, 0))
    camera = layout['camera']
    if camera:
        px, py = camera['x'] * width, camera['y'] * height
        heading = math.atan2(camera['ty'] * height - py, camera['tx'] * width - px)
        arrow(overlay, (px, py), heading, unit * 4.2, unit * 1.5, camera['color'])
    for marker in layout['markers']:
        badge(overlay, marker['x'] * width, marker['y'] * height, unit * marker['size'], marker['icon'], marker['color'],
              marker['text'])
    draw = ImageDraw.Draw(overlay)
    for marker in layout['markers']:
        if marker['label']:
            r = unit * marker['size']
            _label(draw, marker['x'] * width + r * 1.35, marker['y'] * height, marker['label'], unit * 0.82)
    if camera:
        _label(draw, px - math.cos(heading) * unit * 4.6, py - math.sin(heading) * unit * 4.6 + unit * 0.2,
               camera['label'], unit * 0.82, anchor='mt')
    _legend(overlay, draw, layout, unit)
    return Image.alpha_composite(base, overlay).convert('RGB')


def resize(picture, megapixels):
    from PIL import Image
    if not megapixels:
        return picture
    scale = math.sqrt(megapixels * 1e6 / (picture.width * picture.height))
    size = (max(1, round(picture.width * scale)), max(1, round(picture.height * scale)))
    return picture if size == picture.size else picture.resize(size, Image.LANCZOS)


# --- files -----------------------------------------------------------------------------------------------------------

def input_images():
    """Image files in ComfyUI's input folder and its subfolders, as annotated names (subfolder/name.png)."""
    root = folder_paths.get_input_directory()
    found = []
    for folder, folders, names in os.walk(root):
        folders[:] = sorted(name for name in folders if not name.startswith('.'))
        for name in sorted(names):
            if name.lower().endswith(IMAGE_EXTENSIONS):
                found.append(os.path.relpath(os.path.join(folder, name), root).replace('\\', '/'))
    return found


def image_path(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('H3 Scene Map: choose a map image or connect a background image')
    path = folder_paths.get_annotated_filepath(name.strip())
    root = os.path.realpath(folder_paths.get_input_directory())
    if os.path.commonpath([root, os.path.realpath(path)]) != root or not os.path.isfile(path):
        raise ValueError(f'H3 Scene Map: the map image {name!r} is not in the input folder')
    return path


def picture_size(inputs):
    """(width, height) of a map node's picture without running it, from its literal inputs; None when unknown."""
    layout = inputs.get('layout')
    if isinstance(layout, str):
        try:
            saved = normalize(layout)
        except ValueError:
            saved = None
        if saved and saved['width'] and saved['height']:
            return saved['width'], saved['height']
    try:
        from PIL import Image
        with Image.open(image_path(inputs.get('image'))) as picture:
            return picture.size
    except (ValueError, OSError):
        return None


def prompt_line(name, inputs):
    """The prompt text for a map node's output used as the reference `name`, from its literal inputs."""
    layout = inputs.get('layout')
    try:
        layout = normalize(layout if isinstance(layout, str) else None)
    except ValueError:
        layout = normalize(None)
    size = picture_size(inputs) or (1, 1)
    return reference_text(name, layout, *size)


# --- node ------------------------------------------------------------------------------------------------------------

def _pixels(picture):
    import numpy as np
    import torch
    return torch.from_numpy(np.asarray(picture.convert('RGB')).astype(np.float32) / 255.0)[None]


def _picture(tensor):
    import numpy as np
    from PIL import Image
    return Image.fromarray(np.clip(tensor[0].cpu().numpy() * 255, 0, 255).astype(np.uint8)[..., :3])


def _preview(picture):
    """Saves a small copy of a connected background for the editor; returns its /view file."""
    small = picture.copy()
    small.thumbnail((1600, 1600))
    digest = hashlib.sha256(small.tobytes()).hexdigest()[:20]
    name = f'h3c_scene_map_{digest}.png'
    path = os.path.join(folder_paths.get_temp_directory(), name)
    if not os.path.isfile(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        small.save(path)
    return {'filename': name, 'subfolder': '', 'type': 'temp', 'width': picture.width, 'height': picture.height}


class H3C_SceneMap(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=NODE_CLASS, display_name='H3 Scene Map', category=CATEGORY,
            description='A top-down map with markers, a legend and the camera as an arrow, drawn in the node. Connect '
                        'image to a MiniMax H3 Image Still reference input to block a wide shot; the Studio tells the '
                        'model what the map shows. description is the same text for a prompt you write yourself.',
            inputs=[
                io.String.Input('image', default='', tooltip='Map picture in the input folder; the editor sets it.'),
                io.String.Input('layout', multiline=True, default=DEFAULT_LAYOUT,
                                tooltip='Markers, camera and legend as JSON; the editor sets it.'),
                io.Float.Input('megapixels', default=1.0, min=0.0, max=16.0, step=0.1,
                               tooltip='Size of the output, and of the reference MiniMax H3 Image Still makes from it '
                                       '(its other references use 4 MP). 1 MP is enough for a layout and keeps the '
                                       'still fast. 0 keeps the picture size and the usual 4 MP reference.'),
                io.Image.Input('background', optional=True,
                               tooltip='Optional map picture from another node, used instead of image. The editor '
                                       'shows it after the node has run once.'),
            ],
            outputs=[io.Image.Output(display_name='image'), io.String.Output(display_name='description')],
        )

    @classmethod
    def fingerprint_inputs(cls, image='', layout='', megapixels=1.0, background=None):
        try:
            stamp = os.path.getmtime(image_path(image))
        except ValueError:
            stamp = None
        return json.dumps([image, stamp, layout, megapixels])

    @classmethod
    def execute(cls, image='', layout=DEFAULT_LAYOUT, megapixels=1.0, background=None) -> io.NodeOutput:
        from PIL import Image, ImageOps
        saved = normalize(layout)
        preview = None
        if background is not None:
            picture = _picture(background)
            preview = _preview(picture)
        else:
            with Image.open(image_path(image)) as opened:
                picture = ImageOps.exif_transpose(opened).convert('RGB')
        picture = render(resize(picture, megapixels), saved)
        pixels = _pixels(picture)
        if megapixels:
            setattr(pixels, REFERENCE_ATTRIBUTE, float(megapixels))
        text = reference_text('The blocking map', saved, picture.width, picture.height)
        return io.NodeOutput(pixels, text, ui={'h3c_scene_map': [preview]} if preview else None)


# --- routes ----------------------------------------------------------------------------------------------------------

async def images_route(request):
    import asyncio
    from aiohttp import web
    return web.json_response({'images': await asyncio.to_thread(input_images)})


def register(routes):
    routes.get('/h3c/scene-map/images')(images_route)
