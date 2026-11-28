import json
import unittest
from pathlib import Path

from h3_continuity import scene_maps, timeline as rules

FIXTURE = Path(__file__).resolve().parent.parent / 'fixtures' / 'scene_maps' / 'linking.json'


def cases():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def positions(layout):
    camera = layout['camera']
    return {'camera': [camera[key] for key in ('x', 'y', 'tx', 'ty')] if camera else None,
            'markers': {marker['id']: [marker['x'], marker['y']] for marker in layout['markers']}}


def story(scene_map, requires=('scene-map-1',), **box):
    return json.dumps({'version': 1, 'requires': list(requires), 'prompt': '',
                       'boxes': [dict({'id': 'a', 'frames': 39, 'prompt': 'x', 'cut': False, 'scene_map': scene_map}, **box)]})


class ResolveFixtureTest(unittest.TestCase):
    def test_python_resolve_matches_every_fixture_case(self):
        for case in cases():
            parsed = rules.parse(json.dumps(case['timeline']))
            for want in case['expect']:
                got = scene_maps.resolve(parsed, want['index'])
                name = f"{case['name']} clip {want['index'] + 1}"
                self.assertEqual(got['source'], want['source'], name)
                self.assertEqual([marker['id'] for marker in got['opening']['markers']], want['markers'], name)
                self.assertEqual(positions(got['opening']), want['opening'], name)
                self.assertEqual(positions(got['end']), want['end'], name)

    def test_borrowing_clip_takes_picture_size_and_camera_look_from_its_source(self):
        case = next(case for case in cases() if case['name'] == 'continuous_borrows')
        got = scene_maps.resolve(rules.parse(json.dumps(case['timeline'])), 1)
        self.assertEqual(got['picture']['filename'], 'yard.png')
        self.assertEqual((got['width'], got['height']), (2000, 1000))
        self.assertEqual((got['opening']['camera']['fov'], got['opening']['camera']['height']), (55, 0.5))
        self.assertEqual(got['owners'], {'m1': 0, 'm2': 0, 'm9': 1})

    def test_off_map_resolves_to_none(self):
        case = next(case for case in cases() if case['name'] == 'predecessor_off')
        self.assertIsNone(scene_maps.resolve(rules.parse(json.dumps(case['timeline'])), 0))


class ValidateTest(unittest.TestCase):
    def test_absent_field_is_none(self):
        parsed = rules.parse(json.dumps({'version': 1, 'prompt': '', 'boxes': [{'id': 'a', 'frames': 39, 'prompt': 'x'}]}))
        self.assertEqual(parsed.scene_maps, [None])
        self.assertIsNone(scene_maps.resolve(parsed, 0))

    def test_off_map_needs_no_feature_and_keeps_its_work(self):
        parsed = rules.parse(story({'on': False, 'markers': [{'id': 'm1'}]}, requires=()))
        self.assertFalse(parsed.scene_maps[0]['on'])
        self.assertEqual(parsed.scene_maps[0]['markers'][0]['id'], 'm1')

    def test_on_map_requires_feature(self):
        with self.assertRaisesRegex(ValueError, 'box 1 has a scene map, which requires scene-map-1'):
            rules.parse(story({'on': True}, requires=()))

    def test_duplicate_marker_ids_rejected(self):
        with self.assertRaisesRegex(ValueError, 'box 1 scene map markers need unique ids'):
            rules.parse(story({'on': True, 'markers': [{'id': 'm1'}, {'id': 'm1'}]}))

    def test_picture_must_be_local_file(self):
        with self.assertRaisesRegex(ValueError, 'box 1 scene map picture'):
            rules.parse(story({'on': True, 'picture': {'type': 'input', 'filename': '../x.png'}}))

    def test_defaults_fill_every_key(self):
        value = rules.parse(story({'on': True})).scene_maps[0]
        self.assertEqual(set(value), {'on', 'picture', 'width', 'height', 'markers', 'camera', 'opening', 'end', 'absent',
                                      'legend', 'scale', 'video_picture'})
        self.assertEqual((value['picture'], value['video_picture'], value['absent']), (None, False, []))

    def test_resolved_layouts_survive_normalize(self):
        from tests.continuity_support import enable_comfy_cpu
        enable_comfy_cpu()
        from h3_continuity import scene_map
        got = scene_maps.resolve(rules.parse(json.dumps(cases()[0]['timeline'])), 0)
        normal = scene_map.normalize(got['opening'])
        self.assertEqual([(m['x'], m['y'], m['label']) for m in normal['markers']],
                         [(m['x'], m['y'], m['label']) for m in got['opening']['markers']])
        self.assertEqual(normal['camera']['fov'], 55)
        self.assertEqual((normal['width'], normal['height']), (2000, 1000))


