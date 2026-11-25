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
    """Run the real core pack/mask/wrapper/callback dispatch; only weight evaluation is synthetic."""
    def __init__(self, model):
        super().__init__(model)
        self.calls = []
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
            if self.fail:
                raise RuntimeError('sampler failed')
            if callback:
                callback(i, x + 9, x, len(sigmas)-1)
        return core.process_latent_out(x+5)


def run(model, latent, *, steps=8, callback=None, fail=False, extra_sigmas=(), cfg_batch=False, payload=None):
    guider = CpuGuider(model)
    guider.fail = fail
    guider.extra_sigmas = extra_sigmas
    guider.cfg_batch = cfg_batch
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

    def test_video_memory_refs_stabilize_while_keyframes_and_images_stay_untouched(self):
        latent, segment, front = carried()
        prepared, originals = protection.prepare_latent(latent, segment, front)
        anchor = torch.randn(1, 24, 12, 4, 4) * 0.4 + 0.5
        kf_t = torch.randn(1, 24, 1, 4, 4)
        img_t = torch.randn(1, 24, 1, 4, 4)
        vid_t = torch.randn(1, 24, 5, 4, 4) * 2.0 - 1.5
        va_t = torch.randn(1, 24, 5, 4, 4) * 2.0 - 1.5
        payload = {
            'keyframes': [{'latent': kf_t}],
            'refs': [{'kind': 'image', 'latent': img_t}, {'kind': 'video', 'latent': vid_t}, {'kind': 'video_audio', 'latent': va_t}],
            'cond_video_latents': [kf_t, img_t, vid_t, va_t],
        }
        base = patcher()
        with mock.patch.object(protection, '_current_source'):
            model, receipt = protection.patch_model(
                base, prepared, segment, originals, front, dict(method=protection.METHOD, source_stamp=[1,2]),
                anchor_video=anchor, anchor_offset=0, strength=0.70, mode='full')
            _, guider = run(model, prepared, steps=2, payload=payload)
        seen = guider.seen_payloads[0]['cond_video_latents']
        self.assertTrue(torch.equal(seen[0], kf_t))
        self.assertTrue(torch.equal(seen[1], img_t))
        self.assertFalse(torch.equal(seen[2], vid_t))
        self.assertFalse(torch.equal(seen[3], va_t))
        self.assertLess((seen[2].mean() - anchor.mean()).abs().item(), (vid_t.mean() - anchor.mean()).abs().item())

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
