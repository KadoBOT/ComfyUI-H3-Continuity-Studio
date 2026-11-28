import math
import types
import unittest
from unittest import mock

import torch
from tests.continuity_support import enable_comfy_cpu

enable_comfy_cpu()
import comfy.latent_formats
import comfy.model_base
import comfy.model_patcher
import comfy.patcher_extension as pe
import comfy.samplers
import comfy.utils
from comfy.nested_tensor import NestedTensor
from comfy_extras.nodes_custom_sampler import SamplerCustomAdvanced
from h3_continuity import disk_cache, protection
from tests.python.test_protection_latent import carried


def patcher():
    core = comfy.model_base.MiniMaxH3.__new__(comfy.model_base.MiniMaxH3)
    torch.nn.Module.__init__(core)
    core.diffusion_model = types.SimpleNamespace(patch_size=(1,2,2))
    core.latent_format = comfy.latent_formats.MiniMaxH3AV()
    core.model_sampling = types.SimpleNamespace(audio_scale=3.)
    core.latent_shapes = None
    return comfy.model_patcher.ModelPatcher(core, torch.device('cpu'), torch.device('cpu'))


class CpuGuider(comfy.samplers.CFGGuider):
    """Run the real core pack/mask/wrapper/post-cfg/callback dispatch; only weight evaluation is synthetic."""
    def __init__(self, model):
        super().__init__(model)
        self.calls = []
        self.denoised_outputs = []
        self.raw_predictions = []
        self.fail = False
        self.extra_sigmas = []
        self.cfg_batch = False

    def outer_sample(self, noise, latent_image, sampler, sigmas, denoise_mask=None, callback=None,
                     disable_pbar=False, seed=None, latent_shapes=None):
        core = self.model_patcher.model
        core.latent_shapes = latent_shapes
        conditions = core._denoise_mask_values(denoise_mask, latent_shapes) if denoise_mask is not None else {}
        self.initial_mask = conditions['denoise_mask'].clone() if 'denoise_mask' in conditions else None
        fn = self.model_options.get('model_function_wrapper')
        x = core.process_latent_in(latent_image)
        def predict(xx, tt, **c):
            video, audio = comfy.utils.unpack_latents(xx, c['latent_shapes'])
            mask = c['denoise_mask'].clone() if c.get('denoise_mask') is not None else None
            payload = c.get('minimax_payload')
            if payload and hasattr(self, 'seen_payloads'):
                self.seen_payloads.append(payload)
            self.calls.append((float(tt[0]), tuple(video.shape), mask, audio.clone()))
            if hasattr(self, 'custom_predict'):
                return self.custom_predict(xx, tt, **c)
            return xx.clone()
        for i, sigma in enumerate(sigmas[:-1]):
            c = dict(conditions, latent_shapes=latent_shapes, transformer_options={'sample_sigmas':sigmas})
            if hasattr(self, 'extra_payload'):
                c['minimax_payload'] = self.extra_payload
            for s in (sigma, sigma, *[v for index,v in self.extra_sigmas if index == i]):
                xx = torch.cat((x,x),dim=0) if self.cfg_batch else x
                prediction = fn(predict,dict(input=xx,timestep=torch.full((xx.shape[0],),float(s)),c=c,
                                           cond_or_uncond=[0,1] if self.cfg_batch else [0]))
                assert prediction.shape == xx.shape
                self.raw_predictions.append(prediction.clone())
                if self.cfg_batch:
                    cond_p, uncond_p = prediction.chunk(2, dim=0)
                else:
                    cond_p, uncond_p = prediction, torch.zeros_like(prediction)
                denoised = comfy.samplers.cfg_function(
                    core, cond_p, uncond_p, self.cfg, x,
                    torch.full((x.shape[0],), float(s)), model_options=self.model_options)
                assert denoised.shape == x.shape
                self.denoised_outputs.append(denoised.clone())
            if self.fail:
                raise RuntimeError('sampler failed')
            if callback:
                callback(i, x + 9, x, len(sigmas)-1)
        return core.process_latent_out(x+5)


