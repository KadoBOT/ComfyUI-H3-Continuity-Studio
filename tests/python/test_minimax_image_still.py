import asyncio
import unittest
from unittest import mock

import torch

from tests.continuity_support import enable_comfy_cpu
enable_comfy_cpu()

from h3_continuity import minimax_image_nodes as image, image_recipe, story_context
from tests.python.test_ph3_image_recipe import recipe, reference

FILES = {'diffusion_models': ['minimax_h3_image_pruned_w4a8.safetensors', 'p-h3-image_int8_convrot.safetensors'],
         'text_encoders': ['qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors', 'p-h3-image_text_encoder_bf16.safetensors'],
         'vae': ['minimax_h3_image_vae_fp16.safetensors', 'minimax_h3_video_vae_fp16.safetensors']}
ARGS = dict(diffusion_model=FILES['diffusion_models'][0], text_encoder=FILES['text_encoders'][0],
            vae=FILES['vae'][0], prompt='A kitchen at dawn.', instruction='', seed=42, width=2048, height=2048)


class MiniMaxImageTest(unittest.TestCase):
    def setUp(self):
        self.files = mock.patch('folder_paths.get_filename_list', lambda folder: FILES.get(folder, []))
        self.files.start()
        self.addCleanup(self.files.stop)

    def test_schema_filters_image_weights_and_keeps_shared_video_encoder(self):
        schema = {item.id: item.options for item in image.H3C_MiniMaxH3ImageStill.define_schema().inputs if hasattr(item, 'options')}
        for component, folder in [('diffusion_model', 'diffusion_models'), ('text_encoder', 'text_encoders'), ('vae', 'vae')]:
            self.assertEqual(schema[component], [FILES[folder][0]])
        from h3_continuity.extension import H3ContinuityExtension
        self.assertIn(image.H3C_MiniMaxH3ImageStill, asyncio.run(H3ContinuityExtension().get_node_list()))

    def test_native_six_step_graph_and_reference_order(self):
        a, b = torch.zeros(1, 8, 8, 3), torch.ones(1, 8, 8, 3)
        with mock.patch.dict('nodes.NODE_CLASS_MAPPINGS', {'MiniMaxH3ImageConditioning': object}):
            result = image.H3C_MiniMaxH3ImageStill.execute(**{**ARGS, 'instruction': 'Film still.'}, images={'image_2': b, 'image_1': a})
        graph = result.expand
        by_class = {node['class_type']: node['inputs'] for node in graph.values()}
        sampler = by_class['KSampler']
        self.assertEqual((sampler['steps'], sampler['cfg'], sampler['sampler_name'], sampler['scheduler']), (6, 1, 'euler', 'simple'))
        cond = by_class['MiniMaxH3ImageConditioning']
        self.assertEqual(cond['prompt'], 'A kitchen at dawn.\n\nFilm still.')
        self.assertEqual([key for key in cond if key.startswith('images.')], ['images.image_1', 'images.image_2'])
        self.assertIs(cond['images.image_1'], a)
        self.assertIn('vae', cond)
        self.assertEqual(result.result[1]['label'], 'MiniMax H3 Image')

    def test_megapixels_keep_the_width_height_ratio_and_set_the_area(self):
        pixels = torch.zeros(1, 8, 8, 3)
        cases = [(1152, 640, 20.0, (6016, 3328)), (1344, 768, 4.0, (2656, 1504)), (2048, 2048, 0.0, (2048, 2048)),
                 (1000, 563, 16.0, (5344, 3008))]
        for width, height, megapixels, expected in cases:
            with self.subTest(width=width, height=height, megapixels=megapixels), \
                 mock.patch.dict('nodes.NODE_CLASS_MAPPINGS', {'MiniMaxH3ImageConditioning': object}):
                graph = image.H3C_MiniMaxH3ImageStill.execute(**{**ARGS, 'width': width, 'height': height},
                                                              images={'image_1': pixels}, megapixels=megapixels).expand
            cond = next(node['inputs'] for node in graph.values() if node['class_type'] == 'MiniMaxH3ImageConditioning')
            self.assertEqual((cond['width'], cond['height']), expected)
        self.assertEqual(image.H3C_MiniMaxH3ImageStill.INPUT_TYPES()['optional']['megapixels'][0], 'FLOAT')
        with mock.patch.dict('nodes.NODE_CLASS_MAPPINGS', {'MiniMaxH3ImageConditioning': object}):
            with self.assertRaisesRegex(ValueError, 'side above 8192'):
                image.H3C_MiniMaxH3ImageStill.execute(**{**ARGS, 'width': 4096, 'height': 256}, megapixels=20.0)

    def test_lora_stack_is_an_optional_connection(self):
        schema = image.H3C_MiniMaxH3ImageStill.define_schema()
        socket = next((item for item in schema.inputs if item.id == 'lora_stack'), None)
        self.assertIsNotNone(socket)
        self.assertTrue(socket.optional)
        self.assertEqual(image.H3C_MiniMaxH3ImageStill.INPUT_TYPES()['optional']['lora_stack'][0], 'LORA_STACK')

    def test_loras_patch_model_and_clip_in_stack_order(self):
        with mock.patch.dict('nodes.NODE_CLASS_MAPPINGS', {'MiniMaxH3ImageConditioning': object}):
            graph = image.H3C_MiniMaxH3ImageStill.execute(**ARGS, lora_stack=[
                ('style.safetensors', 0.7, 0.2), ('detail.safetensors', -0.3, 0.0)]).expand
        loaders = [(key, node['inputs']) for key, node in graph.items() if node['class_type'] == 'LoraLoader']
        self.assertEqual(len(loaders), 2)
        (first_id, first), (second_id, second) = loaders
        by_type = {node['class_type']: key for key, node in graph.items()}
        self.assertEqual(first, {'model': [by_type['UNETLoader'], 0], 'clip': [by_type['CLIPLoader'], 0],
                                'lora_name': 'style.safetensors', 'strength_model': 0.7, 'strength_clip': 0.2})
        self.assertEqual(second, {'model': [first_id, 0], 'clip': [first_id, 1],
                                 'lora_name': 'detail.safetensors', 'strength_model': -0.3, 'strength_clip': 0.0})
        self.assertEqual(graph[by_type['KSampler']]['inputs']['model'], [second_id, 0])
        self.assertEqual(graph[by_type['MiniMaxH3ImageConditioning']]['inputs']['clip'], [second_id, 1])

    def test_empty_or_disabled_stack_keeps_unpatched_model_and_clip(self):
        for stack in (None, [], [('None', 1.0, 1.0), ('', 1.0, 1.0), ('unused.safetensors', 0.0, 0.0)]):
            with self.subTest(stack=stack), mock.patch.dict('nodes.NODE_CLASS_MAPPINGS', {'MiniMaxH3ImageConditioning': object}):
                graph = image.H3C_MiniMaxH3ImageStill.execute(**ARGS, lora_stack=stack).expand
                by_type = {node['class_type']: key for key, node in graph.items()}
                self.assertNotIn('LoraLoader', by_type)
                self.assertEqual(graph[by_type['KSampler']]['inputs']['model'], [by_type['UNETLoader'], 0])
                self.assertEqual(graph[by_type['MiniMaxH3ImageConditioning']]['inputs']['clip'], [by_type['CLIPLoader'], 0])

    def test_studio_candidates_keep_connected_stack_and_ancestors(self):
        workflow = {'api': {
            '5': {'class_type': 'H3C_MiniMaxH3ImageStill', 'inputs': {**ARGS, 'lora_stack': ['stack', 0]}},
            'stack': {'class_type': 'easy loraStack', 'inputs': {'optional_lora_stack': ['base', 0]}},
            'base': {'class_type': 'easy loraStack', 'inputs': {'lora_1_name': 'style.safetensors'}},
        }}
        with mock.patch.dict('nodes.NODE_CLASS_MAPPINGS', {'H3C_MiniMaxH3ImageStill': image.H3C_MiniMaxH3ImageStill}):
            result = image_recipe.prepare({**recipe(), 'label': 'MiniMax H3 Image'}, workflow, {'prompt': 'A room.'}, [])
        self.assertEqual(result['prompt']['5']['inputs']['lora_stack'], ['stack', 0])
        for node_id in ('stack', 'base'):
            self.assertEqual(result['prompt'][node_id], workflow['api'][node_id])

    def test_unavailable_core_and_wrong_vae_fail_before_loading(self):
        with mock.patch('nodes.NODE_CLASS_MAPPINGS', {}):
            with self.assertRaisesRegex(ValueError, 'Update ComfyUI.*MiniMaxH3ImageConditioning'):
                image.H3C_MiniMaxH3ImageStill.execute(**ARGS)
        with mock.patch.dict('nodes.NODE_CLASS_MAPPINGS', {'MiniMaxH3ImageConditioning': object}):
            for overrides, message in [({'vae': FILES['vae'][1]}, 'VAE'), ({'prompt': ' '}, 'prompt'),
                                       ({'width': 1000}, 'multiple of 32')]:
                with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, message):
                    image.H3C_MiniMaxH3ImageStill.execute(**{**ARGS, **overrides})

    def test_scene_is_first_and_references_guide_a_new_image_at_the_requested_size(self):
        workflow = {'api': {'5': {'class_type': 'H3C_MiniMaxH3ImageStill', 'inputs': {**ARGS}}}}
        captured = {**recipe(), 'label': 'MiniMax H3 Image'}
        refs = [reference('image20', ['identity: Courier'], 'a' * 64), reference('image21', ['location: Hall'], 'b' * 64)]
        with mock.patch.dict('nodes.NODE_CLASS_MAPPINGS', {'H3C_MiniMaxH3ImageStill': image.H3C_MiniMaxH3ImageStill}):
            result = image_recipe.prepare(captured, workflow, {'prompt': '@image20 in @image21.'}, refs)
        self.assertEqual(result['provenance']['references'][0]['slot'], 'image21')
        self.assertEqual(set(result['prompt']['h3c_still_source_0']['inputs']), {'source'})
        self.assertEqual(result['prompt']['5']['inputs']['width'], 2048)
        self.assertNotIn('h3c_ph3_size', result['prompt'])
        prompt = result['prompt']['5']['inputs']['prompt']
        self.assertIn('<Picture 2>', prompt)
        self.assertTrue(prompt.startswith('The target image is a new still'))
        self.assertNotIn('Edit <Picture', prompt)
        self.assertNotIn('canvas', prompt)
        self.assertIn('grid', prompt)
        api = {**workflow['api'], '1': {'class_type': 'H3C_Timeline', 'inputs': {'still_recipe': ['5', 1]}}}
        self.assertEqual(story_context.still_model_for(api, '1'), 'MiniMax H3 Image')

    def test_real_scheduler_keeps_video_lazy_and_expands_a_still_on_demand(self):
        from tests.python.test_ph3_image_lazy import Timeline, Preview, stand_in, stand_ins, execute, RAN, SEEN
        pixels = torch.ones(1, 8, 8, 3)
        core = {**stand_ins(), 'H3C_MiniMaxH3ImageStill': image.H3C_MiniMaxH3ImageStill,
                'PH3TestTimeline': Timeline, 'PH3TestPreview': Preview,
                'MiniMaxH3ImageConditioning': stand_in('conditioning', ('cond', 'latent'), ('CONDITIONING', 'LATENT'),
                    ['clip', 'vae', 'prompt', 'width', 'height']),
                'ConditioningZeroOut': stand_in('zero', ('negative',), ('CONDITIONING',), ['conditioning']),
                'KSampler': stand_in('sampler', ('sampled',), ('LATENT',),
                    ['model', 'seed', 'steps', 'cfg', 'sampler_name', 'scheduler', 'positive', 'negative', 'latent_image', 'denoise']),
                'VAEDecode': stand_in('decode', (pixels,), ('IMAGE',), ['samples', 'vae'])}
        generator = {'class_type': 'H3C_MiniMaxH3ImageStill', 'inputs': {**ARGS}}
        with mock.patch.dict('nodes.NODE_CLASS_MAPPINGS', core):
            RAN.clear()
            self.assertTrue(execute({'1': generator, '2': {'class_type': 'PH3TestTimeline',
                                   'inputs': {'still_recipe': ['1', 1]}}}, ['2']))
            self.assertEqual(RAN, ['timeline'])
            self.assertTrue(execute({'1': generator, '2': {'class_type': 'PH3TestPreview',
                                   'inputs': {'image': ['1', 0]}}}, ['2']))
            self.assertIn('sampler', RAN)
            self.assertEqual(SEEN['sampler']['steps'], 6)
            self.assertEqual(tuple(SEEN['preview'].shape), (1, 8, 8, 3))


if __name__ == '__main__':
    unittest.main()
