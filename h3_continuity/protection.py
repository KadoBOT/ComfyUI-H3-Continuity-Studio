"""Native H3 continuation protection; public techniques credited in the long-chain guide."""

import copy
import math
import threading
from dataclasses import replace

import torch
import torch.nn.functional as F

from . import latents, store, timeline, timing

METHOD = 'h3c-continuity-protection-v1'
WHO = 'H3 Continuity Protection'
RECEIPT_KEY = '_h3c_protection_receipt'
# H3 blocks that Geiru Context Suite reports as carrying brightness; its finding, not our measurement.
LIGHTING_BLOCKS = '31-33, 36-44, 47'
DEFAULT_STRENGTH = 0.70
REF_STRENGTH_MULTIPLIER = 1.5
SHORT_REF_TOKENS = 2
SHORT_REF_MEAN_CAP = 0.25
TAIL_ANCHOR_TOKENS = 12
CARRIED_TAIL_TOKENS = 5
SEAM_FEATHER_TOKENS = 8
SEAM_RAMP_TOKENS = 2
ROOT_PULL_MAX_STD = 0.25
MEAN_TAIL_FLOOR = 0.85
PHASE1_STD_HEADROOM = 1.15
MODES = ('full', 'contrast_only')


def parse_blocks(text):
    blocks = set()
    for part in str(text or '').replace(';', ',').split(','):
        ends = [end.strip() for end in part.split('-')]
        if ends == ['']:
            continue
        if len(ends) > 2 or not all(end.isdigit() for end in ends):
            raise ValueError(f"{WHO}: cannot read attention blocks '{part.strip()}'; "
                             f'use numbers and ranges such as {LIGHTING_BLOCKS}.')
        blocks.update(range(min(map(int, ends)), max(map(int, ends)) + 1))
    return frozenset(blocks)