def run(model, latent, *, steps=8, callback=None, fail=False, extra_sigmas=(), cfg_batch=False,
        cfg=1.0, payload=None, custom_predict=None):
    guider = CpuGuider(model)
    guider.fail = fail
    guider.extra_sigmas = extra_sigmas
    guider.cfg_batch = cfg_batch
    guider.set_cfg(cfg)
    if custom_predict is not None:
        guider.custom_predict = custom_predict
    if payload is not None:
        guider.extra_payload = payload
        guider.seen_payloads = []
    noise = types.SimpleNamespace(seed=1, generate_noise=lambda latent: NestedTensor([torch.zeros_like(t) for t in latent['samples'].tensors]))
    def prepare_callback(model, steps, output):
        def capture(i, x0, x, total):
            output['x0'] = x0
            if callback:
                callback(i, x0, x, total)
        return capture
    with mock.patch('latent_preview.prepare_callback', side_effect=prepare_callback):
        result = SamplerCustomAdvanced.execute(noise, guider, object(), torch.linspace(1,0,steps+1), latent)
    return result.args, guider


class ProtectionSamplingTest(unittest.TestCase):
    def setup_run(self, *, capstone=True, ending=False):
        latent, segment, front = carried(ending=ending)
        prepared, originals = protection.prepare_latent(latent, segment, front)
        base = patcher()
        descriptor = dict(method=protection.METHOD, source_stamp=[1,2])
        with mock.patch.object(protection, '_current_source'):
            model, receipt = protection.patch_model(base, prepared, segment, originals,
                                                    front if capstone else None, descriptor)
        return base, model, prepared, segment, originals, receipt

    def test_normal_and_denoised_outputs_restore_every_carried_slot(self):
        base, model, prepared, segment, original, receipt = self.setup_run()
        callbacks=[]
        with mock.patch.object(protection, '_current_source'):
            (normal, denoised), guider = run(model, prepared, callback=lambda *a:callbacks.append(a))
        self.assertEqual(len(callbacks),8)
        for output in (normal, denoised):
            self.assertTrue(torch.equal(output['samples'].tensors[0][:,:,:12], original))
            self.assertEqual(output['samples'].tensors[0].shape, prepared['samples'].tensors[0].shape)
            self.assertIn(disk_cache.content_digest(output['samples']), receipt.accepted)
        self.assertFalse(torch.equal(normal['samples'].tensors[0][:,:,12:], denoised['samples'].tensors[0][:,:,12:]))
        self.assertNotIn('model_function_wrapper',base.model_options)
        self.assertEqual(base.wrappers,{})
        self.assertTrue(receipt.complete)

    def test_callback_uses_internal_coordinates_and_preserves_previews(self):
        _,model,prepared,segment,original,receipt=self.setup_run(capstone=False)
        model.model.latent_format.scale_factor=2.
        with mock.patch.object(protection,'_current_source'):
            (normal,denoised),guider=run(model,prepared)
        for output in (normal,denoised):
            self.assertTrue(torch.equal(output['samples'].tensors[0][:,:,:12],original))
        # Free audio remains the sampler's prediction, including native AV scaling.
        expected=model.model.process_latent_out(model.model.process_latent_in(prepared['samples'])+9).tensors[1]
        self.assertTrue(torch.equal(denoised['samples'].tensors[1][...,segment.carried_ticks:],expected[...,segment.carried_ticks:]))

    def test_phase_stabilization_clamps_contrast_hf_and_tapers_over_schedule(self):
        self.assertAlmostEqual(protection._schedule_weight(0.70, 0.0), 0.70)
        self.assertAlmostEqual(protection._schedule_weight(0.70, 0.75), 0.70)
        self.assertAlmostEqual(protection._schedule_weight(0.70, 1.0), 0.35)
        torch.manual_seed(7)
        anchor = torch.randn(1, 24, 15, 6, 6) * 0.5 + 0.25
        # Phase 0 (t%5==0) has distinct mean/std from phase 1 (t%5!=0)
        for t in range(15):
            if t % 5 == 0:
                anchor[:, :, t] = anchor[:, :, t] * 0.6 - 0.5
        stats = protection.compute_phase_stats(anchor[:, :, 12:], abs_offset=12)
        gen = torch.randn(1, 24, 8, 6, 6) * 1.4 - 0.8
        # Inject checkerboard HF spike into first 12 channels
        gen[:, :12, :, ::2, ::2] += 1.5
        full_out = protection._stabilize_video(gen, stats, abs_offset=12, strength=1.0, match_mean=True)
        co_out = protection._stabilize_video(gen, stats, abs_offset=12, strength=1.0, match_mean=False)
        self.assertLess((full_out[:, :, 3].mean() - anchor[:, :, 0].mean()).abs().max().item(), 1.5)
        self.assertTrue(torch.allclose(co_out.mean(dim=(2,3,4)), gen.mean(dim=(2,3,4)), atol=1e-4))
        # Upper-clamped std: oversized channels are damped down, quiet channels are not boosted above anchor
        self.assertLess(full_out.std(dim=(2,3,4)).mean().item(), gen.std(dim=(2,3,4)).mean().item())
        quiet = torch.randn(1, 24, 8, 6, 6) * 0.1 + 0.25
        quiet_out = protection._stabilize_video(quiet, stats, abs_offset=12, strength=1.0, match_mean=False)
        self.assertTrue(torch.allclose(quiet_out, quiet, atol=1e-4))

    def test_video_memory_refs_stabilize_while_user_refs_keyframes_and_images_stay_untouched(self):
        torch.manual_seed(11)
        latent, segment, front = carried()
        prepared, originals = protection.prepare_latent(latent, segment, front)
        anchor = torch.randn(1, 24, 12, 4, 4) * 0.4 + 0.5
        kf_t = torch.randn(1, 24, 1, 4, 4)
        img_t = torch.randn(1, 24, 1, 4, 4)
        user_vid_t = torch.randn(1, 24, 5, 4, 4) * 2.0 - 1.5
        user_va_t = torch.randn(1, 24, 5, 4, 4) * 2.0 - 1.5
        mem_vid_t = torch.randn(1, 24, 5, 4, 4) * 2.0 - 1.5
        mem_va_t = torch.randn(1, 24, 5, 4, 4) * 2.0 - 1.5
        mem_short_t = torch.randn(1, 24, 2, 4, 4) * 2.0 - 1.5
        payload = {
            'keyframes': [{'latent': kf_t}],
            'refs': [
                {'kind': 'image', 'latent': img_t},
                {'kind': 'video', 'latent': user_vid_t},
                {'kind': 'video_audio', 'latent': user_va_t},
                {'kind': 'video', 'latent': mem_vid_t, 'h3c_memory': True},
                {'kind': 'video_audio', 'latent': mem_va_t, 'h3c_memory': True},
                {'kind': 'video', 'latent': mem_short_t, 'h3c_memory': True},
            ],
            'cond_video_latents': [kf_t, img_t, user_vid_t, user_va_t, mem_vid_t, mem_va_t, mem_short_t],
        }
        base = patcher()
        with mock.patch.object(protection, '_current_source'):
            model, receipt = protection.patch_model(
                base, prepared, segment, originals, front, dict(method=protection.METHOD, source_stamp=[1,2]),
                anchor_video=anchor, anchor_offset=0, strength=0.70, mode='full')
            _, guider = run(model, prepared, steps=2, payload=payload)
        seen = guider.seen_payloads[0]['cond_video_latents']
        # Keyframes, images, and user-supplied @video* refs (without h3c_memory) stay untouched.
        self.assertTrue(torch.equal(seen[0], kf_t))
        self.assertTrue(torch.equal(seen[1], img_t))
        self.assertTrue(torch.equal(seen[2], user_vid_t))
        self.assertTrue(torch.equal(seen[3], user_va_t))
        # H3 Continuity visual-memory refs stabilize toward the anchor.
        self.assertFalse(torch.equal(seen[4], mem_vid_t))
        self.assertFalse(torch.equal(seen[5], mem_va_t))
        self.assertFalse(torch.equal(seen[6], mem_short_t))
        self.assertLess((seen[4].mean() - anchor.mean()).abs().item(), (mem_vid_t.mean() - anchor.mean()).abs().item())
        # Tiny 2-token memory windows keep std damped but cap mean forcing (never 100% forced to anchor mean).
        self.assertLess(seen[6].std().item(), mem_short_t.std().item())
        full_shift = (seen[4].mean() - mem_vid_t.mean()).abs().item()
        short_shift = (seen[6].mean() - mem_short_t.mean()).abs().item()
        self.assertLess(short_shift, full_shift * 0.5)
        self.assertGreater((seen[6].mean() - anchor.mean()).abs().item(), 0.5)

    def test_memory_references_tags_h3c_memory_blocks(self):
        from h3_continuity import conditioning
        class FakeVae:
            def decode(self, video):
                return torch.zeros(1, 17, 8, 8, 3)
        vid5 = torch.randn(1, 24, 5, 4, 4)
        vid2 = torch.randn(1, 24, 2, 4, 4)
        _, blocks = conditioning.memory_references(object(), FakeVae(), [vid5, vid2], memory_frames=(17, 5))
        self.assertEqual(len(blocks), 2)
        for blk, src in zip(blocks, (vid5, vid2)):
            self.assertIs(blk['h3c_memory'], True)
            self.assertEqual(blk['kind'], 'video')
            self.assertIs(blk['latent'], src)

    def test_sawtooth_snap_eliminated_and_feathered_on_same_shot_continuation(self):
        torch.manual_seed(21)
        # Clean scene anchor is bright (+0.8), carried tail drifted darker (-0.8): a 1.6 latent mean gap.
        anchor = torch.randn(1, 24, 15, 6, 6) * 0.35 + 0.8
        carried_tail = torch.randn(1, 24, 12, 6, 6) * 0.35 - 0.8
        stats = protection.compute_phase_stats(anchor, abs_offset=0)
        tail_stats = protection.compute_carried_tail_stats(carried_tail)
        # Case 1: DiT opens smoothly at carried tail mean (-0.8). Opening token must NOT snap toward +0.8!
        gen_smooth = torch.randn(1, 24, 14, 6, 6) * 0.35 - 0.8
        out_smooth = protection._stabilize_video(
            gen_smooth, stats, abs_offset=12, strength=0.70, mean_strength=0.70, match_mean=True,
            tail_stats=tail_stats, same_shot=True, seam_feather=protection.SEAM_FEATHER_TOKENS,
            seam_ramp=protection.SEAM_RAMP_TOKENS, local_mean=True,
            phase1_std_headroom=protection.PHASE1_STD_HEADROOM)
        tail_p1_mean = tail_stats[1][0].mean().item()
        anc_p1_mean = stats[1][0].mean().item()
        tok0_mean = out_smooth[:, :, 0].mean().item()
        tok_far_mean = out_smooth[:, :, 10].mean().item()
        # Opening token stays right at carried tail mean (eliminating the sawtooth snap).
        self.assertLess(abs(tok0_mean - tail_p1_mean), 0.12)
        # Downstream tokens feather gently toward anchor, soft-clamped by ROOT_PULL_MAX_STD * anc_std.
        self.assertGreater(tok_far_mean, tok0_mean)
        self.assertLess(abs(tok_far_mean - tail_p1_mean), 0.35 * protection.ROOT_PULL_MAX_STD * 1.5 + 0.15)
        self.assertLess(tok_far_mean, anc_p1_mean - 1.0)
        # Case 2: Raw DiT jumps +1.5 brighter at the opening seam; opening token is pulled back toward tail_mean.
        gen_jump = gen_smooth + 1.5
        out_jump = protection._stabilize_video(
            gen_jump, stats, abs_offset=12, strength=0.70, mean_strength=0.70, match_mean=True,
            tail_stats=tail_stats, same_shot=True, seam_feather=protection.SEAM_FEATHER_TOKENS,
            seam_ramp=protection.SEAM_RAMP_TOKENS, local_mean=True,
            phase1_std_headroom=protection.PHASE1_STD_HEADROOM)
        self.assertLess(abs(out_jump[:, :, 0].mean().item() - tail_p1_mean), 0.65)
        # Case 3: Contrast/std clamping ramps smoothly over seam_ramp tokens (idx=0 damped less than idx=2).
        gen_hot = torch.randn(1, 24, 10, 6, 6) * 2.0 - 0.8
        out_hot = protection._stabilize_video(
            gen_hot, stats, abs_offset=12, strength=1.0, mean_strength=1.0, match_mean=False,
            tail_stats=tail_stats, same_shot=True, seam_feather=8, seam_ramp=2, local_mean=True)
        std0 = out_hot[:, :, 0].std().item()
        std1 = out_hot[:, :, 1].std().item()
        std2 = out_hot[:, :, 2].std().item()
        self.assertGreater(std0, std1)
        self.assertGreater(std1, std2)

    def test_post_cut_continuation_anchors_mean_to_carried_tail_and_clamps_std_from_root(self):
        torch.manual_seed(22)
        root_anchor = torch.randn(1, 24, 15, 6, 6) * 0.3 + 1.0
        carried_tail = torch.randn(1, 24, 12, 6, 6) * 0.3 - 1.0
        stats = protection.compute_phase_stats(root_anchor, abs_offset=0)
        tail_stats = protection.compute_carried_tail_stats(carried_tail)
        gen = torch.randn(1, 24, 14, 6, 6) * 1.8 - 1.0
        gen[:, :12, :, ::2, ::2] += 1.2
        out = protection._stabilize_video(
            gen, stats, abs_offset=12, strength=0.85, mean_strength=0.85, match_mean=True,
            tail_stats=tail_stats, same_shot=False, seam_feather=8, seam_ramp=2, local_mean=True)
        tail_p1_mean = tail_stats[1][0].mean().item()
        # Even deep into the clip (idx=10), post-cut continuation mean stays pinned to carried tail, never pulled to +1.0.
        self.assertLess(abs(out[:, :, 0].mean().item() - tail_p1_mean), 0.18)
        self.assertLess(abs(out[:, :, 10].mean().item() - tail_p1_mean), 0.18)
        # Std and HF overshoot are still damped down toward root stats.
        self.assertLess(out[:, :, 4:].std().item(), gen[:, :, 4:].std().item() * 0.6)

    def test_intra_clip_pan_preserves_opening_seam_mean(self):
        torch.manual_seed(23)
        anchor = torch.randn(1, 24, 15, 6, 6) * 0.4
        carried_tail = torch.randn(1, 24, 12, 6, 6) * 0.4
        stats = protection.compute_phase_stats(anchor, abs_offset=0)
        tail_stats = protection.compute_carried_tail_stats(carried_tail)
        # Smooth brightening pan from 0.0 at idx=0 to +3.0 at idx=19.
        ramp = torch.linspace(0.0, 3.0, 20).view(1, 1, 20, 1, 1)
        gen = torch.randn(1, 24, 20, 6, 6) * 0.4 + ramp
        out_local = protection._stabilize_video(
            gen, stats, abs_offset=12, strength=0.70, mean_strength=0.70, match_mean=True,
            tail_stats=tail_stats, same_shot=True, seam_feather=8, seam_ramp=2, local_mean=True)
        out_global = protection._stabilize_video(
            gen, stats, abs_offset=12, strength=0.70, mean_strength=0.70, match_mean=True,
            tail_stats=tail_stats, same_shot=True, seam_feather=8, seam_ramp=2, local_mean=False)
        # Local temporal mean keeps idx=0 near 0.0 instead of shifting it backward to -1.0 like clip-wide mean.
        self.assertLess(abs(out_local[:, :, 0].mean().item()), 0.25)
        self.assertLess(out_global[:, :, 0].mean().item(), -0.6)

    def test_split_final_step_schedule_and_phase1_motion_headroom(self):
        self.assertAlmostEqual(protection._schedule_weight(0.70, 1.0), 0.35)
        self.assertAlmostEqual(protection._mean_schedule_weight(0.70, 0.0), 0.70)
        self.assertAlmostEqual(protection._mean_schedule_weight(0.70, 0.75), 0.70)
        self.assertAlmostEqual(protection._mean_schedule_weight(0.70, 1.0), 0.70 * protection.MEAN_TAIL_FLOOR)
        self.assertEqual(protection._schedule_weights(0.70, 1.0), (0.70 * protection.MEAN_TAIL_FLOOR, 0.35))

        # Construct smooth low-frequency spatial field (minimal HF) to isolate std headroom per phase.
        torch.manual_seed(24)
        grid_y = torch.linspace(-1.0, 1.0, 8).view(1, 1, 1, 8, 1)
        grid_x = torch.linspace(-1.0, 1.0, 8).view(1, 1, 1, 1, 8)
        base_field = (grid_y + grid_x).expand(1, 24, 10, 8, 8).clone()
        stats = protection.compute_phase_stats(base_field, abs_offset=0)
        # 1.10x std on both phases: below PHASE1_STD_HEADROOM (1.15) for phase-1, above 1.0 for phase-0.
        gen_motion = base_field * 1.10
        out = protection._stabilize_video(
            gen_motion, stats, abs_offset=0, strength=1.0, match_mean=False,
            phase1_std_headroom=protection.PHASE1_STD_HEADROOM)
        p0_ratio = (out[:, :, [0, 5]].std() / base_field[:, :, [0, 5]].std()).item()
        p1_ratio = (out[:, :, [1, 2, 3, 4, 6, 7, 8, 9]].std() / base_field[:, :, [1, 2, 3, 4, 6, 7, 8, 9]].std()).item()
        self.assertLess(p0_ratio, 1.03)
        self.assertGreater(p1_ratio, 1.08)

        # Even with phase-1 std headroom, checkerboard HF overshoot on phase-1 is still damped down.
        gen_hf = base_field.clone()
        gen_hf[:, :, [1, 2, 3, 4, 6, 7, 8, 9], ::2, ::2] += 0.35
        out_hf = protection._stabilize_video(
            gen_hf, stats, abs_offset=0, strength=1.0, match_mean=False,
            phase1_std_headroom=protection.PHASE1_STD_HEADROOM)
        _, raw_high = protection._split_hf(gen_hf[:, :, [1, 2, 3, 4, 6, 7, 8, 9]])
        _, out_high = protection._split_hf(out_hf[:, :, [1, 2, 3, 4, 6, 7, 8, 9]])
        self.assertLess(out_high.pow(2).mean().sqrt().item(), raw_high.pow(2).mean().sqrt().item() * 0.5)

    def test_post_cfg_stabilizes_cfg_gt_1_without_distorting_uncond_and_runs_at_cfg_1(self):
        torch.manual_seed(25)
        latent, segment, front = carried()
        prepared, originals = protection.prepare_latent(latent, segment, front)
        # Anchor and carried tail both sit near 0.0.
        anchor = torch.randn(1, 24, 15, 4, 4) * 0.3
        base = patcher()
        # Case A: BasicGuider (cfg=1.0, cfg_batch=False) runs post_cfg and never leaks options onto base.
        with mock.patch.object(protection, '_current_source'):
            model_cfg1, receipt_cfg1 = protection.patch_model(
                base, prepared, segment, originals, front, dict(method=protection.METHOD, source_stamp=[1, 2]),
                anchor_video=anchor, anchor_offset=0, strength=0.70, mode='full')
            outputs_cfg1, _ = run(model_cfg1, prepared, steps=4, cfg=1.0, cfg_batch=False)
        self.assertTrue(receipt_cfg1.complete)
        self.assertGreater(receipt_cfg1.post_cfg_calls, 0)
        self.assertNotIn('sampler_post_cfg_function', base.model_options)
        for out in outputs_cfg1:
            self.assertTrue(torch.equal(out['samples'].tensors[0][:, :, :12], originals))

        # Case B: CFGGuider (cfg=4.0, cfg_batch=True) leaves raw uncond/cond untouched pre-CFG,
        # and stabilizes the post-CFG amplified denoised x0.
        def biased_predict(xx, tt, **c):
            v, a = comfy.utils.unpack_latents(xx, c['latent_shapes'])
            v_out = v.clone()
            v_out[0, :, 12:] = 2.0   # cond drifted bright
            v_out[1, :, 12:] = -0.5  # uncond sits at -0.5 -> raw CFG(4) = -0.5 + 4*(2.5) = +9.5
            return comfy.utils.pack_latents((v_out, a))[0]

        with mock.patch.object(protection, '_current_source'):
            model_cfg4, receipt_cfg4 = protection.patch_model(
                base, prepared, segment, originals, front, dict(method=protection.METHOD, source_stamp=[1, 2]),
                anchor_video=anchor, anchor_offset=0, strength=0.80, mode='full')
            outputs_cfg4, guider_cfg4 = run(
                model_cfg4, prepared, steps=4, cfg=4.0, cfg_batch=True, custom_predict=biased_predict)
        self.assertTrue(receipt_cfg4.complete)
        self.assertEqual(receipt_cfg4.post_cfg_calls, len(guider_cfg4.denoised_outputs))
        self.assertNotIn('sampler_post_cfg_function', base.model_options)
        # Pre-CFG raw predictions remain completely unmodified (uncond is NOT warped toward anchor).
        raw_v, _ = comfy.utils.unpack_latents(guider_cfg4.raw_predictions[-1], guider_cfg4.model_patcher.model.latent_shapes)
        self.assertAlmostEqual(raw_v[0, :, 12:].mean().item(), 2.0, places=4)
        self.assertAlmostEqual(raw_v[1, :, 12:].mean().item(), -0.5, places=4)
        # Post-CFG denoised x0 was stabilized strongly down from raw CFG +9.5 toward tail/anchor (~0.0).
        post_v, _ = comfy.utils.unpack_latents(guider_cfg4.denoised_outputs[-1], guider_cfg4.model_patcher.model.latent_shapes)
        self.assertLess(post_v[0, :, 12:].mean().item(), 4.0)
        for out in outputs_cfg4:
            self.assertTrue(torch.equal(out['samples'].tensors[0][:, :, :12], originals))

    def test_existing_wrappers_cfg_batches_and_audio_survive(self):
        latent,segment,front=carried()
        prepared,original=protection.prepare_latent(latent,segment,front)
        base=patcher(); seen=[]
        def prev(fn,args):
            seen.append(args['cond_or_uncond'])
            return fn(args['input'],args['timestep'],**args['c'])
        base.set_model_unet_function_wrapper(prev)
        base.add_wrapper_with_key(pe.WrappersMP.OUTER_SAMPLE,'existing',lambda executor,*a,**k:executor(*a,**k))
        with mock.patch.object(protection,'_current_source'):
            model,receipt=protection.patch_model(base,prepared,segment,original,front,dict(source_stamp=[1,2]))
            outputs,guider=run(model,prepared,cfg_batch=True)
        self.assertTrue(seen)
        self.assertTrue(all(x==[0,1] for x in seen))
        self.assertIs(base.model_options['model_function_wrapper'],prev)
        self.assertEqual(list(base.wrappers[pe.WrappersMP.OUTER_SAMPLE]),['existing'])
        self.assertTrue(all(shape[0]==2 for _,shape,_,_ in guider.calls))

    def test_reroll_failure_clears_previous_receipt(self):
        _,model,prepared,segment,original,receipt=self.setup_run()
        with mock.patch.object(protection,'_current_source'):
            run(model,prepared)
            self.assertTrue(receipt.complete)
            with self.assertRaisesRegex(RuntimeError,'sampler failed'):run(model,prepared,fail=True)
            self.assertFalse(receipt.complete)
            self.assertFalse(receipt.accepted)
            run(model,prepared)
            with self.assertRaisesRegex(RuntimeError,'preview failed'):
                run(model,prepared,callback=lambda *a:(_ for _ in ()).throw(RuntimeError('preview failed')))
            self.assertFalse(receipt.complete)

    def test_anchor_take_change_before_sampling_fails(self):
        _,model,prepared,segment,original,receipt=self.setup_run()
        with mock.patch.object(protection,'_current_source',side_effect=ValueError('source changed')):
            with self.assertRaisesRegex(ValueError,'source changed'):run(model,prepared)
        self.assertFalse(receipt.complete)

    def test_context_windows_are_rejected_before_sampling(self):
        latent,segment,front=carried(); prepared,original=protection.prepare_latent(latent,segment,front)
        model=patcher();model.model_options['context_handler']=object()
        with self.assertRaisesRegex(ValueError,'Context Windows'):
            protection.patch_model(model,prepared,segment,original,front,{})

    def test_preserves_frozen_ending_in_both_outputs(self):
        _,model,prepared,segment,original,receipt=self.setup_run(capstone=False,ending=True)
        with mock.patch.object(protection,'_current_source'):
            outputs,_=run(model,prepared)
        for output in outputs:
            self.assertTrue(torch.equal(output['samples'].tensors[0][:,:,-7:],segment.ending_video))

    def test_cut_memory_samples_without_noise_mask_and_records_descriptor(self):
        from h3_continuity import nodes, timing
        tokens = timing.tokens_for_frames(90)
        video = torch.randn(1, 24, tokens, 4, 4) * 1.5 - 1.2
        audio = torch.randn(1, 32, 2, timing.ticks_for_frames(90))
        latent = dict(samples=NestedTensor((video, audio)))
        plan = nodes.SegmentPlan(None, 0, 0, 90, (4, 4), None, None,
                                 protection_source=dict(status='ready', mode='cut_memory', context_noise=False))
        prepared, originals = protection.prepare_latent(latent, plan)
        anchor = torch.randn(1, 24, 15, 4, 4) * 0.4 + 0.5
        base = patcher()
        with mock.patch.object(protection, '_current_source'):
            model, receipt = protection.patch_model(
                base, prepared, plan, originals, None, dict(method=protection.METHOD, mode='cut_memory', source_stamp=[1,2]),
                anchor_video=anchor, anchor_offset=0, strength=0.70, mode='full')
            outputs, guider = run(model, prepared, steps=4)
        self.assertTrue(receipt.complete)
        self.assertEqual(receipt.descriptor['strength'], 0.70)
        self.assertEqual(receipt.descriptor['protection_mode'], 'full')
        self.assertTrue(all(mask is None for _, _, mask, _ in guider.calls))
        for output in outputs:
            self.assertIn(disk_cache.content_digest(output['samples']), receipt.accepted)
        guider = CpuGuider(model)
        bad_mask = NestedTensor([torch.ones_like(t) for t in prepared['samples'].tensors])
        with mock.patch.object(protection, '_current_source'):
            with self.assertRaisesRegex(ValueError, 'noise mask'):
                guider.sample(NestedTensor([torch.zeros_like(t) for t in prepared['samples'].tensors]),
                              prepared['samples'], object(), torch.linspace(1, 0, 5), denoise_mask=bad_mask)

    def test_windows_added_after_preparation_and_double_protection_fail(self):
        _,model,prepared,segment,original,receipt=self.setup_run()
        with self.assertRaisesRegex(ValueError,'already protected'):
            protection.patch_model(model,prepared,segment,original,None,{})
        model.model_options['context_handler']=object()
        guider=CpuGuider(model)
        with mock.patch.object(protection,'_current_source'):
            with self.assertRaisesRegex(ValueError,'Context Windows'):
                run(model,prepared)

    def test_invalid_schedules_reject_before_model_call_and_receipt_stays_empty(self):
        for sigmas in (torch.tensor([1.,0.5,.5,0]),torch.tensor([1.,.2]),torch.tensor([1.,float('nan'),0])):
            _,model,prepared,segment,original,receipt=self.setup_run()
            guider=CpuGuider(model)
            with mock.patch.object(protection,'_current_source'):
                with self.assertRaises(ValueError):
                    guider.sample(NestedTensor([torch.zeros_like(t) for t in prepared['samples'].tensors]),prepared['samples'],object(),sigmas,
                                  denoise_mask=prepared['noise_mask'])
            self.assertFalse(guider.calls)
            self.assertFalse(receipt.complete)

    def test_empty_schedule_is_not_an_executed_receipt(self):
        _,model,prepared,segment,original,receipt=self.setup_run()
        guider=CpuGuider(model)
        result=guider.sample(prepared['samples'],prepared['samples'],object(),torch.tensor([]))
        self.assertIs(result,prepared['samples'])
        self.assertFalse(receipt.complete)

    def test_changed_sampling_input_or_mask_fails_before_model_evaluation(self):
        for change in ('samples','noise_mask'):
            _,model,prepared,segment,original,receipt=self.setup_run()
            guider=CpuGuider(model)
            samples=prepared['samples']+1 if change=='samples' else prepared['samples']
            mask=NestedTensor([torch.zeros_like(t) for t in prepared['noise_mask'].tensors]) if change=='noise_mask' else prepared['noise_mask']
            with mock.patch.object(protection,'_current_source'):
                with self.assertRaisesRegex(ValueError,'prepared.*input|prepared.*mask'):
                    guider.sample(NestedTensor([torch.zeros_like(t) for t in samples.tensors]),samples,
                                  object(),torch.linspace(1,0,9),denoise_mask=mask)
            self.assertFalse(guider.calls)
            self.assertFalse(receipt.complete)

    def test_mixed_av_dtype_binding_matches_native_packing(self):
        latent,segment,front=carried(dtype=torch.bfloat16)
        latent['samples']=NestedTensor((latent['samples'].tensors[0],latent['samples'].tensors[1].float()))
        prepared,original=protection.prepare_latent(latent,segment,front)
        with mock.patch.object(protection,'_current_source'):
            model,receipt=protection.patch_model(patcher(),prepared,segment,original,front,dict(source_stamp=[1,2]))
            outputs,_=run(model,prepared)
        self.assertTrue(receipt.complete)
        for output in outputs:
            self.assertTrue(torch.equal(output['samples'].tensors[0][:,:,:12],original.float()))


if __name__=='__main__':unittest.main()
