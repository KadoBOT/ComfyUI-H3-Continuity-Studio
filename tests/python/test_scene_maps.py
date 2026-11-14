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


if __name__ == '__main__':
    unittest.main()
