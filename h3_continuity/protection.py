"""Native H3 continuation protection; public techniques credited in the long-chain guide."""

import copy

import torch

from . import latents, store, timeline, timing

METHOD = 'h3c-continuity-protection-v1'
WHO = 'H3 Continuity Protection'


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
              'An authored frame guide owns the target pose.' if guides else '')
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
