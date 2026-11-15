"""Native H3 continuation protection; public techniques credited in the long-chain guide."""

import copy
import math
import threading
from dataclasses import replace

import torch

from . import latents, store, timeline, timing

METHOD = 'h3c-continuity-protection-v1'
WHO = 'H3 Continuity Protection'
RECEIPT_KEY = '_h3c_protection_receipt'


def source_info(parsed, index, entries, is_done, guides, ending):
    """Defer optional source failures: ordinary Timeline graphs need no protection anchor."""
    chain = timeline.continuation_chain(parsed, index)
    if len(chain) < 2:
        return dict(status='skip', reason='Fresh clip or track gap: no carried chain.')
    if any(parsed.boxes[i].plate_changes or (parsed.boxes[i].new_scene and not parsed.boxes[i].cut)
           for i in chain):
        return dict(status='skip', reason='Appearance change: protection resumes after the next fresh clip.')
    source = entries.get(chain[0] + 1)
    if (not source or store.box_of(source) != parsed.boxes[chain[0]].id
            or not is_done(chain[0], source)):
        return dict(status='error', reason='The chain source needs rendering before protection can run.')
    reason = ('A following clip holds the ending.' if ending else
              'An authored frame guide owns the target pose.' if guides or parsed.boxes[index].last else '')
    return dict(status='ready', source=copy.deepcopy(source), context_noise=parsed.context_noise,
                capstone_suppressed=reason)


def _identity(entry):
    return {key: entry.get(key) for key in ('index', 'stem', 'created', 'frames', 'context_frames', 'played',
                                           'latent_width', 'latent_height', 'timeline')}


def _current_source(segment, descriptor=None):
    info = segment.protection_source or {}
    if info.get('status') != 'ready':
        raise ValueError(f"{WHO}: source unavailable. {info.get('reason', 'Use a native Timeline segment.')}")
    expected = info['source']
    folder = segment.sequence.folder
    current = next((e for e in store.load_manifest(folder)['segments'] if store.box_of(e) == store.box_of(expected)), None)
    if current is None or _identity(current) != _identity(expected):
        raise ValueError(f'{WHO}: source take changed; prepare the Timeline again.')
    if (current.get('latent_height'), current.get('latent_width')) != tuple(d * 16 for d in segment.latent_size):
        raise ValueError(f'{WHO}: source resolution differs; render the chain at the same resolution.')
    try:
        stamp = store.latent_stamp(folder, current)
    except OSError as error:
        raise ValueError(f'{WHO}: source latent is unavailable: {error}') from None
    if descriptor is not None and stamp != descriptor['source_stamp']:
        raise ValueError(f'{WHO}: source latent changed; prepare the Timeline again.')
    return current, stamp