W, H = 2000, 1123
SIX = ('subject_definitions:\n<Subject 1> is a woman in @image17.\n\nsummary:\nA standoff.\n\nretention_analysis:\n'
       '<Subject 1> (appears in [Shot 1]): fully_preserved - identity.\n\ndetailed_description:\n'
       '[Shot 1] Low wide shot under the overpass.\n\noverall_soundscape:\nWind.\n\nnon_diegetic_music:\nN/A')
T2VA = ('integrated_multimodal_description:\n[Shot 1] Low wide shot under the overpass.\n\noverall_soundscape:\nWind.\n\n'
        'non_diegetic_music:\nN/A')


def shot_map(**changes):
    value = {'on': True, 'picture': {'type': 'input', 'subfolder': 'maps', 'filename': 'yard.png'}, 'width': W, 'height': H,
             'markers': [{'id': 'm1', 'label': 'STRAY', 'icon': 'person'},
                         {'id': 'm2', 'label': 'OUTCAST', 'icon': 'paw', 'entity': 'e2'}],
             'camera': {'fov': 55, 'height': 0.5},
             'opening': {'camera': {'x': 1368 / W, 'y': 928 / H, 'tx': 879 / W, 'ty': 440 / H},
                         'markers': {'m1': [733 / W, 640 / H], 'm2': [957 / W, 610 / H]}},
             'end': {'markers': {'m1': [800 / W, 470 / H]}}}
    value.update(changes)
    return value


def clip_story(prompt=SIX, scene_map=None, pictures=('image17',), boxes=None, **box):
    first = dict({'id': 'a', 'frames': 39, 'prompt': prompt, 'cut': False,
                  'scene_map': shot_map() if scene_map is None else scene_map}, **box)
    return json.dumps({'version': 1, 'requires': ['scene-map-1'], 'prompt': '',
                       'pictures': [{'slot': slot, 'file': {'type': 'input', 'filename': slot + '.png'}} for slot in pictures],
                       'bible': {'entities': [{'id': 'e1', 'kind': 'character', 'name': 'STRAY', 'pictures': [], 'description': '', 'looks': []},
                                              {'id': 'e2', 'kind': 'character', 'name': 'OUTCAST', 'pictures': [], 'description': '', 'looks': []}]},
                       'boxes': [first] + list(boxes or [])})


def parts(**values):
    return dict({'blocking': '', 'definition': '', 'retention': '', 'slot': '', 'reason': ''}, **values)


class InsertTest(unittest.TestCase):
    def test_blocking_lands_on_the_description_shot_line(self):
        prompt = SIX.replace('a woman in @image17.', 'a woman in @image17, seen in [Shot 1] reference.')
        out = scene_maps.insert(prompt, parts(blocking='B.'))
        self.assertIn('[Shot 1] Low wide shot under the overpass. B.\n', out)
        self.assertNotIn('reference. B.', out)
        self.assertEqual(out.count('B.'), 1)

    def test_definition_and_retention_close_their_sections(self):
        out = scene_maps.insert(SIX, parts(definition='D.', retention='R.'))
        self.assertIn('a woman in @image17.\nD.\n\nsummary:', out)
        self.assertIn('identity.\nR.\n\ndetailed_description:', out)

    def test_t2va_format(self):
        self.assertIn('[Shot 1] Low wide shot under the overpass. B.\n\noverall_soundscape:',
                      scene_maps.insert(T2VA, parts(blocking='B.')))

    def test_description_without_a_shot_line_gets_it_at_the_end_of_its_body(self):
        prompt = SIX.replace('[Shot 1] Low', 'Low')
        self.assertIn('Low wide shot under the overpass.\nB.\n\noverall_soundscape:', scene_maps.insert(prompt, parts(blocking='B.')))

    def test_unstructured_prompt_gets_final_paragraphs(self):
        self.assertEqual(scene_maps.insert('Plain prompt.', parts(blocking='B.', definition='D.')), 'Plain prompt.\n\nD.\n\nB.')

    def test_empty_parts_change_nothing(self):
        self.assertEqual(scene_maps.insert(SIX, parts()), SIX)


class VideoPartsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.continuity_support import enable_comfy_cpu
        enable_comfy_cpu()

    def test_off_map_leaves_prompt_and_layout_key_unchanged(self):
        bare = rules.parse(clip_story(scene_map={'on': False}))
        none = rules.parse(json.dumps({**json.loads(clip_story()), 'boxes': [{'id': 'a', 'frames': 39, 'prompt': SIX}]}))
        self.assertEqual(rules.assemble_prompt(bare, 0), rules.assemble_prompt(none, 0))
        self.assertEqual(rules.layout_key(bare, 0), rules.layout_key(none, 0))
        self.assertIsNone(scene_maps.video_parts(bare, 0))

    def test_fresh_ref2va_gets_blocking_text_in_assembled_prompt(self):
        parsed = rules.parse(clip_story())
        got = scene_maps.video_parts(parsed, 0)
        self.assertEqual(got['reason'], '')
        self.assertTrue(got['blocking'].startswith('A camera about 0.5 m above the ground with a 55 degree'))
        self.assertIn('STRAY moves from the far left', got['blocking'])
        self.assertEqual((got['definition'], got['retention'], got['slot']), ('', '', ''))
        text = rules.assemble_prompt(parsed, 0)
        self.assertIn('[Shot 1] Low wide shot under the overpass. A camera about 0.5 m', text)
        self.assertEqual(rules.box_slots(parsed, 0).mode, 'ref2va')

    def test_t2va_clip_gets_text(self):
        parsed = rules.parse(clip_story(prompt=T2VA, pictures=()))
        self.assertIn('[Shot 1] Low wide shot under the overpass. A camera', rules.assemble_prompt(parsed, 0))
        self.assertEqual(rules.box_slots(parsed, 0).mode, 't2va')

    def test_first_frame_clip_gets_reason_and_no_text(self):
        parsed = rules.parse(clip_story(pictures=('image17', 'image18'), first='image18'))
        got = scene_maps.video_parts(parsed, 0)
        self.assertEqual(got['reason'], 'This clip has a start frame, which already shows the opening.')
        self.assertEqual(got['blocking'], '')
        self.assertNotIn('A camera', rules.assemble_prompt(parsed, 0))

    def test_continuing_clip_gets_reason_and_no_text(self):
        parsed = rules.parse(clip_story(boxes=[{'id': 'b', 'frames': 34, 'prompt': SIX, 'cut': False,
                                                'scene_map': {'on': True}}]))
        self.assertEqual(scene_maps.video_parts(parsed, 1)['reason'], 'This clip continues the previous one.')

    def test_missing_picture_and_camera_reasons(self):
        self.assertEqual(scene_maps.video_parts(rules.parse(clip_story(scene_map=shot_map(picture=None))), 0)['reason'],
                         'The map has no picture.')
        no_camera = shot_map(opening={'markers': {'m1': [0.3, 0.5]}})
        self.assertEqual(scene_maps.video_parts(rules.parse(clip_story(scene_map=no_camera)), 0)['reason'],
                         'The map has no camera, so the video gets no map text.')

    def test_cast_entity_marker_uses_subject_label_or_entity_name(self):
        parsed = rules.parse(clip_story(prompt=SIX.replace('<Subject 1> is a woman', '<Subject 2> is a beast'),
                                        cast={'<Subject 2>': 'e2'}))
        resolved = scene_maps.resolve(parsed, 0)
        self.assertEqual(scene_maps.names(parsed, 0, resolved, rules.assemble_prompt(parsed, 0)), {'m2': '<Subject 2>'})
        plain = rules.parse(clip_story())
        self.assertEqual(scene_maps.names(plain, 0, scene_maps.resolve(plain, 0), SIX), {'m2': 'OUTCAST'})


class PictureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.continuity_support import enable_comfy_cpu
        enable_comfy_cpu()

    def test_ref2va_clip_with_switch_gets_next_slot_and_both_lines(self):
        prompt = SIX.replace('in @image17.', 'in @image17 beside @image18.')
        parsed = rules.parse(clip_story(prompt=prompt, pictures=('image17', 'image18'), scene_map=shot_map(video_picture=True)))
        self.assertEqual(parsed.scene_map_slots, {0: 'image19'})
        picture = parsed.pictures[-1]
        self.assertEqual((picture['slot'], picture['title'], picture['file']['subfolder']),
                         ('image19', 'Scene map', 'h3c_scene_maps'))
        self.assertEqual(picture['scene_map']['picture']['filename'], 'yard.png')
        text = rules.assemble_prompt(parsed, 0)
        self.assertIn('\n@image19 is a storyboard reference for [Shot 1]: a top-down plan of this place defining the camera '
                      'viewpoint and where each subject starts.\n\nsummary:', text)
        self.assertIn('\n@image19 ([Shot 1] storyboard): weak_reference - only the camera viewpoint and where each subject '
                      "starts are followed; the plan's view, symbols, arrow, labels and legend are not reproduced.\n\n"
                      'detailed_description:', text)
        slots = rules.box_slots(parsed, 0)
        self.assertEqual((slots.mode, slots.tags['image19']), ('ref2va', '<Picture 3>'))
        self.assertEqual(slots.tags['image17'], '<Picture 1>')

    def test_slot_skips_every_image_slot_already_named(self):
        prompt = SIX.replace('in @image17.', 'in @image17 and @image30.')
        parsed = rules.parse(clip_story(prompt=prompt, scene_map=shot_map(video_picture=True)))
        self.assertEqual(parsed.scene_map_slots, {0: 'image31'})

    def test_t2va_clip_never_gets_the_picture(self):
        parsed = rules.parse(clip_story(prompt=T2VA, pictures=(), scene_map=shot_map(video_picture=True)))
        self.assertEqual(parsed.scene_map_slots, {})
        self.assertEqual(rules.box_slots(parsed, 0).mode, 't2va')
        self.assertNotIn('storyboard', rules.assemble_prompt(parsed, 0))

    def test_nine_pictures_blocks_picture_keeps_text(self):
        slots = [f'image{n}' for n in range(17, 26)]
        prompt = SIX.replace('in @image17.', 'in ' + ' '.join('@' + slot for slot in slots) + '.')
        parsed = rules.parse(clip_story(prompt=prompt, pictures=slots, scene_map=shot_map(video_picture=True)))
        self.assertEqual(parsed.scene_map_slots, {})
        got = scene_maps.video_parts(parsed, 0)
        self.assertEqual(got['reason'], 'This clip already sends 9 pictures, so the map goes in as text only.')
        self.assertTrue(got['blocking'])
        self.assertEqual((got['definition'], got['slot']), ('', ''))

    def test_switch_off_sends_no_picture(self):
        parsed = rules.parse(clip_story())
        self.assertEqual(parsed.scene_map_slots, {})
        self.assertEqual(len(parsed.pictures), 1)

    def test_layout_key_changes_when_only_the_picture_changes(self):
        recoloured = shot_map(video_picture=True)
        recoloured['markers'][0]['color'] = '#3a86ff'
        stories = [rules.parse(clip_story(scene_map=value)) for value in (shot_map(video_picture=True), recoloured)]
        self.assertEqual(*[rules.assemble_prompt(parsed, 0) for parsed in stories])
        self.assertNotEqual(*[rules.layout_key(parsed, 0) for parsed in stories])

    def test_ensure_renders_once_and_rerenders_when_base_is_newer(self):
        import os, tempfile
        from unittest import mock
        import folder_paths
        from PIL import Image
        with tempfile.TemporaryDirectory() as root, \
                mock.patch.object(folder_paths, 'get_directory_by_type', lambda kind: root):
            os.makedirs(os.path.join(root, 'maps'))
            base = os.path.join(root, 'maps', 'yard.png')
            Image.new('RGB', (W, H), (200, 180, 120)).save(base)
            parsed = rules.parse(clip_story(scene_map=shot_map(video_picture=True)))
            picture = parsed.pictures[-1]
            path = scene_maps.ensure(picture)
            self.assertTrue(path.endswith(os.path.join('h3c_scene_maps', picture['file']['filename'])))
            with Image.open(path) as made:
                self.assertAlmostEqual(made.width * made.height / 1e6, 1.0, delta=0.01)
            stamp = os.path.getmtime(path)
            self.assertEqual(scene_maps.ensure(picture), path)
            self.assertEqual(os.path.getmtime(path), stamp)
            os.utime(base, (stamp + 10, stamp + 10))
            scene_maps.ensure(picture)
            self.assertGreater(os.path.getmtime(path), stamp)

    def test_ensure_missing_base_names_clip_and_file(self):
        import tempfile
        from unittest import mock
        import folder_paths
        with tempfile.TemporaryDirectory() as root, \
                mock.patch.object(folder_paths, 'get_directory_by_type', lambda kind: root):
            parsed = rules.parse(clip_story(scene_map=shot_map(video_picture=True)))
            with self.assertRaisesRegex(ValueError, r"box 1 uses a scene map picture \(yard\.png\), but the file is missing "
                                                    r"from ComfyUI's input folder"):
                scene_maps.ensure(parsed.pictures[-1])

    def test_preview_returns_mode_parts_and_reason(self):
        got = scene_maps.preview(clip_story(scene_map=shot_map(video_picture=True)), 'a')
        self.assertEqual(got['video']['mode'], 'ref2va')
        self.assertEqual(got['video']['parts']['slot'], 'image18')
        self.assertEqual(got['video']['reason'], '')
        first = scene_maps.preview(clip_story(pictures=('image17', 'image18'), first='image18'), 'a')
        self.assertEqual(first['video']['reason'], 'This clip has a start frame, which already shows the opening.')
        self.assertIsNone(scene_maps.preview(clip_story(scene_map={'on': False}), 'a')['video']['parts'])
        with self.assertRaisesRegex(ValueError, 'no clip'):
            scene_maps.preview(clip_story(), 'zzz')

    def test_preview_shows_each_still_line(self):
        got = scene_maps.preview(clip_story(), 'a')['stills']
        self.assertTrue(got['first'].startswith('The map is a storyboard reference: a top-down plan'))
        self.assertNotEqual(got['first'], got['last'])
        self.assertEqual(scene_maps.preview(clip_story(scene_map={'on': False}), 'a')['stills'], {})


