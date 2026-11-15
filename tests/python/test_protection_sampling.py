import copy
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
        conditions = core._denoise_mask_values(denoise_mask, latent_shapes)
        self.initial_mask = conditions['denoise_mask'].clone()
        fn = self.model_options.get('model_function_wrapper')
        x = core.process_latent_in(latent_image)
        def predict(xx, tt, **c):
            video, audio = comfy.utils.unpack_latents(xx, c['latent_shapes'])
            self.calls.append((float(tt[0]), tuple(video.shape), c['denoise_mask'].clone(), audio.clone()))
            return xx.clone()
        for i, sigma in enumerate(sigmas[:-1]):
            c = dict(conditions, latent_shapes=latent_shapes, transformer_options={'sample_sigmas':sigmas})
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


def run(model, latent, *, steps=8, callback=None, fail=False, extra_sigmas=(), cfg_batch=False):
    guider = CpuGuider(model)
    guider.fail = fail
    guider.extra_sigmas = extra_sigmas
    guider.cfg_batch = cfg_batch
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

    def test_capstone_enters_last_quarter_once_per_model_call(self):
        for steps in (4,8,12):
            _,model,prepared,segment,original,receipt=self.setup_run()
            extra=[(0,.99),(math.ceil(.75*steps)-1,float(1-(math.ceil(.75*steps)-.1)/steps))]
            with mock.patch.object(protection,'_current_source'):
                (_, _),guider=run(model,prepared,steps=steps,extra_sigmas=extra)
            threshold=float(torch.linspace(1,0,steps+1)[math.ceil(.75*steps)])
            for sigma,shape,mask,audio in guider.calls:
                appended=sigma <= threshold
                self.assertEqual(shape[2],37+appended)
                self.assertEqual(mask.shape[2],37+appended)
                if appended:self.assertEqual(mask[:,:,-1].sum().item(),0)
            self.assertEqual(receipt.descriptor['late_start_step'],math.ceil(.75*steps))

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

    def test_short_schedule_has_at_least_one_late_step(self):
        for steps in (1,2,3):
            _,model,prepared,segment,original,receipt=self.setup_run()
            with mock.patch.object(protection,'_current_source'):
                _,guider=run(model,prepared,steps=steps)
            self.assertTrue(any(shape[2]==38 for _,shape,_,_ in guider.calls))

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


if __name__=='__main__':unittest.main()
