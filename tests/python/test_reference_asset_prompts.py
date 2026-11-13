import json
import unittest
from unittest import mock

from h3_continuity import image_recipe, reference_assets, stills

STYLE = ("Painted angular planes and hard rim light. Safety orange belongs only to STRAY's jacket. "
         "Characters move as living animated figures.")


def entity(id, kind, name, description, looks=()):
    return dict(id=id, kind=kind, name=name, pictures=[], description=description, looks=list(looks))


def document():
    return {'boxes': [{'id': 'b1', 'frames': 22, 'prompt': '',
                       'schedule': {'entities': ['e1', 'e2'], 'place': 'e3'}},
                      {'id': 'b2', 'frames': 22, 'prompt': '',
                       'schedule': {'entities': ['e1'], 'place': 'e3'}}],
            'bible': {'style': {'look': STYLE}, 'entities': [
                entity('e1', 'character', 'STRAY', 'A wiry woman in a safety-orange jacket.',
                       [{'from': 'b2', 'description': 'Her jacket is torn.', 'pictures': []}]),
                entity('e2', 'character', 'Wounded grazer', 'A barrel-bodied grazer with long horns.'),
                entity('e3', 'place', 'Overpass and Grassland', 'A collapsed highway in dry grass.')]}}


def planned_prompt(key, approved_identity=None):
    saved = document()
    body = {'timeline': json.dumps(saved), 'recipe': {'version': 2, 'adapter': 'pixels'}, 'workflow': {'api': {}}}
    row = next(r for r in reference_assets.catalog(saved, body) if r['key'] == key)
    body.update(asset_key=key, input_fingerprint=row['input_fingerprint'], prompt=row['prompt'])
    with mock.patch.object(stills, '_pixel_references', return_value=[]), \
         mock.patch.object(reference_assets, '_approved_pixels', return_value=approved_identity or []), \
         mock.patch.object(image_recipe, 'prepare', return_value={'ok': True}) as prepared:
        answer = reference_assets.prepare(body)
    assert answer == {'ok': True}, answer
    return prepared.call_args.args[2]['prompt']


class CastSheetTest(unittest.TestCase):
    def test_cast_is_a_character_sheet_with_face_and_full_body_on_ivory(self):
        prompt = planned_prompt('entity:e2')
        self.assertTrue(prompt.startswith('A character reference sheet'), prompt)
        self.assertIn('plain ivory background', prompt)
        self.assertIn('face', prompt)
        self.assertIn('full body', prompt)
        self.assertIn('A barrel-bodied grazer with long horns.', prompt)
        self.assertIn('no text, letters or numbers', prompt)

    def test_a_look_is_a_character_sheet_of_the_same_identity(self):
        identity = [{'slot': 'image17', 'roles': ['identity: STRAY'], 'sha256': 'a' * 64}]
        prompt = planned_prompt('entity:e1:look:b2', identity)
        self.assertTrue(prompt.startswith('A character reference sheet'), prompt)
        self.assertIn('same character as the identity reference', prompt)
        self.assertIn('Her jacket is torn.', prompt)

    def test_style_sentences_about_other_cast_are_left_out(self):
        prompt = planned_prompt('entity:e2')
        self.assertIn('Painted angular planes and hard rim light.', prompt)
        self.assertNotIn('STRAY', prompt)
        self.assertIn('STRAY', planned_prompt('entity:e1'))


class LocationGridTest(unittest.TestCase):
    def test_location_is_an_empty_two_by_two_grid_of_camera_angles(self):
        prompt = planned_prompt('entity:e3')
        self.assertTrue(prompt.startswith('A location reference sheet'), prompt)
        self.assertIn('2 rows and 2 columns', prompt)
        for cell in ('row 1, column 1', 'row 1, column 2', 'row 2, column 1', 'row 2, column 2'):
            self.assertIn(cell, prompt)
        self.assertIn('A collapsed highway in dry grass.', prompt)
        self.assertIn('no people, characters, animals or creatures', prompt)
        self.assertNotIn('STRAY', prompt)
        self.assertNotIn('Characters move', prompt)


if __name__ == '__main__':
    unittest.main()