def load_anchors(segment):
    source, stamp = _current_source(segment)
    folder = segment.sequence.folder
    delivered = source.get('context_frames', 0) + store.played_frames(source)
    cap_slot = 5 * ((delivered - 1) // 17)
    front = store.load_video_window(folder, source, 0, 1)
    reason = segment.protection_source['capstone_suppressed']
    back = None if reason else store.load_video_window(folder, source, cap_slot, 1)
    shape = (1, 24, 1, *segment.latent_size)
    if any(tuple(v.shape) != shape or not v.is_floating_point() for v in (front, back) if v is not None):
        raise ValueError(f'{WHO}: source does not contain a compatible H3 video anchor.')
    from .disk_cache import content_digest
    descriptor = dict(method=METHOD, source_box=store.box_of(source), source_index=source['index'],
                      source_stem=source['stem'], source_created=source.get('created'),
                      source_layout=(source.get('timeline') or {}).get('layout'), source_stamp=stamp,
                      source_digest=content_digest((front, back)).hex(), context_frames=segment.context_frames,
                      capstone_suppressed=reason)
    _current_source(segment, descriptor)
    return front, back, descriptor


def prepare_latent(latent, segment, front):
    if (segment.protection_source or {}).get('context_noise'):
        raise ValueError(f'{WHO}: turn off the old Context noise control before using sampler-level protection.')
    video, audio = latents.split_h3_latent(latent, WHO)
    count = timing.tokens_for_frames(segment.context_frames)
    if tuple(front.shape) != (1, 24, 1, *video.shape[3:]) or count >= video.shape[2]:
        raise ValueError(f'{WHO}: anchor or carried length does not match this latent.')
    masks = latent.get('noise_mask')
    if not getattr(masks, 'is_nested', False) or len(masks.tensors) != 2:
        raise ValueError(f'{WHO}: expected the native Timeline AV noise mask.')
    vm, am = masks.tensors
    try:
        vm = torch.broadcast_to(vm, video.shape)
    except RuntimeError:
        raise ValueError(f'{WHO}: incompatible video mask shape.') from None
    expected = torch.ones_like(vm)
    expected[:, :, :count] = 0
    if segment.ending_video is not None:
        expected[:, :, -segment.ending_video.shape[2]:] = 0
    if not torch.equal(vm, expected):
        raise ValueError(f'{WHO}: an incompatible mask already edits the carried or free video.')
    originals = video[:, :, :count].clone()
    video = video.clone()
    video[:, :, :1] = front.to(video)
    vm = vm.clone()
    vm[:, :, 1:count] = torch.linspace(1, 0, count - 1, device=vm.device, dtype=vm.dtype).view(1,1,-1,1,1)
    from comfy.nested_tensor import NestedTensor
    prepared = dict(latent, samples=NestedTensor((video, audio)), noise_mask=NestedTensor((vm, am)))
    return prepared, originals


class ProtectionReceipt:
    """An opaque execution witness: never a cacheable or persisted prepared setting."""
    def __init__(self):
        self.lock = threading.Lock()
        self.complete = False
        self.accepted = set()
        self.descriptor = None
        self.schedule = None
        self.calls = 0


def _streams(value, shapes):
    from comfy.utils import unpack_latents
    return list(value.tensors) if getattr(value, 'is_nested', False) else list(unpack_latents(value, shapes))


def _restored(value, shapes, segment, originals, core, *, internal=False):
    from comfy.nested_tensor import NestedTensor
    from comfy.utils import pack_latents
    parts = _streams(value, shapes)
    video, audio = (v.clone() for v in parts)
    if video.shape[2] != timing.tokens_for_frames(segment.frames) or tuple(video.shape[3:]) != segment.latent_size:
        raise ValueError(f'{WHO}: sampler output shape changed; cannot restore carried frames.')

    def converted(tensor, target, *, sound=False):
        if internal:
            tensor = core.latent_format.process_in(tensor)
            if sound:
                tensor = tensor * core.audio_scale()
        return tensor.to(target)

    video[:, :, :originals.shape[2]] = converted(originals, video)
    if segment.ending_video is not None:
        video[:, :, -segment.ending_video.shape[2]:] = converted(segment.ending_video, video)
    if segment.carried_audio is not None:
        start = segment.carried_audio_start
        audio[..., start:start + segment.carried_audio.shape[-1]] = converted(segment.carried_audio, audio, sound=True)
    if segment.ending_audio is not None:
        start = timing.audio_tail_start(segment.frames, audio.shape[-1],
                                        timing.frames_for_tokens(segment.ending_video.shape[2]))
        audio[..., start:start + segment.ending_audio.shape[-1]] = converted(segment.ending_audio, audio, sound=True)
    result = NestedTensor((video, audio))
    return result if getattr(value, 'is_nested', False) else pack_latents(result.tensors)[0]


def _sample_digest(value, shapes):
    from comfy.nested_tensor import NestedTensor
    from .disk_cache import content_digest
    return content_digest(NestedTensor(_streams(value, shapes)))


def patch_model(model, prepared, segment, originals, capstone, descriptor):
    import comfy.model_base
    import comfy.patcher_extension as pe
    import comfy.utils
    core = model.model
    if (not isinstance(core, comfy.model_base.MiniMaxH3) or isinstance(core, comfy.model_base.MiniMaxH3Image)
            or not hasattr(core, '_denoise_mask_values')):
        raise ValueError(f'{WHO}: a current native MiniMax H3 AV model with partial masks is required.')
    if model.model_options.get('context_handler') is not None:
        raise ValueError(f'{WHO}: Context Windows are not supported; use a non-windowed continuing clip.')
    if model.model_options.get('h3c_protection'):
        raise ValueError(f'{WHO}: this model is already protected; connect only one protection node.')
    m = model.clone()
    m.model_options['h3c_protection'] = True
    receipt = ProtectionReceipt()
    previous = m.model_options.get('model_function_wrapper')

    def evaluate(apply_model, args):
        c = args['c']
        options = c.get('transformer_options') or {}
        if options.get('context_window') is not None:
            raise ValueError(f'{WHO}: Context Windows are not supported.')
        if receipt.schedule is None:
            raise ValueError(f'{WHO}: sample this model through the protected sampler path.')
        values = args['timestep'].detach().float().flatten()
        sigma = float(values[0])
        if not bool(torch.isfinite(values).all()) or not bool((values == values[0]).all()) or not 0 <= sigma <= receipt.schedule[0]:
            raise ValueError(f'{WHO}: ambiguous model timestep for the sampling schedule.')
        receipt.calls += 1
        if capstone is None or sigma > receipt.schedule[receipt.start]:
            return previous(apply_model, args) if previous else apply_model(args['input'], args['timestep'], **c)
        shapes = c.get('latent_shapes')
        if shapes is None or len(shapes) != 2:
            raise ValueError(f'{WHO}: missing native packed AV shapes for the capstone.')
        video, audio = comfy.utils.unpack_latents(args['input'], shapes)
        anchor = core.latent_format.process_in(capstone).to(video).expand(video.shape[0], -1, -1, -1, -1)
        enlarged, new_shapes = comfy.utils.pack_latents((torch.cat((video, anchor), dim=2), audio))
        mask = c.get('denoise_mask')
        if mask is None or mask.shape[2] != video.shape[2]:
            raise ValueError(f'{WHO}: missing native video mask for the capstone.')
        conditions = dict(c, latent_shapes=new_shapes,
                          denoise_mask=torch.cat((mask, torch.zeros_like(mask[:, :, :1])), dim=2),
                          transformer_options=dict(options))
        # Native H3 rebuilds its packed layout on a changed temporal signature.
        if 'minimax_payload' in conditions:
            conditions['minimax_payload'] = {k:v for k,v in conditions['minimax_payload'].items() if k != 'layout'}
        call = dict(args, input=enlarged, c=conditions)
        result = previous(apply_model, call) if previous else apply_model(enlarged, args['timestep'], **conditions)
        streams = comfy.utils.unpack_latents(result, new_shapes)
        return comfy.utils.pack_latents((streams[0][:, :, :video.shape[2]], streams[1]))[0]

    def sample(executor, noise, latent_image, sampler, sigmas, denoise_mask=None, callback=None,
               disable_pbar=False, seed=None, latent_shapes=None):
        if not receipt.lock.acquire(blocking=False):
            raise ValueError(f'{WHO}: this prepared model is already sampling.')
        receipt.complete, receipt.accepted, receipt.descriptor = False, set(), None
        receipt.calls = 0
        receipt.schedule = None
        try:
            if getattr(executor.class_obj, 'model_options', {}).get('context_handler') is not None:
                raise ValueError(f'{WHO}: Context Windows are not supported.')
            schedule = sigmas.detach().double().cpu().flatten().tolist()
            if (len(schedule) < 2 or schedule[-1] != 0 or not all(math.isfinite(s) for s in schedule)
                    or not all(a > b >= 0 for a,b in zip(schedule, schedule[1:]))):
                raise ValueError(f'{WHO}: needs a finite descending sigma schedule ending at zero.')
            if latent_shapes is None or len(latent_shapes) != 2:
                raise ValueError(f'{WHO}: needs native packed AV sampling.')
            _current_source(segment, descriptor)
            receipt.schedule = schedule
            receipt.start = min(len(schedule)-2, math.ceil(.75 * (len(schedule)-1)))
            last_x0 = None

            def restored_callback(step, x0, x, total):
                nonlocal last_x0
                restored = _restored(x0, latent_shapes, segment, originals, core, internal=True)
                last_x0 = _sample_digest(core.process_latent_out(restored.cpu()), latent_shapes)
                if callback:
                    callback(step, restored, x, total)

            result = executor(noise, latent_image, sampler, sigmas, denoise_mask, restored_callback,
                              disable_pbar, seed, latent_shapes=latent_shapes)
            result = _restored(result, latent_shapes, segment, originals, core)
            if not receipt.calls:
                raise ValueError(f'{WHO}: the protected model was not evaluated by the sampler.')
            receipt.accepted = {_sample_digest(result, latent_shapes)}
            if last_x0 is not None:
                receipt.accepted.add(last_x0)
            receipt.descriptor = dict(descriptor, late_start_step=receipt.start if capstone is not None else None,
                                      sampling_steps=len(schedule)-1)
            receipt.complete = True
            return result
        finally:
            receipt.schedule = None
            receipt.lock.release()

    m.set_model_unet_function_wrapper(evaluate)
    # Run restoration outside existing wrappers, so Save sees the final restored result.
    pe.add_wrapper_with_key(pe.WrappersMP.OUTER_SAMPLE, METHOD, sample, m.model_options, is_model_options=True)
    return m, receipt


def validate_save(segment, latent):
    receipt = segment.protection_receipt
    if receipt is None and RECEIPT_KEY not in latent:
        return None
    if not isinstance(receipt, ProtectionReceipt) or latent.get(RECEIPT_KEY) is not receipt:
        raise ValueError(f'{WHO}: connect this node\'s returned segment and sampler output to Save Segment.')
    from .disk_cache import content_digest
    if not receipt.complete or content_digest(latent['samples']) not in receipt.accepted:
        raise ValueError(f'{WHO}: this output has no matching completed sampling receipt; sample again.')
    return copy.deepcopy(receipt.descriptor)


from comfy_api.latest import io
from .nodes import CATEGORY, SegmentType


class H3C_ContinuityProtection(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='H3C_ContinuityProtection', display_name=WHO, category=CATEGORY,
                         description='Opt-in context noise, clean scene anchors and a late capstone for native '
                                     'continuations. Connect model to the guider, latent to the sampler and the '
                                     'returned segment to Save Segment. Turn off old Context noise. Protected '
                                     'sampling bypasses disk cache. No Context Windows. Regenerate affected clips '
                                     'or start a new generation; graph changes do not mark old takes outdated.',
                         inputs=[io.Model.Input('model'), io.Latent.Input('latent'), SegmentType.Input('segment'),
                                 io.Boolean.Input('enabled', default=True)],
                         outputs=[io.Model.Output(display_name='model'), io.Latent.Output(display_name='latent'),
                                  SegmentType.Output(display_name='segment'), io.String.Output(display_name='info')])

    @classmethod
    def execute(cls, model, latent, segment, enabled=True):
        info = segment.protection_source or {}
        if not enabled or segment.carried_video is None or info.get('status') == 'skip':
            reason = 'Disabled.' if not enabled else info.get('reason', 'No continuing native chain.')
            return io.NodeOutput(model, latent, segment, f'{WHO}: passed through. {reason}')
        owned = replace(segment, timeline=copy.deepcopy(segment.timeline),
                        protection_source=copy.deepcopy(segment.protection_source))
        front, capstone, descriptor = load_anchors(owned)
        prepared, originals = prepare_latent(latent, owned, front)
        model, owned.protection_receipt = patch_model(model, prepared, owned, originals, capstone, descriptor)
        prepared[RECEIPT_KEY] = owned.protection_receipt
        message = f'{WHO}: prepared; sampler-level noise and clean chain anchor. Disk sampling cache bypassed.'
        if descriptor.get('capstone_suppressed'):
            message += f" Capstone off: {descriptor['capstone_suppressed']}"
        return io.NodeOutput(model, prepared, owned, message)
