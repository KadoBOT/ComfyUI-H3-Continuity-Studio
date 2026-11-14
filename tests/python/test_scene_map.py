import json
import os
import tempfile
import unittest
from unittest import mock

import torch
from PIL import Image

from tests.continuity_support import enable_comfy_cpu
enable_comfy_cpu()

from h3_continuity import minimax_image_nodes as image, scene_map, stills  # noqa: E402
from tests.python.test_minimax_image_still import ARGS, FILES  # noqa: E402
from tests.python.test_ph3_image_recipe import recipe  # noqa: E402

W, H = 2000, 1123
# Shot 22 of The Carcass, the layout the arrow test generated from.
SHOT_22 = {'width': W, 'height': H, 'camera': {'x': 1368 / W, 'y': 928 / H, 'tx': 879 / W, 'ty': 440 / H, 'fov': 55,
                                                 'height': 0.5},
           'markers': [{'x': 879 / W, 'y': 440 / H, 'icon': 'target', 'color': '#e0352b', 'label': 'WOUNDED GRAZER'},
                       {'x': 733 / W, 'y': 640 / H, 'icon': 'person', 'color': '#ff7a1a', 'label': 'STRAY'},
                       {'x': 957 / W, 'y': 610 / H, 'icon': 'paw', 'color': '#7b4bd6', 'label': 'OUTCAST'}]}


def pixel(picture, x, y):
    return picture.getpixel((round(x), round(y)))


class LayoutTest(unittest.TestCase):
    def test_missing_and_out_of_range_fields_get_defaults(self):
        layout = scene_map.normalize({'markers': [{'x': 3, 'y': -1, 'icon': 'nope', 'color': 'red', 'size': 9,
                                                   'label': ' A ', 'text': 'ABCD', 'legend': False}, 'junk'],
                                      'camera': {'x': 0.5, 'y': 0.5, 'tx': 0.5, 'ty': 0.5, 'fov': 400},
                                      'legend': {'position': 'middle'}, 'scale': 0})
        marker = layout['markers'][0]
        self.assertEqual((marker['x'], marker['y'], marker['icon'], marker['color'], marker['size']), (1, 0, 'dot', '#e0352b', 4))
        self.assertEqual((marker['label'], marker['text'], marker['legend']), ('A', 'ABC', False))
        self.assertEqual(len(layout['markers']), 1)
        self.assertEqual(layout['camera']['fov'], 170)
        self.assertNotEqual((layout['camera']['x'], layout['camera']['y']), (layout['camera']['tx'], layout['camera']['ty']))
        self.assertEqual(layout['legend'], {'show': True, 'position': 'bottom-left'})
        self.assertEqual(layout['scale'], 0.25)
        self.assertIsNone(scene_map.normalize(None)['camera'])
        with self.assertRaisesRegex(ValueError, 'JSON'):
            scene_map.normalize('{')
        with self.assertRaisesRegex(ValueError, 'object'):
            scene_map.normalize('[]')

    def test_every_icon_has_a_name_and_drawable_shapes(self):
        for key, icon in scene_map.icons().items():
            with self.subTest(icon=key):
                self.assertTrue(icon['name'])
                for shape in icon['shapes']:
                    self.assertTrue({'circle', 'ring', 'poly', 'line'} & set(shape))

    def test_legend_lists_each_labelled_marker_once_then_the_camera(self):
        layout = scene_map.normalize({**SHOT_22, 'markers': SHOT_22['markers'] + [
            {**SHOT_22['markers'][1]}, {'x': 0.1, 'y': 0.1, 'label': ''}, {'x': 0.2, 'y': 0.2, 'label': 'Hidden', 'legend': False}]})
        rows = scene_map.legend_rows(layout)
        self.assertEqual([row[3] for row in rows][:3], ['WOUNDED GRAZER', 'STRAY', 'OUTCAST'])
        self.assertEqual(rows[-1][3], 'CAMERA · tip = lens, 0.5 m above ground, 55° view')
        self.assertEqual(len(rows), 4)


