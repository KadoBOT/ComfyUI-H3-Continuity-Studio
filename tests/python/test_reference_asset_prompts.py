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


SIZED = {'version': 2, 'adapter': 'pixels', 'bindings': {'size': {'width': [{}], 'height': [{}]}}}


def planned(key, approved_identity=None, saved=None, recipe=None, size=None):
    saved = saved or document()
    recipe = recipe or {'version': 2, 'adapter': 'pixels'}
    body = {'timeline': json.dumps(saved), 'recipe': recipe, 'workflow': {'api': {}}}
    row = next(r for r in reference_assets.catalog(saved, body) if r['key'] == key)
    body.update(asset_key=key, input_fingerprint=row['input_fingerprint'], prompt=row['prompt'])
    if size:
        body['size'] = size
    with mock.patch.object(stills, '_pixel_references', return_value=[]), \
         mock.patch.object(reference_assets, '_approved_pixels', return_value=approved_identity or []), \
         mock.patch.object(image_recipe, 'prepare', return_value={'ok': True}) as prepared:
        answer = reference_assets.prepare(body)
    assert answer == {'ok': True}, answer
    return prepared.call_args.args[2]


def planned_prompt(key, approved_identity=None):
    return planned(key, approved_identity)['prompt']


class CastSheetTest(unittest.TestCase):
    def test_cast_is_a_six_column_sheet_with_one_head_and_four_headless_bodies(self):
        prompt = planned_prompt('entity:e2')
        self.assertTrue(prompt.startswith('A 16:9 landscape character reference sheet'), prompt)
        self.assertIn('ivory background', prompt)
        self.assertIn('six equal-width vertical columns', prompt)
        self.assertIn('The face appears exactly once', prompt)
        for column in ('Columns 1-2 (merged)', 'Column 3: front', 'Column 4: true 90-degree profile',
                       'Column 5: back', 'Column 6: relaxed'):
            self.assertIn(column, prompt)
        self.assertIn('neck-down only', prompt)
        self.assertIn('NO head, NO face and NO hair', prompt)
        self.assertIn('A barrel-bodied grazer with long horns.', prompt)
        self.assertIn('no text, letters or numbers', prompt)

    def test_a_look_is_a_character_sheet_of_the_same_identity(self):
        identity = [{'slot': 'image17', 'roles': ['identity: STRAY'], 'sha256': 'a' * 64}]
        prompt = planned_prompt('entity:e1:look:b2', identity)
        self.assertTrue(prompt.startswith('A 16:9 landscape character reference sheet of the same character'), prompt)
        self.assertIn('same character as the identity reference', prompt)
        self.assertIn('Her jacket is torn.', prompt)

    def test_style_sentences_about_other_cast_are_left_out(self):
        prompt = planned_prompt('entity:e2')
        self.assertIn('Painted angular planes and hard rim light.', prompt)
        self.assertNotIn('STRAY', prompt)
        self.assertIn('STRAY', planned_prompt('entity:e1'))


    def test_a_style_sentence_about_another_character_without_naming_them_is_left_out(self):
        saved = document()
        saved['bible']['style']['look'] = ('Painted angular planes and hard rim light. '
                                           "Safety orange appears only on the woman's jacket.")
        prompt = planned('entity:e2', saved=saved)['prompt']
        self.assertIn('Painted angular planes', prompt)
        self.assertNotIn('Safety orange', prompt)
        self.assertNotIn('jacket', prompt)

    def test_the_sheet_does_not_assume_a_human_body(self):
        prompt = planned_prompt('entity:e2')
        self.assertIn('Never turn a non-human character into a person', prompt)
        for human in ('collarbone', 'five fingers'):
            self.assertNotIn(human, prompt)


class CastSheetSizeTest(unittest.TestCase):
    def test_a_sheet_is_16_9_unless_the_reference_sets_a_size(self):
        self.assertEqual(planned('entity:e2', recipe=SIZED).get('size'), {'width': 2048, 'height': 1152})
        own = {'width': 1024, 'height': 1536}
        self.assertEqual(planned('entity:e2', recipe=SIZED, size=own).get('size'), own)

    def test_a_workflow_without_size_inputs_keeps_its_own_size(self):
        self.assertNotIn('size', planned('entity:e2'))

    def test_a_location_keeps_the_workflow_size(self):
        self.assertNotIn('size', planned('entity:e3', recipe=SIZED))


def with_overrides(key, overrides):
    saved = document()
    saved['reference_preparation'] = {'version': 1, 'generate': {}, 'requests': [],
                                      'assets': [{'key': key, 'category': 'cast', 'role': 'identity',
                                                  'part_overrides': overrides}]}
    return saved


def row_of(saved, key):
    return next(r for r in reference_assets.catalog(saved) if r['key'] == key)


