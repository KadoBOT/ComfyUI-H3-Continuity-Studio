import unittest

import torch
from tests.continuity_support import enable_comfy_cpu

enable_comfy_cpu()
from comfy.nested_tensor import NestedTensor
from h3_continuity import latents, nodes, protection, timing


def carried(context=39, *, feather=0, dtype=torch.float32, batch=1, ending=False):
    tokens = timing.tokens_for_frames(context + 85)
    video = torch.randn(batch, 24, tokens, 4, 4, dtype=dtype)
    audio = torch.randn(batch, 32, 2, timing.ticks_for_frames(context + 85), dtype=dtype)
    source = torch.randn(1, 24, timing.tokens_for_frames(192), 4, 4, dtype=dtype)
    sound = torch.randn(1, 32, 2, 320, dtype=dtype)
    latent, original, original_audio, ticks = latents.build_continuation(
        dict(samples=NestedTensor((video, audio))), source, sound, context, True, audio_feather=feather)
    plan = nodes.SegmentPlan(None, context, ticks, context + 85, (4,4), original, original_audio,
                             protection_source=dict(status='ready', context_noise=False))
    if ending:
        latent, plan.ending_video, plan.ending_audio = latents.build_ending(latent, source, sound, 22, False, context)
    return latent, plan, source[:, :, :1]


class ProtectionLatentTest(unittest.TestCase):
    def test_front_anchor_and_linear_mask_preserve_free_video_and_audio(self):
        for context in (22, 39, 90, 141):
            with self.subTest(context=context):
                latent, plan, front = carried(context, feather=4)
                old = [t.clone() for k in ('samples','noise_mask') for t in latent[k].tensors]
                prepared, originals = protection.prepare_latent(latent, plan, front)
                video, audio = prepared['samples'].tensors
                mask, sound_mask = prepared['noise_mask'].tensors
                count = timing.tokens_for_frames(context)
                self.assertTrue(torch.equal(video[:,:,:1], front))
                self.assertTrue(torch.equal(originals, latent['samples'].tensors[0][:,:,:count]))
                self.assertTrue(torch.equal(video[:,:,1:], latent['samples'].tensors[0][:,:,1:]))
                self.assertEqual(mask[:,:,:1].sum().item(), 0)
                self.assertTrue(torch.equal(mask[0,0,1:count,0,0], torch.linspace(1,0,count-1)))
                self.assertTrue(bool((mask[:,:,count:] == 1).all()))
                self.assertTrue(torch.equal(audio, latent['samples'].tensors[1]))
                self.assertTrue(torch.equal(sound_mask, latent['noise_mask'].tensors[1]))
                for expected, actual in zip(old, [t for k in ('samples','noise_mask') for t in latent[k].tensors]):
                    self.assertTrue(torch.equal(expected, actual))

    def test_rejects_old_pixel_noise_and_incompatible_masks(self):
        latent, plan, front = carried()
        plan.protection_source['context_noise'] = True
        with self.assertRaisesRegex(ValueError, 'Context noise'):
            protection.prepare_latent(latent, plan, front)
        plan.protection_source['context_noise'] = False
        vm, am = latent['noise_mask'].tensors
        vm[:,:,15] = .5
        with self.assertRaisesRegex(ValueError, 'mask'):
            protection.prepare_latent(latent, plan, front)
        latent.pop('noise_mask')
        with self.assertRaisesRegex(ValueError, 'mask'):
            protection.prepare_latent(latent, plan, front)

    def test_full_expanded_masks_batch_dtype_and_protected_ending(self):
        for dtype in (torch.float32, torch.bfloat16):
            latent, plan, front = carried(dtype=dtype, batch=2, ending=True)
            vm, am = latent['noise_mask'].tensors
            latent['noise_mask'] = NestedTensor((vm.expand_as(latent['samples'].tensors[0]), am))
            prepared, originals = protection.prepare_latent(latent, plan, front)
            video = prepared['samples'].tensors[0]
            self.assertEqual(video.dtype, dtype)
            self.assertEqual(originals.shape[0], 2)
            self.assertTrue(torch.equal(video[:,:,0], front[:,:,0].expand(2,-1,-1,-1)))
            self.assertTrue(torch.equal(prepared['noise_mask'].tensors[0][:,:,-7:], vm[:,:,-7:].expand(2,24,-1,-1,-1)))

    def test_wrong_anchor_shape_and_wrong_context_fail(self):
        latent, plan, front = carried()
        with self.assertRaisesRegex(ValueError, 'anchor'):
            protection.prepare_latent(latent, plan, front[:,:,:,:,:2])
        plan.context_frames = 123
        with self.assertRaises(ValueError):
            protection.prepare_latent(latent, plan, front)


if __name__ == '__main__':
    unittest.main()