def balanced_attention(q, k, v, anchor, context, balance):
    """Re-split only the attention shared by anchor and context keys; q, k, v are [1, heads, rows, dim].

    With anchor share a and context share c of one query's attention, the anchor takes
    (a + c) * balance * a / (balance * a + c) and the context keeps the rest of a + c. Every other key
    keeps its exact share. Two marker value channels read a and c out of the ordinary attention pass.
    """
    attend = torch.nn.functional.scaled_dot_product_attention
    heads, rows, dim = q.shape[1:]
    marks = v.new_zeros(k.shape[2], 8)
    marks[anchor, 0] = 1
    marks[context, 1] = 1
    out = torch.empty(q.shape[0], rows, heads * dim, dtype=q.dtype, device=q.device)
    wide = torch.promote_types(q.dtype, torch.float32)   # shares need more than half precision
    step = max(1, heads // 4)   # heads are independent; groups bound the extra memory
    for h in range(0, heads, step):
        qs, ks, vs = (t[:, h:h + step] for t in (q, k, v))
        full = attend(qs, ks, torch.cat((vs, marks.expand(*vs.shape[:2], -1, -1)), dim=-1))
        a, c = full[..., dim:dim + 1].to(wide), full[..., dim + 1:dim + 2].to(wide)
        gain = (a + c) * balance * a / (balance * a + c).clamp_min(1e-12) - a
        moved = (attend(qs, ks[:, :, anchor], vs[:, :, anchor]).to(wide)
                 - attend(qs, ks[:, :, context], vs[:, :, context]).to(wide))
        part = (full[..., :dim].to(wide) + gain * moved).to(q.dtype)
        out[:, :, h * dim:(h + step) * dim] = part.transpose(1, 2).reshape(q.shape[0], rows, -1)
    return out


def attention_override(previous, receipt, tokens, held, balance, blocks):
    """Core optimized_attention_override: balance our own rows on the chosen blocks, otherwise defer."""
    def override(func, q, k, v, heads, mask=None, skip_reshape=False, **kwargs):
        options = kwargs.get('transformer_options') or {}
        layout = options.get('minimax_h3_layout')
        span = next(((a, z) for a, z, kind in getattr(layout, 'segments', ()) if kind == 'video'), None)
        frames = layout.signature[1] if span else 0
        # The late capstone is one extra held latent after the clip's own tokens.
        if (span and skip_reshape and mask is None and not kwargs.get('skip_output_reshape')
                and options.get('block_index') in blocks and k.shape[-2] == layout.seq_len
                and frames in (tokens, tokens + 1)):
            rows = (span[1] - span[0]) // frames

            def index(slots):
                return torch.cat([torch.arange(span[0] + s * rows, span[0] + (s + 1) * rows) for s in slots]).to(k.device)

            receipt.balanced += 1
            receipt.balanced_blocks.add(options['block_index'])
            return balanced_attention(q, k, v, index([0] + [tokens] * (frames > tokens)), index(held), balance)
        if previous:
            return previous(func, q, k, v, heads, mask=mask, skip_reshape=skip_reshape, **kwargs)
        return func(q, k, v, heads, mask=mask, skip_reshape=skip_reshape, **kwargs)
    override.h3c_balance = balance
    return override


def passthrough_reason(segment):
    info = getattr(segment, 'protection_source', None) or {}
    record = getattr(segment, 'timeline', None) or {}
    if any(kind in record for kind in ('bridge', 'replacement', 'layer')):
        return 'Bridge, replacement or layer: no protected continuing chain.'
    if getattr(segment, 'carried_video', False) is None and info.get('mode') != 'cut_memory':
        return 'Fresh clip: no carried chain.'
    if info.get('status') == 'skip':
        return info.get('reason') or 'No protected continuing chain.'
    return None


def _is_appearance_reset(box):
    return bool(box.plate_changes or (box.new_scene and not box.cut))


def _resolve_root(parsed, index, seen=None):
    """Find the earliest clean scene root index whose visual tone/lighting owns box `index`, or None.

    A `new_scene=True` cut always starts a fresh lighting/exposure root (never inheriting mean/color
    across scene/lighting changes via `cast`, `selected`, or `scene` visual memory). An in-chain
    `plate_changes` (or `new_scene` without `cut`) resets the root to that box for subsequent clips.
    """
    seen = set() if seen is None else set(seen)
    if index in seen:
        return None
    seen.add(index)
    box = parsed.boxes[index]
    chain = timeline.continuation_chain(parsed, index)
    if len(chain) >= 2:
        resets = [i for i in chain if _is_appearance_reset(parsed.boxes[i])]
        if resets:
            latest = resets[-1]
            return None if latest == index else latest
        root = _resolve_root(parsed, chain[0], seen)
        return chain[0] if root is None else root
    if not box.cut or box.memory == 'off' or box.new_scene:
        return None
    indices = timeline.track_indices(parsed, index)
    pos = indices.index(index)
    start_pos = max(p for p, i in enumerate(indices[:pos + 1])
                    if p == 0 or (parsed.boxes[i].cut and parsed.boxes[i].new_scene)
                    or _is_appearance_reset(parsed.boxes[i]))
    start = indices[start_pos]
    if start == index:
        return None
    if _is_appearance_reset(parsed.boxes[start]):
        return start
    root = _resolve_root(parsed, start, seen)
    return start if root is None else root


def source_info(parsed, index, entries, is_done, guides, ending):
    """Defer optional source failures: ordinary Timeline graphs need no protection anchor."""
    if _is_appearance_reset(parsed.boxes[index]):
        return dict(status='skip', reason='Appearance change: resets protection root for subsequent clips.')
    chain = timeline.continuation_chain(parsed, index)
    is_cut = len(chain) < 2
    root = _resolve_root(parsed, index)
    if root is None:
        return dict(status='skip', reason='Fresh clip or track gap: no carried chain.')
    source = entries.get(root + 1)
    if (not source or store.box_of(source) != parsed.boxes[root].id
            or not is_done(root, source)):
        return dict(status='error', reason='The chain source needs rendering before protection can run.')
    mode = 'cut_memory' if is_cut else 'continuation'
    if is_cut:
        reason = 'Cut memory clip: anchor statistical protection active.'
    elif ending:
        reason = 'A following clip holds the ending.'
    elif guides or parsed.boxes[index].last:
        reason = 'An authored frame guide owns the target pose.'
    else:
        reason = ''
    return dict(status='ready', mode=mode, same_shot=(not is_cut and root in chain),
                source=copy.deepcopy(source), context_noise=parsed.context_noise, capstone_suppressed=reason)


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
    descriptor = dict(method=METHOD, mode=(segment.protection_source or {}).get('mode', 'continuation'),
                      source_box=store.box_of(source), source_index=source['index'],
                      source_stem=source['stem'], source_created=source.get('created'),
                      source_layout=(source.get('timeline') or {}).get('layout'), source_stamp=stamp,
                      source_digest=content_digest((front, back)).hex(), context_frames=segment.context_frames,
                      capstone_suppressed=reason)
    _current_source(segment, descriptor)
    return front, back, descriptor


def load_anchor_clip(segment, descriptor=None):
    """Load the clean anchor clip's target video latent tokens and absolute starting token index.

    For direct same-shot continuations, use the clean anchor's exit tail (`TAIL_ANCHOR_TOKENS`) so
    opening-frame composition sweeps (such as camera orbits from dark furniture onto sunlit walls)
    do not skew downstream shots; cuts and post-cut continuations use the full played anchor.
    """
    source, _ = _current_source(segment, descriptor)
    folder = segment.sequence.folder
    src_ctx = source.get('context_frames', 0)
    anc_start = timing.tokens_for_frames(src_ctx) if src_ctx else 0
    delivered = src_ctx + store.played_frames(source)
    total_tok = store.video_tokens(folder, source)
    delivered_tok = next((t for t in range(1, total_tok + 1) if timing.frames_for_tokens(t) >= delivered), total_tok)
    end_tok = max(anc_start + 1, min(total_tok, delivered_tok))
    if (segment.protection_source or {}).get('same_shot'):
        tail_tokens = min(end_tok - anc_start, TAIL_ANCHOR_TOKENS)
        anc_start = end_tok - tail_tokens
    anc_video = store.load_video_window(folder, source, anc_start, end_tok - anc_start)
    if anc_video.ndim != 5 or anc_video.shape[:2] != (1, 24) or tuple(anc_video.shape[3:]) != segment.latent_size:
        raise ValueError(f'{WHO}: source does not contain a compatible H3 video anchor.')
    return anc_video, anc_start


def prepare_latent(latent, segment, front=None):
    if (segment.protection_source or {}).get('context_noise'):
        raise ValueError(f'{WHO}: turn off the old Context noise control before using sampler-level protection.')
    video, audio = latents.split_h3_latent(latent, WHO)
    if (timing.frames_for_tokens(video.shape[2]) != segment.frames or tuple(video.shape[3:]) != segment.latent_size
            or audio.shape[:3] != (video.shape[0], 32, 2)
            or audio.shape[-1] != timing.ticks_for_frames(segment.frames)):
        raise ValueError(f'{WHO}: latent geometry does not match the native segment.')
    if front is not None and tuple(front.shape) != (1, 24, 1, *video.shape[3:]):
        raise ValueError(f'{WHO}: anchor shape does not match this latent.')

    from comfy.nested_tensor import NestedTensor
    if segment.carried_video is None:
        if (segment.protection_source or {}).get('mode') != 'cut_memory':
            raise ValueError(f'{WHO}: carried video does not match the native segment.')
        prepared = dict(latent, samples=NestedTensor((video.clone(), audio.clone())))
        return prepared, None

    count = timing.tokens_for_frames(segment.context_frames)
    if count >= video.shape[2]:
        raise ValueError(f'{WHO}: carried length does not match this latent.')

    def same(actual, expected, label):
        try:
            matches = expected is not None and torch.equal(actual, expected.to(actual).expand_as(actual))
        except RuntimeError:
            matches = False
        if not matches:
            raise ValueError(f'{WHO}: {label} does not match the native segment.')

    same(video[:, :, :count], segment.carried_video, 'carried video')
    if segment.carried_audio is not None:
        start = segment.carried_audio_start
        same(audio[..., start:start + segment.carried_audio.shape[-1]], segment.carried_audio, 'carried audio')
    if segment.ending_video is not None:
        same(video[:, :, -segment.ending_video.shape[2]:], segment.ending_video, 'ending video')
    if segment.ending_audio is not None:
        start = timing.audio_tail_start(segment.frames, audio.shape[-1],
                                        timing.frames_for_tokens(segment.ending_video.shape[2]))
        same(audio[..., start:start + segment.ending_audio.shape[-1]], segment.ending_audio, 'ending audio')
    masks = latent.get('noise_mask')
    if not getattr(masks, 'is_nested', False) or len(masks.tensors) != 2:
        raise ValueError(f'{WHO}: expected the native Timeline AV noise mask.')
    vm, am = masks.tensors
    end_start = video.shape[2] - (segment.ending_video.shape[2] if segment.ending_video is not None else 0)
    if (tuple(vm.shape[2:]) != tuple(video.shape[2:]) or vm.shape[0] != video.shape[0] or vm.shape[1] not in (1, 24)
            or not bool((vm[:, :, :count] == 0).all()) or not bool((vm[:, :, count:end_start] == 1).all())
            or (end_start < video.shape[2] and not bool((vm[:, :, end_start:] == 0).all()))):
        raise ValueError(f'{WHO}: expected the native Timeline video noise mask.')
    originals = video[:, :, :count].clone()
    prepared = dict(latent, samples=NestedTensor((video.clone(), audio.clone())),
                    noise_mask=NestedTensor((vm.clone(), am.clone())))
    return prepared, originals


def _split_hf(z):
    """3x3 replicate-padded spatial high-pass decomposition for [B, C, T, H, W] float32 tensors."""
    b, c, t, h, w = z.shape
    flat = z.permute(0, 2, 1, 3, 4).reshape(b * t, c, h, w)
    low = F.avg_pool2d(F.pad(flat, (1, 1, 1, 1), mode='replicate'), kernel_size=3, stride=1, padding=0)
    low = low.reshape(b, t, c, h, w).permute(0, 2, 1, 3, 4)
    return low, z - low


def _tensor_stats(z):
    mean = z.mean(dim=(2, 3, 4), keepdim=True)
    std = z.std(dim=(2, 3, 4), unbiased=False, keepdim=True).clamp_min(1e-5)
    _, high = _split_hf(z)
    hf_rms = high.pow(2).mean(dim=(2, 3, 4), keepdim=True).sqrt().clamp_min(1e-5)
    return mean, std, hf_rms


def compute_phase_stats(video, abs_offset=0):
    """Compute separate phase-0 (t%5==0, 1-frame) and phase-1 (t%5!=0, 4-frame) channel stats."""
    z = video.float()
    t = z.shape[2]
    p0 = [k for k in range(t) if (abs_offset + k) % 5 == 0]
    p1 = [k for k in range(t) if (abs_offset + k) % 5 != 0]
    all_stats = _tensor_stats(z)
    return {
        0: _tensor_stats(z[:, :, p0]) if p0 else all_stats,
        1: _tensor_stats(z[:, :, p1]) if p1 else all_stats,
        'all': all_stats,
    }


def compute_carried_tail_stats(carried_video):
    """Phase-0 / phase-1 stats at the immediate exit of `carried_video` ([B, C, T_ctx, H, W]).

    Uses the final token of each phase within the trailing 5-token cycle (`CARRIED_TAIL_TOKENS`) so
    opening generated token `ctx_tok` meets the exact exit luminance/exposure of the previous clip.
    """
    z = carried_video[:1].float()
    t = z.shape[2]
    start = max(0, t - CARRIED_TAIL_TOKENS)
    tail = z[:, :, start:]
    t_tail = tail.shape[2]
    p0 = [k for k in range(t_tail) if (start + k) % 5 == 0]
    p1 = [k for k in range(t_tail) if (start + k) % 5 != 0]
    last_stats = _tensor_stats(tail[:, :, -1:])
    return {
        0: _tensor_stats(tail[:, :, p0[-1:]]) if p0 else last_stats,
        1: _tensor_stats(tail[:, :, p1[-1:]]) if p1 else last_stats,
        'all': _tensor_stats(tail),
    }


def _stats_on_device(stats, device, cache):
    key = str(device)
    if key not in cache:
        cache[key] = {
            p: tuple(t.to(device=device, dtype=torch.float32) for t in vals)
            for p, vals in stats.items()
        }
    return cache[key]


def _smooth_temporal_mean(tok_mean):
    """3-tap [0.25, 0.50, 0.25] replicate-padded temporal smoothing on [B, C, T, 1, 1] token means."""
    if tok_mean.shape[2] <= 1:
        return tok_mean
    flat = tok_mean.squeeze(-1).squeeze(-1)
    padded = F.pad(flat, (1, 1), mode='replicate')
    smoothed = 0.25 * padded[:, :, :-2] + 0.50 * padded[:, :, 1:-1] + 0.25 * padded[:, :, 2:]
    return smoothed.unsqueeze(-1).unsqueeze(-1)


def _soft_clamp_delta(delta, cap):
    """Smoothly bound |delta| to `cap` via cap * tanh(delta / cap)."""
    cap = cap.clamp_min(1e-5)
    return cap * torch.tanh(delta / cap)


def _stabilize_video(video, stats, *, abs_offset=0, strength=1.0, match_mean=True,
                     mean_strength=None, tail_stats=None, same_shot=True,
                     seam_feather=0, seam_ramp=0, end_ramp=0,
                     local_mean=False, phase1_std_headroom=1.0):
    """Phase-aware per-channel upper-clamped std, seam-feathered mean alignment, and 3x3 HF damping."""
    orig_dtype = video.dtype
    z = video.float()
    t = z.shape[2]
    detail_w = float(strength)
    mean_w = detail_w if mean_strength is None else float(mean_strength)
    if detail_w <= 0.0 and (not match_mean or mean_w <= 0.0):
        return video
    p0 = [k for k in range(t) if (abs_offset + k) % 5 == 0]
    p1 = [k for k in range(t) if (abs_offset + k) % 5 != 0]
    out = z.clone()

    for phase, idx in ((0, p0), (1, p1)):
        if not idx:
            continue
        anc_mean, anc_std, anc_hf = stats[phase]
        cur = z[:, :, idx]
        if local_mean:
            tok_mean = cur.mean(dim=(3, 4), keepdim=True)
            cur_mean = _smooth_temporal_mean(tok_mean) if (phase == 1 and cur.shape[2] >= 2) else tok_mean
        else:
            cur_mean = cur.mean(dim=(2, 3, 4), keepdim=True)
        centered = cur - cur_mean
        cur_std = centered.std(dim=(2, 3, 4), unbiased=False, keepdim=True).clamp_min(1e-5)
        std_cap = anc_std * (float(phase1_std_headroom) if phase == 1 else 1.0)
        target_std = torch.minimum(cur_std, std_cap)
        std_aligned = centered * (target_std / cur_std)

        low, high = _split_hf(std_aligned)
        cur_hf = high.pow(2).mean(dim=(2, 3, 4), keepdim=True).sqrt().clamp_min(1e-5)
        hf_scale = torch.clamp(anc_hf / cur_hf, max=1.0)
        # Cancel replicate-padding boundary bias so HF damping preserves exact spatial mean.
        detail_aligned = low + high * hf_scale - (hf_scale - 1.0) * high.mean(dim=(3, 4), keepdim=True)

        idx_t = torch.tensor(idx, device=z.device, dtype=torch.float32).view(1, 1, -1, 1, 1)
        detail_ramp = torch.ones_like(idx_t)
        if seam_ramp > 0:
            detail_ramp = torch.minimum(detail_ramp, ((idx_t + 1.0) / float(seam_ramp + 1)).clamp(0.0, 1.0))
        end_fade = torch.ones_like(idx_t)
        if end_ramp > 0:
            dist_end = float(t - 1) - idx_t
            end_fade = ((dist_end + 1.0) / float(end_ramp + 1)).clamp(0.0, 1.0)
            detail_ramp = torch.minimum(detail_ramp, end_fade)

        centered_out = centered + (detail_w * detail_ramp) * (detail_aligned - centered)

        if match_mean and mean_w > 0.0:
            if tail_stats is not None:
                tail_mean = tail_stats[phase][0]
                if same_shot:
                    cap = anc_std * ROOT_PULL_MAX_STD
                    far_mean = tail_mean + _soft_clamp_delta(anc_mean - tail_mean, cap)
                    if seam_feather > 0:
                        frac = (idx_t / float(seam_feather)).clamp(0.0, 1.0)
                        alpha = 0.5 * (1.0 - torch.cos(math.pi * frac))
                        target_mean = tail_mean + alpha * (far_mean - tail_mean)
                    else:
                        target_mean = far_mean
                else:
                    # Post-cut continuation: anchor mean strictly to carried tail; root owns std/HF only.
                    target_mean = tail_mean
                # target_mean already matches tail_mean at idx=0 and feathers smoothly; only fade near a frozen ending.
                mean_ramp = end_fade
            else:
                target_mean = anc_mean
                mean_ramp = detail_ramp
            mean_out = cur_mean + (mean_w * mean_ramp) * (target_mean - cur_mean)
        else:
            mean_out = cur_mean

        out[:, :, idx] = centered_out + mean_out

    return out.to(dtype=orig_dtype)


def _schedule_weight(strength, u):
    """Hold full detail/std stabilization through u=0.75 progress, tapering smoothly to 0.5*strength at u=1.0."""
    if strength <= 0:
        return 0.0
    if u <= 0.75:
        return float(strength)
    frac = min(1.0, max(0.0, (u - 0.75) / 0.25))
    return float(strength) * (1.0 - 0.5 * frac)


def _mean_schedule_weight(strength, u):
    """Hold full mean stabilization through u=0.75, tapering only to MEAN_TAIL_FLOOR*strength at u=1.0."""
    if strength <= 0:
        return 0.0
    if u <= 0.75:
        return float(strength)
    frac = min(1.0, max(0.0, (u - 0.75) / 0.25))
    return float(strength) * (1.0 - (1.0 - MEAN_TAIL_FLOOR) * frac)


def _schedule_weights(strength, u):
    """Return (mean_weight, detail_weight) at normalized progress u in [0, 1]."""
    return _mean_schedule_weight(strength, u), _schedule_weight(strength, u)


class ProtectionReceipt:
    """An opaque execution witness: never a cacheable or persisted prepared setting."""
    def __init__(self):
        self.lock = threading.Lock()
        self.complete = False
        self.accepted = set()
        self.descriptor = None
        self.schedule = None
        self.calls = 0
        self.post_cfg_calls = 0
        self.balanced = 0
        self.balanced_blocks = set()


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

    if originals is not None:
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


def patch_model(model, prepared, segment, originals, capstone, descriptor, balance=1.0, blocks=frozenset(),
                *, anchor_video=None, anchor_offset=0, strength=DEFAULT_STRENGTH, mode='full'):
    import comfy.model_base
    import comfy.patcher_extension as pe
    import comfy.utils
    import comfy.sampler_helpers
    from .disk_cache import content_digest
    core = model.model
    if (not isinstance(core, comfy.model_base.MiniMaxH3) or isinstance(core, comfy.model_base.MiniMaxH3Image)
            or not hasattr(core, '_denoise_mask_values')):
        raise ValueError(f'{WHO}: a current native MiniMax H3 AV model with partial masks is required.')
    if model.model_options.get('context_handler') is not None:
        raise ValueError(f'{WHO}: Context Windows are not supported; use a non-windowed continuing clip.')
    if model.model_options.get('h3c_protection'):
        raise ValueError(f'{WHO}: this model is already protected; connect only one protection node.')
    if mode not in MODES:
        raise ValueError(f'{WHO}: unsupported protection mode {mode!r}; expected one of {MODES}.')
    strength = float(strength)
    if not math.isfinite(strength) or not 0.0 <= strength <= 1.0:
        raise ValueError(f'{WHO}: strength must be between 0.0 and 1.0.')
    match_mean = (mode == 'full')

    m = model.clone()
    m.model_options['h3c_protection'] = True
    receipt = ProtectionReceipt()
    previous = m.model_options.get('model_function_wrapper')

    masks = prepared.get('noise_mask')
    if masks is not None:
        video_mask = masks.tensors[0]
        held = ([s for s in range(1, originals.shape[2]) if float(video_mask[0, 0, s].max()) < .5]
                if originals is not None else [])
    else:
        held = []

    balancing = balance != 1 and bool(blocks) and bool(held)
    if balancing:
        invalid = blocks - set(range(len(core.diffusion_model.blocks)))
        if invalid:
            raise ValueError(f'{WHO}: attention blocks {sorted(invalid)} do not exist in this model.')
        t_opts = m.model_options.setdefault('transformer_options', {})
        t_opts['optimized_attention_override'] = attention_override(
            t_opts.get('optimized_attention_override'), receipt, prepared['samples'].tensors[0].shape[2],
            held, float(balance), blocks)

    expected_samples, expected_shapes = comfy.utils.pack_latents(prepared['samples'].tensors)
    expected_input = _sample_digest(expected_samples, expected_shapes)
    if masks is not None:
        expected_mask = content_digest(comfy.utils.pack_latents([
            comfy.sampler_helpers.prepare_mask(mask, shape, torch.device('cpu'))
            for mask, shape in zip(masks.tensors, expected_shapes)])[0].float())
    else:
        expected_mask = None

    anc_tensor = anchor_video if anchor_video is not None else capstone
    anc_stats = None
    if anc_tensor is not None:
        anc_in = core.latent_format.process_in(anc_tensor.float())
        anc_stats = compute_phase_stats(anc_in, abs_offset=anchor_offset)
    tail_stats = None
    if originals is not None:
        orig_in = core.latent_format.process_in(originals[:1].float())
        tail_stats = compute_carried_tail_stats(orig_in)
    same_shot = bool((segment.protection_source or {}).get('same_shot', True))
    dev_stats_cache = {}
    dev_tail_cache = {}
    ref_cache = {}
    use_post_cfg = hasattr(m, 'set_model_sampler_post_cfg_function')
    active_shapes = [None]

    def call_model(apply_model, args):
        receipt.balanced_blocks.clear()
        result = previous(apply_model, args) if previous else apply_model(args['input'], args['timestep'], **args['c'])
        missing = blocks - receipt.balanced_blocks if balancing else set()
        if missing:
            raise ValueError(f'{WHO}: attention balance never ran on selected blocks {sorted(missing)}; '
                             'another attention patch may be bypassing native attention.')
        return result

    def _stabilize_packed(packed, sigma, shapes):
        if anc_stats is None or strength <= 0 or receipt.schedule is None:
            return packed
        sched = receipt.schedule
        n_steps = max(1, len(sched) - 1)
        step_idx = min(range(n_steps), key=lambda k: abs(sched[k] - sigma))
        u = step_idx / max(1, n_steps - 1) if n_steps > 1 else 0.0
        mean_w, detail_w = _schedule_weights(strength, u)
        if detail_w <= 0 and (not match_mean or mean_w <= 0):
            return packed
        if shapes is None or len(shapes) != 2:
            raise ValueError(f'{WHO}: missing native packed AV shapes for stabilization.')
        is_nested = getattr(packed, 'is_nested', False)
        video_x0, audio_x0 = _streams(packed, shapes)
        ctx_tok = originals.shape[2] if originals is not None else 0
        end_tok = segment.ending_video.shape[2] if segment.ending_video is not None else 0
        gen_end = video_x0.shape[2] - end_tok
        if ctx_tok < gen_end:
            dev_st = _stats_on_device(anc_stats, video_x0.device, dev_stats_cache)
            dev_tail = _stats_on_device(tail_stats, video_x0.device, dev_tail_cache) if tail_stats is not None else None
            gen = _stabilize_video(
                video_x0[:, :, ctx_tok:gen_end], dev_st, abs_offset=ctx_tok,
                strength=detail_w, mean_strength=mean_w, match_mean=match_mean,
                tail_stats=dev_tail, same_shot=same_shot,
                seam_feather=SEAM_FEATHER_TOKENS if ctx_tok > 0 else 0,
                seam_ramp=SEAM_RAMP_TOKENS if ctx_tok > 0 else 0,
                end_ramp=SEAM_RAMP_TOKENS if end_tok > 0 else 0,
                local_mean=True, phase1_std_headroom=PHASE1_STD_HEADROOM,
            )
            parts = ([video_x0[:, :, :ctx_tok]] if ctx_tok > 0 else []) + [gen] + (
                [video_x0[:, :, gen_end:]] if end_tok > 0 else [])
            video_out = parts[0] if len(parts) == 1 else torch.cat(parts, dim=2)
            if is_nested:
                from comfy.nested_tensor import NestedTensor
                return NestedTensor((video_out, audio_x0))
            return comfy.utils.pack_latents((video_out, audio_x0))[0]
        return packed

    def post_cfg(args):
        if receipt.schedule is None:
            return args['denoised']
        sigma_val = args.get('sigma')
        if sigma_val is None:
            return args['denoised']
        sigma = float(sigma_val.detach().float().flatten()[0])
        shapes = active_shapes[0] or getattr(args.get('model'), 'latent_shapes', None)
        receipt.post_cfg_calls += 1
        return _stabilize_packed(args['denoised'], sigma, shapes)

    def evaluate(apply_model, args):
        c = args['c']
        c_options = c.get('transformer_options') or {}
        if c_options.get('context_window') is not None:
            raise ValueError(f'{WHO}: Context Windows are not supported.')
        if receipt.schedule is None:
            raise ValueError(f'{WHO}: sample this model through the protected sampler path.')
        values = args['timestep'].detach().float().flatten()
        sigma = float(values[0])
        if not bool(torch.isfinite(values).all()) or not bool((values == values[0]).all()) or not 0 <= sigma <= receipt.schedule[0]:
            raise ValueError(f'{WHO}: ambiguous model timestep for the sampling schedule.')
        receipt.calls += 1

        shapes = c.get('latent_shapes')
        conditions = dict(c, transformer_options=dict(c_options))

        if anc_stats is not None and strength > 0 and 'minimax_payload' in conditions:
            payload = conditions['minimax_payload']
            refs = payload.get('refs') or ()
            kfs = payload.get('keyframes') or ()
            cond_lats = payload.get('cond_video_latents')
            kf_count = sum(1 for kf in kfs if kf.get('latent') is not None)
            ref_entries = [r for r in refs if 'latent' in r]
            if cond_lats and len(cond_lats) == kf_count + len(ref_entries):
                # Target only H3 Continuity visual-memory refs; leave user @video* refs, stills and keyframes untouched.
                video_indices = [kf_count + i for i, r in enumerate(ref_entries)
                                 if r.get('h3c_memory') and r.get('kind') in ('video', 'video_audio')]
                if video_indices:
                    cache_key = tuple((idx, id(cond_lats[idx]), tuple(cond_lats[idx].shape)) for idx in video_indices)
                    if cache_key not in ref_cache:
                        new_cond_lats = list(cond_lats)
                        eff_ref_w = min(1.0, strength * REF_STRENGTH_MULTIPLIER)
                        short_mean_w = min(SHORT_REF_MEAN_CAP, strength * 0.35)
                        for idx in video_indices:
                            ref_t = new_cond_lats[idx]
                            if isinstance(ref_t, torch.Tensor) and ref_t.ndim == 5 and ref_t.shape[1] == 24:
                                dev_st = _stats_on_device(anc_stats, ref_t.device, dev_stats_cache)
                                ref_mean_w = short_mean_w if ref_t.shape[2] <= SHORT_REF_TOKENS else eff_ref_w
                                ref_in = core.latent_format.process_in(ref_t.float())
                                ref_stab = _stabilize_video(
                                    ref_in, dev_st, abs_offset=0,
                                    strength=eff_ref_w, mean_strength=ref_mean_w, match_mean=match_mean,
                                    phase1_std_headroom=PHASE1_STD_HEADROOM,
                                )
                                new_cond_lats[idx] = core.latent_format.process_out(ref_stab).to(dtype=ref_t.dtype)
                        ref_cache[cache_key] = new_cond_lats
                    new_payload = dict(payload)
                    new_payload['cond_video_latents'] = ref_cache[cache_key]
                    conditions['minimax_payload'] = new_payload

        packed = call_model(apply_model, dict(args, c=conditions))

        if not use_post_cfg:
            cond_or_uncond = args.get('cond_or_uncond') or [0]
            if 1 not in cond_or_uncond:
                packed = _stabilize_packed(packed, sigma, shapes)
        return packed

    def sample(executor, noise, latent_image, sampler, sigmas, denoise_mask=None, callback=None,
               disable_pbar=False, seed=None, latent_shapes=None):
        if not receipt.lock.acquire(blocking=False):
            raise ValueError(f'{WHO}: this prepared model is already sampling.')
        receipt.complete, receipt.accepted, receipt.descriptor = False, set(), None
        receipt.calls = receipt.post_cfg_calls = receipt.balanced = 0
        receipt.schedule = None
        ref_cache.clear()
        try:
            if getattr(executor.class_obj, 'model_options', {}).get('context_handler') is not None:
                raise ValueError(f'{WHO}: Context Windows are not supported.')
            schedule = sigmas.detach().double().cpu().flatten().tolist()
            if (len(schedule) < 2 or schedule[-1] != 0 or not all(math.isfinite(s) for s in schedule)
                    or not all(a > b >= 0 for a, b in zip(schedule, schedule[1:]))):
                raise ValueError(f'{WHO}: needs a finite descending sigma schedule ending at zero.')
            if latent_shapes is None or len(latent_shapes) != 2:
                raise ValueError(f'{WHO}: needs native packed AV sampling.')
            if _sample_digest(latent_image, latent_shapes) != expected_input:
                raise ValueError(f'{WHO}: sampler did not receive the prepared input latent.')
            if expected_mask is None:
                if denoise_mask is not None:
                    raise ValueError(f'{WHO}: unexpected noise mask on cut-memory clip.')
            elif denoise_mask is None or content_digest(denoise_mask) != expected_mask:
                raise ValueError(f'{WHO}: sampler did not receive the prepared noise mask.')
            _current_source(segment, descriptor)
            receipt.schedule = schedule
            active_shapes[0] = latent_shapes
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
            if balancing and not receipt.balanced:
                raise ValueError(f'{WHO}: attention balance never ran; another attention patch replaces native H3 '
                                 'attention on these blocks. Set attention_balance to 1 or remove that patch.')
            receipt.accepted = {_sample_digest(result, latent_shapes)}
            if last_x0 is not None:
                receipt.accepted.add(last_x0)
            receipt.descriptor = dict(descriptor, strength=strength, protection_mode=mode,
                                      sampling_steps=len(schedule) - 1,
                                      attention_balance=float(balance) if balancing else None,
                                      attention_blocks=sorted(blocks) if balancing else None)
            receipt.complete = True
            return result
        finally:
            active_shapes[0] = None
            receipt.schedule = None
            ref_cache.clear()
            receipt.lock.release()

    m.set_model_unet_function_wrapper(evaluate)
    if use_post_cfg:
        m.set_model_sampler_post_cfg_function(post_cfg, disable_cfg1_optimization=False)
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
                         description='Sampler-level protection against darkening, color burn, saturation creep and '
                                     'edge halos across continuations and visual-memory cuts. Connect model to the '
                                     'guider, latent to the sampler and the returned segment to Save Segment. Turn off '
                                     'old Context noise. Protected sampling bypasses disk cache. No Context Windows.',
                         inputs=[io.Model.Input('model'), io.Latent.Input('latent'), SegmentType.Input('segment'),
                                 io.Boolean.Input('enabled', default=True),
                                 io.Float.Input('strength', default=DEFAULT_STRENGTH, min=0.0, max=1.0, step=0.05,
                                                optional=True,
                                                tooltip='Stabilization strength toward the clean scene anchor across '
                                                        'sampling steps (default 0.70; 0 disables latent stabilization).'),
                                 io.Combo.Input('mode', options=list(MODES), default='full', optional=True,
                                                tooltip="'full' (default) prevents darkening, color cast, contrast creep "
                                                        "and edge halos across multi-hop chains and visual-memory cuts. "
                                                        "'contrast_only' caps contrast/halo overshoot without pulling mean "
                                                        'exposure, useful when a continuation pans from dark into bright lighting.'),
                                 io.Float.Input('attention_balance', default=1.0, min=0.0, max=1000.0, step=0.1,
                                                optional=True,
                                                tooltip='Experimental (native attention only). 1 = unchanged.'),
                                 io.String.Input('attention_blocks', default=LIGHTING_BLOCKS, optional=True,
                                                 tooltip='Transformer blocks (0-49) attention_balance applies to.')],
                         outputs=[io.Model.Output(display_name='model'), io.Latent.Output(display_name='latent'),
                                  SegmentType.Output(display_name='segment'), io.String.Output(display_name='info')])

    @classmethod
    def execute(cls, model, latent, segment, enabled=True, strength=DEFAULT_STRENGTH, mode='full',
                attention_balance=1.0, attention_blocks=LIGHTING_BLOCKS):
        reason = 'Disabled.' if not enabled else passthrough_reason(segment)
        if reason:
            return io.NodeOutput(model, latent, segment, f'{WHO}: passed through. {reason}')
        blocks = parse_blocks(attention_blocks)
        owned = replace(segment, timeline=copy.deepcopy(segment.timeline),
                        protection_source=copy.deepcopy(segment.protection_source))
        front, capstone, descriptor = load_anchors(owned)
        if 'source' in (owned.protection_source or {}):
            anchor_video, anchor_offset = load_anchor_clip(owned, descriptor)
        else:
            anchor_video, anchor_offset = front, 0
        prepared, originals = prepare_latent(latent, owned, front)
        model, owned.protection_receipt = patch_model(
            model, prepared, owned, originals, capstone, descriptor,
            attention_balance, blocks,
            anchor_video=anchor_video, anchor_offset=anchor_offset,
            strength=strength, mode=mode)
        prepared[RECEIPT_KEY] = owned.protection_receipt
        mode_note = 'cut memory' if descriptor.get('mode') == 'cut_memory' else 'continuation'
        source_label = descriptor.get('source_index', descriptor.get('source_box', 'anchor'))
        message = (f'{WHO}: prepared ({mode_note}, anchor box {source_label}, '
                   f'mode {mode}, strength {float(strength):.2f}); sampler-level stabilization active. '
                   f'Disk sampling cache bypassed.')
        if hasattr(model.model_options.get('transformer_options', {}).get('optimized_attention_override'), 'h3c_balance'):
            message += f' Attention balance {attention_balance:g} on {len(blocks)} blocks.'
        return io.NodeOutput(model, prepared, owned, message)
