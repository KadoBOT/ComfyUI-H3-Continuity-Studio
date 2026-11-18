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
    def test_the_default_layout_is_two_head_studies_and_four_whole_figures(self):
        prompt = planned_prompt('entity:e2')
        self.assertTrue(prompt.startswith('A 16:9 landscape character reference sheet for the character described below'), prompt)
        self.assertIn('plain ivory background', prompt)
        self.assertIn('two large head studies stacked', prompt)
        self.assertIn('four whole-figure studies', prompt)
        for column in ('Column 3, FRONT', 'Column 4, LEFT SIDE', 'Column 5, BACK', 'Column 6, RIGHT SIDE'):
            self.assertIn(column, prompt)
        self.assertIn('There is no text anywhere.', prompt)

    def test_the_description_goes_where_the_layout_puts_it(self):
        prompt = planned_prompt('entity:e2')
        self.assertIn('THE CHARACTER\nA barrel-bodied grazer with long horns.\n\nLEFT THIRD, TOP HALF', prompt)
        self.assertEqual(prompt.count('A barrel-bodied grazer with long horns.'), 1)
        self.assertNotIn('{description}', prompt)
        self.assertNotIn('{look}', prompt)

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

    def test_the_creature_layout_is_one_head_and_a_two_by_two_of_headless_body_views(self):
        saved = with_overrides('entity:e2', {'layout': {'choice': 'creature'}})
        prompt = planned('entity:e2', saved=saved)['prompt']
        self.assertTrue(prompt.startswith('A 16:9 landscape creature reference sheet'), prompt)
        self.assertIn('2 rows and 2 columns', prompt)
        for view in ('Row 1, column 1: left side', 'Row 1, column 2: right side', 'Row 2, column 1: back',
                     'Row 2, column 2: top-down'):
            self.assertIn(view, prompt)
        self.assertIn('THE CREATURE\nA barrel-bodied grazer with long horns.\n', prompt)
        for human in (' arms', 'collarbone', 'five fingers', 'outfit', 'clothing'):
            self.assertNotIn(human, prompt)

    def test_a_layout_of_your_own_replaces_the_template(self):
        saved = with_overrides('entity:e2', {'layout': {'choice': 'custom', 'text': 'A turnaround on ivory.'}})
        prompt = planned('entity:e2', saved=saved)['prompt']
        self.assertTrue(prompt.startswith('A turnaround on ivory.\nA barrel-bodied grazer with long horns.'), prompt)
        self.assertNotIn('reference sheet', prompt)
        placed = with_overrides('entity:e2', {'layout': {'choice': 'custom', 'text': 'Sheet of {description} on ivory.'}})
        self.assertTrue(planned('entity:e2', saved=placed)['prompt'].startswith('Sheet of A barrel-bodied grazer with long horns. on ivory.'))
        empty = with_overrides('entity:e2', {'layout': {'choice': 'custom'}})
        self.assertTrue(planned('entity:e2', saved=empty)['prompt'].startswith('A barrel-bodied grazer with long horns.'))

    def test_every_cast_layout_is_sixteen_by_nine(self):
        for choice in ('human', 'creature', 'custom'):
            saved = with_overrides('entity:e2', {'layout': {'choice': choice}})
            self.assertEqual(planned('entity:e2', saved=saved, recipe=SIZED).get('size'), {'width': 2048, 'height': 1152}, choice)


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
        layout = parts[0]['text'].replace('{description}', 'A barrel-bodied grazer with long horns.')
        self.assertEqual(prompt, '\n'.join([layout, parts[1]['text']]))

    def test_a_cast_layout_offers_the_human_creature_and_custom_choices(self):
        layout = row_of(document(), 'entity:e2')['prompt_parts'][0]
        self.assertEqual((layout['choice'], layout['choices']), ('human', ['human', 'creature', 'custom']))
        self.assertNotIn('choices', row_of(document(), 'entity:e3')['prompt_parts'][0])
        saved = with_overrides('entity:e2', {'layout': {'choice': 'creature'}})
        self.assertEqual(row_of(saved, 'entity:e2')['prompt_parts'][0]['choice'], 'creature')
        self.assertFalse(row_of(saved, 'entity:e2')['prompt_parts'][0]['edited'])

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
        for bad in ({'nope': {'enabled': False}}, {'style': {'enabled': 'no'}}, {'style': {'text': 3}}, {'style': 'x'},
                    {'layout': {'choice': 'dragon'}}, {'style': {'choice': 'human'}}):
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