STILL = ('@still{k} is a storyboard reference: a top-down plan of this place defining the camera viewpoint and where '
         'each subject stands; nothing from the plan is drawn.')


class StillTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.continuity_support import enable_comfy_cpu
        enable_comfy_cpu()

    def test_first_frame_still_gets_opening_map_last_to_end(self):
        parsed = rules.parse(clip_story())
        resolved = scene_maps.resolve(parsed, 0)
        self.assertEqual(scene_maps.still_layout(parsed, 0, {'kind': 'first'}), resolved['opening'])
        self.assertEqual(scene_maps.still_layout(parsed, 0, {'kind': 'last'}), resolved['end'])
        self.assertIsNone(scene_maps.still_layout(rules.parse(clip_story(scene_map=shot_map(picture=None))), 0, {}))
        self.assertIsNone(scene_maps.still_layout(rules.parse(clip_story(scene_map={'on': False})), 0, {}))

    def test_still_line_exact_copy(self):
        parsed = rules.parse(clip_story())
        line = scene_maps.still_line('@still2', scene_maps.still_layout(parsed, 0, {'kind': 'first'}))
        self.assertTrue(line.startswith(STILL.format(k=2) + ' The camera stands'), line)
        self.assertIn('STRAY', line)
        bare = scene_maps.still_layout(rules.parse(clip_story(scene_map=shot_map(opening={'markers': {}}))), 0, {})
        self.assertEqual(scene_maps.still_line('@still1', bare), STILL.format(k=1))

    def prepare(self, scene_map=None, kind='first', inputs=None, prompt='STRAY on the trail.'):
        import os, tempfile
        from unittest import mock
        import folder_paths
        from PIL import Image
        from h3_continuity import minimax_image_nodes as image, stills
        from tests.python.test_minimax_image_still import ARGS, FILES
        from tests.python.test_ph3_image_recipe import recipe
        story = json.loads(clip_story(prompt=prompt, pictures=(), scene_map=scene_map))
        del story['bible']
        saved = {'api': {'5': {'class_type': 'H3C_MiniMaxH3ImageStill', 'inputs': {**ARGS, **(inputs or {})}},
                         '9': {'class_type': 'LoadImage', 'inputs': {'image': 'yard.png'}}}}
        body = dict(name='scene-maps-test', box='a', target={'kind': kind}, workflow=saved, recipe=recipe(),
                    timeline=json.dumps(story), prompt='')
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        os.makedirs(os.path.join(root.name, 'maps'))
        Image.new('RGB', (W, H), (200, 180, 120)).save(os.path.join(root.name, 'maps', 'yard.png'))
        Image.new('RGB', (64, 64)).save(os.path.join(root.name, 'yard.png'))
        with mock.patch.object(folder_paths, 'get_directory_by_type', lambda kind: root.name), \
                mock.patch.object(folder_paths, 'get_input_directory', lambda: root.name), \
                mock.patch.object(folder_paths, 'get_output_directory', lambda: root.name), \
                mock.patch('folder_paths.get_filename_list', lambda folder: FILES.get(folder, [])), \
                mock.patch.dict('nodes.NODE_CLASS_MAPPINGS', {'H3C_MiniMaxH3ImageStill': image.H3C_MiniMaxH3ImageStill}):
            result = stills.prepare(body)
            self.assertTrue(result.get('ok'), result)
            refs = result['provenance']['references']
            files = [stills.file_path(ref['file']) for ref in refs if ref.get('title') == 'Scene map']
            sizes = []
            for path in files:
                with Image.open(path) as made:
                    sizes.append(made.width * made.height / 1e6)
        return result, refs, sizes

    def test_prepared_still_request_has_map_reference_last_at_one_megapixel(self):
        result, refs, sizes = self.prepare(inputs={'images.image_2': ['9', 0]}, prompt='STRAY on the trail matching @still2.')
        prompt = result['prompt']['5']['inputs']['prompt']
        self.assertEqual([ref['slot'] for ref in refs], ['still2', 'still3'])
        ref = refs[-1]
        self.assertEqual((ref['roles'], ref['title'], ref['reference_megapixels']), (['blocking map: still3'], 'Scene map', 1.0))
        self.assertNotIn('scene_map', ref)
        self.assertAlmostEqual(sizes[0], 1.0, delta=0.01)
        self.assertTrue(prompt.startswith('STRAY on the trail matching <Picture 1>.\n\n' + STILL.replace('@still{k}', ref['label'])), prompt)
        source = result['prompt'][ref['port']['node']]['inputs'][ref['port']['input']][0]
        self.assertEqual(json.loads(result['prompt'][source]['inputs']['source'])['reference_megapixels'], 1.0)

    def test_last_frame_still_draws_the_end_layout(self):
        first = self.prepare()[1][-1]['sha256']
        self.assertNotEqual(self.prepare(kind='last')[1][-1]['sha256'], first)

    def test_map_off_still_request_unchanged(self):
        result, refs, _ = self.prepare(scene_map={'on': False})
        self.assertEqual(refs, [])
        self.assertEqual(result['prompt']['5']['inputs']['prompt'], 'STRAY on the trail.')

    def test_image_source_keeps_the_map_at_its_own_size(self):
        from unittest import mock
        import torch
        from h3_continuity import scene_map, still_nodes
        with mock.patch('h3_continuity.stills.load_pixel_source', lambda source: torch.zeros(1, 4, 4, 3)):
            pixels = still_nodes.H3C_StillImageSource.execute(json.dumps({'reference_megapixels': 1.0})).result[0]
            plain = still_nodes.H3C_StillImageSource.execute(json.dumps({})).result[0]
        self.assertEqual(getattr(pixels, scene_map.REFERENCE_ATTRIBUTE), 1.0)
        self.assertFalse(hasattr(plain, scene_map.REFERENCE_ATTRIBUTE))


if __name__ == '__main__':
    unittest.main()