class PromptPartsTest(unittest.TestCase):
    def test_a_row_lists_every_text_the_studio_adds_in_the_order_it_is_sent(self):
        parts = row_of(document(), 'entity:e2')['prompt_parts']
        self.assertEqual([p['id'] for p in parts], ['layout', 'style'])
        self.assertEqual([p['where'] for p in parts], ['before', 'after'])
        self.assertTrue(parts[0]['text'].startswith('A 16:9 landscape character reference sheet'))
        self.assertTrue(parts[1]['text'].startswith('Visual style: Painted angular planes'))
        self.assertTrue(all(p['enabled'] and not p['edited'] for p in parts))
        self.assertEqual([p['id'] for p in row_of(document(), 'entity:e3')['prompt_parts']], ['layout', 'style', 'empty'])

    def test_the_prompt_is_what_the_parts_say(self):
        saved = document()
        parts = row_of(saved, 'entity:e2')['prompt_parts']
        prompt = planned('entity:e2')['prompt']
        self.assertEqual(prompt, '\n'.join([parts[0]['text'], 'A barrel-bodied grazer with long horns.', parts[1]['text']]))

    def test_a_part_can_be_switched_off_for_one_reference(self):
        saved = with_overrides('entity:e2', {'style': {'enabled': False}})
        self.assertNotIn('Visual style', planned('entity:e2', saved=saved)['prompt'])
        self.assertIn('Visual style', planned('entity:e1')['prompt'])
        self.assertFalse(row_of(saved, 'entity:e2')['prompt_parts'][1]['enabled'])

    def test_a_part_can_be_rewritten_for_one_reference(self):
        saved = with_overrides('entity:e2', {'layout': {'text': 'A creature turnaround on ivory.'}})
        prompt = planned('entity:e2', saved=saved)['prompt']
        self.assertTrue(prompt.startswith('A creature turnaround on ivory.\n'), prompt)
        self.assertNotIn('six equal-width', prompt)
        self.assertTrue(row_of(saved, 'entity:e2')['prompt_parts'][0]['edited'])
        self.assertEqual(saved['bible']['style']['look'], STYLE)

    def test_a_sheet_without_its_layout_is_not_forced_to_16_9(self):
        saved = with_overrides('entity:e2', {'layout': {'enabled': False}})
        self.assertNotIn('size', planned('entity:e2', saved=saved, recipe=SIZED))

    def test_edits_change_the_design_only_for_that_reference(self):
        plain = row_of(document(), 'entity:e2')['input_fingerprint']
        edited = row_of(with_overrides('entity:e2', {'style': {'enabled': False}}), 'entity:e2')['input_fingerprint']
        self.assertNotEqual(plain, edited)
        self.assertEqual(row_of(document(), 'entity:e1')['input_fingerprint'],
                         row_of(with_overrides('entity:e2', {'style': {'enabled': False}}), 'entity:e1')['input_fingerprint'])

    def test_bad_edits_are_refused(self):
        for bad in ({'nope': {'enabled': False}}, {'style': {'enabled': 'no'}}, {'style': {'text': 3}}, {'style': 'x'}):
            with self.assertRaises(ValueError):
                reference_assets.catalog(with_overrides('entity:e2', bad))


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

    def test_a_place_with_an_interior_gets_one_interior_camera(self):
        prompt = planned_prompt('entity:e3')
        self.assertIn('If the place has an interior', prompt)
        self.assertIn('row 2, column 2, instead shows that interior from the inside', prompt)


class ObjectGridTest(unittest.TestCase):
    def test_object_is_a_two_by_two_ivory_grid_of_angles_of_only_the_object(self):
        saved = document()
        saved['bible']['entities'].append(entity('e4', 'prop', 'Pry bar', 'A long steel pry bar, sharpened at one end.'))
        saved['boxes'][0]['schedule']['props'] = ['e4']
        body = {'timeline': json.dumps(saved), 'recipe': {'version': 2, 'adapter': 'pixels'}, 'workflow': {'api': {}}}
        row = next(r for r in reference_assets.catalog(saved, body) if r['key'] == 'entity:e4')
        body.update(asset_key=row['key'], input_fingerprint=row['input_fingerprint'], prompt=row['prompt'])
        with mock.patch.object(stills, '_pixel_references', return_value=[]),              mock.patch.object(image_recipe, 'prepare', return_value={'ok': True}) as prepared:
            reference_assets.prepare(body)
        prompt = prepared.call_args.args[2]['prompt']
        self.assertTrue(prompt.startswith('An object reference sheet'), prompt)
        self.assertIn('plain ivory background', prompt)
        self.assertIn('2 rows and 2 columns', prompt)
        for cell in ('row 1, column 1', 'row 1, column 2', 'row 2, column 1', 'row 2, column 2'):
            self.assertIn(cell, prompt)
        self.assertIn('Only the object appears', prompt)
        self.assertIn('A long steel pry bar, sharpened at one end.', prompt)


if __name__ == '__main__':
    unittest.main()