class DescriptionTest(unittest.TestCase):
    def test_shot_22_reads_as_the_prompt_that_worked(self):
        layout = scene_map.normalize(SHOT_22)
        text = scene_map.describe(layout, W, H)
        self.assertIn('The camera stands at the bottom right of the map, about 0.5 m above the ground, and looks towards '
                      'the top left of the map with a 55 degree horizontal field of view.', text)
        self.assertIn('In frame, from left to right: STRAY on the far left, in the distance, farthest from the camera; '
                      'OUTCAST just left of centre, in the middle distance, nearest to the camera; '
                      'WOUNDED GRAZER in the centre, in the distance.', text)
        self.assertNotIn('Out of frame', text)

    def test_markers_outside_or_behind_the_view_are_out_of_frame(self):
        layout = scene_map.normalize({**SHOT_22, 'markers': SHOT_22['markers'] + [
            {'x': 0.95, 'y': 0.95, 'icon': 'flag'}, {'x': 0.05, 'y': 0.95, 'icon': 'text', 'text': '7'}]})
        self.assertIn('Out of frame: a flag marker, the marker 7.', scene_map.describe(layout, W, H))
        right = scene_map.normalize({'camera': {'x': 0.5, 'y': 0.9, 'tx': 0.5, 'ty': 0.1, 'fov': 60},
                                     'markers': [{'x': 0.58, 'y': 0.5, 'label': 'R'}]})
        self.assertIn('R just right of centre', scene_map.describe(right, 1000, 1000))

    def test_reference_text_names_the_picture_and_rules_out_every_mark(self):
        layout = scene_map.normalize(SHOT_22)
        text = scene_map.reference_text('@still3', layout, W, H)
        self.assertTrue(text.startswith('@still3 is a top-down blocking map of this place, a plan for the shot and not part '
                                        'of the picture. The arrow on it marks the camera'))
        self.assertTrue(text.endswith('no arrow, camera, marker, label or legend appears in the picture.'))
        plain = scene_map.reference_text('The map', scene_map.normalize(None), 100, 100)
        self.assertNotIn('arrow', plain)
        self.assertNotIn('camera', plain)


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.map = Image.new('RGB', (W, H), (200, 180, 120))

    def test_markers_arrow_labels_and_legend_are_drawn_in_place(self):
        layout = scene_map.normalize(SHOT_22)
        picture = scene_map.render(self.map, layout)
        unit = scene_map.MARKER_RADIUS * W
        self.assertEqual(picture.size, (W, H))
        r, g, b = pixel(picture, 733 + unit * 0.6, 640)
        self.assertGreater(r, 220)
        self.assertLess(b, 80)  # STRAY's orange disc, beside the white glyph
        # Just behind the arrow's tip, on its axis, the arrow is white.
        self.assertEqual(pixel(picture, 1368 + unit * 2.5 * 0.707, 928 + unit * 2.5 * 0.707), (255, 255, 255))
        self.assertEqual(pixel(picture, 1368 - unit * 3, 928 - unit * 3), (200, 180, 120))  # nothing ahead of the camera
        self.assertLess(sum(pixel(picture, unit * 1.2, H - unit * 1.2)), 300)  # legend box, bottom left
        hidden = scene_map.render(self.map, scene_map.normalize({**SHOT_22, 'legend': {'show': False}}))
        self.assertEqual(pixel(hidden, unit * 1.2, H - unit * 1.2), (200, 180, 120))

    def test_text_markers_and_legend_corners(self):
        layout = scene_map.normalize({'markers': [{'x': 0.5, 'y': 0.5, 'icon': 'text', 'text': '12', 'label': 'Two',
                                                   'color': '#ffd23f'}], 'legend': {'position': 'top-right'}})
        picture = scene_map.render(self.map, layout)
        unit = scene_map.MARKER_RADIUS * W
        self.assertLess(sum(pixel(picture, W - unit * 1.2, unit * 1.2)), 300)
        self.assertEqual(pixel(picture, unit * 1.2, H - unit * 1.2), (200, 180, 120))

    def test_resize_keeps_the_aspect_and_sets_the_area(self):
        small = scene_map.resize(self.map, 1.0)
        self.assertAlmostEqual(small.width * small.height / 1e6, 1.0, delta=0.01)
        self.assertAlmostEqual(small.width / small.height, W / H, places=2)
        self.assertIs(scene_map.resize(self.map, 0), self.map)


class NodeTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        os.makedirs(os.path.join(self.folder.name, 'maps'))
        Image.new('RGB', (W, H), (200, 180, 120)).save(os.path.join(self.folder.name, 'maps', 'site.png'))
        patch = mock.patch('folder_paths.get_input_directory', lambda: self.folder.name)
        patch.start()
        self.addCleanup(patch.stop)

    def test_lists_input_images_and_rejects_files_outside_the_input_folder(self):
        Image.new('RGB', (4, 4)).save(os.path.join(self.folder.name, 'a.jpg'))
        open(os.path.join(self.folder.name, 'notes.txt'), 'w').close()
        self.assertEqual(scene_map.input_images(), ['a.jpg', 'maps/site.png'])
        for name in ('', '../outside.png', 'missing.png'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                scene_map.image_path(name)

    def test_output_is_one_megapixel_and_names_its_reference_size(self):
        result = scene_map.H3C_SceneMap.execute(image='maps/site.png', layout=json.dumps(SHOT_22), megapixels=1.0)
        pixels, text = result.result
        self.assertEqual(pixels.shape[0], 1)
        self.assertAlmostEqual(pixels.shape[1] * pixels.shape[2] / 1e6, 1.0, delta=0.01)
        self.assertEqual(getattr(pixels, scene_map.REFERENCE_ATTRIBUTE), 1.0)
        self.assertTrue(text.startswith('The blocking map is a top-down blocking map'))
        self.assertIn('STRAY on the far left', text)
        self.assertIsNone(result.ui)
        whole = scene_map.H3C_SceneMap.execute(image='maps/site.png', layout=json.dumps(SHOT_22), megapixels=0).result[0]
        self.assertEqual(tuple(whole.shape), (1, H, W, 3))
        self.assertFalse(hasattr(whole, scene_map.REFERENCE_ATTRIBUTE))

    def test_a_connected_background_wins_and_is_previewed_for_the_editor(self):
        background = torch.full((1, 300, 400, 3), 0.5)
        with tempfile.TemporaryDirectory() as temp, mock.patch('folder_paths.get_temp_directory', lambda: temp):
            result = scene_map.H3C_SceneMap.execute(image='', layout='{}', megapixels=0, background=background)
            preview = result.ui['h3c_scene_map'][0]
            self.assertTrue(os.path.isfile(os.path.join(temp, preview['filename'])))
        self.assertEqual((preview['type'], preview['width'], preview['height']), ('temp', 400, 300))
        self.assertEqual(tuple(result.result[0].shape), (1, 300, 400, 3))
        with self.assertRaisesRegex(ValueError, 'choose a map image'):
            scene_map.H3C_SceneMap.execute(image='', layout='{}')

    def test_the_still_node_keeps_a_map_at_its_own_size(self):
        plain, map_pixels = torch.zeros(1, 8, 8, 3), torch.zeros(1, 8, 8, 3)
        setattr(map_pixels, scene_map.REFERENCE_ATTRIBUTE, 1.0)
        with mock.patch('folder_paths.get_filename_list', lambda folder: FILES.get(folder, [])), \
             mock.patch.dict('nodes.NODE_CLASS_MAPPINGS', {'MiniMaxH3ImageConditioning': object}):
            graph = image.H3C_MiniMaxH3ImageStill.execute(**ARGS, images={'image_1': plain, 'image_2': map_pixels}).expand
        scaled = [node['inputs'] for node in graph.values() if node['class_type'] == 'ResizeImageMaskNode'
                  and node['inputs']['resize_type'] == 'scale total pixels']
        self.assertEqual([item['resize_type.megapixels'] for item in scaled], [4.0, 1.0])

    def test_studio_introduces_a_connected_map_after_the_clip_and_numbers_it_last(self):
        clip = 'STRAY on the trail. Nobody else.'
        saved = {'api': {'5': {'class_type': 'H3C_MiniMaxH3ImageStill', 'inputs': {**ARGS, 'images.image_2': ['9', 0]}},
                         '9': {'class_type': 'H3C_SceneMap', 'inputs': {'image': 'maps/site.png', 'megapixels': 1.0,
                                                                        'layout': json.dumps(SHOT_22)}}}}
        timeline = json.dumps({'prompt': '', 'boxes': [{'id': 'b1', 'frames': 22, 'prompt': clip}]})

        def prepare(prompt):
            body = dict(name='scene-map-test', box='b1', target={'kind': 'first'}, workflow=saved, recipe=recipe(),
                        timeline=timeline.replace(clip, prompt), prompt='stale')
            with mock.patch('folder_paths.get_filename_list', lambda folder: FILES.get(folder, [])), \
                 mock.patch.dict('nodes.NODE_CLASS_MAPPINGS', {'H3C_MiniMaxH3ImageStill': image.H3C_MiniMaxH3ImageStill}):
                result = stills.prepare(body)
            self.assertTrue(result.get('ok'), result)
            return result

        result = prepare(clip)
        prompt = result['prompt']['5']['inputs']['prompt']
        self.assertTrue(prompt.startswith(clip + '\n\n<Picture 1> is a top-down blocking map of this place'))
        self.assertIn('STRAY on the far left', prompt)
        self.assertEqual(result['prompt']['5']['inputs']['images.image_1'], ['9', 0])
        ref = result['provenance']['references'][0]
        self.assertEqual((ref['roles'], ref['title']), (['blocking map: still2'], 'Blocking map'))
        self.assertNotIn('scene_map', ref)
        mentioned = prepare('Follow @still2 for the blocking.')['prompt']['5']['inputs']['prompt']
        self.assertEqual(mentioned, 'Follow <Picture 1> for the blocking.')


if __name__ == '__main__':
    unittest.main()
