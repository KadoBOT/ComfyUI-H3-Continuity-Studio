"""Read-only CPU measurements; none is a perceptual quality verdict."""

import numpy as np
import torch

STALE_OVERLAP_MAD = 0.05
_BT709 = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _frame_luma_2d(frame):
    arr = np.asarray(frame, dtype=np.float32)
    rgb = arr[..., :3]
    if rgb.shape[-1] == 1:
        return rgb[..., 0]
    return rgb @ _BT709


def _frame_block_luma(frame):
    """~240 px wide block-averaged grayscale frame in float32, suppressing pixel-level codec shimmer."""
    luma = _frame_luma_2d(frame)
    h, w = luma.shape[0], luma.shape[1]
    k = max(1, w // 240)
    bh, bw = max(1, h // k) * k, max(1, w // k) * k
    if bh > h or bw > w:
        return luma
    return luma[:bh, :bw].reshape(bh // k, k, bw // k, k).mean(axis=(1, 3))


def _frame_vignette_drop(frame):
    """4-corner darkening relative to adjacent mid-edges for a single frame (positive = darker corners)."""
    luma = _frame_luma_2d(frame)
    h, w = luma.shape[0], luma.shape[1]
    ph, pw = max(1, h // 8), max(1, w // 8)
    corners = (
        float(luma[:ph, :pw].mean(dtype=np.float64))
        + float(luma[:ph, w - pw:].mean(dtype=np.float64))
        + float(luma[h - ph:, :pw].mean(dtype=np.float64))
        + float(luma[h - ph:, w - pw:].mean(dtype=np.float64))
    ) * 0.25
    if h >= 4 and w >= 4 and h > 2 * ph and w > 2 * pw:
        top_bot = (float(luma[:ph, pw:w - pw].sum(dtype=np.float64))
                   + float(luma[h - ph:, pw:w - pw].sum(dtype=np.float64)))
        left_right = (float(luma[ph:h - ph, :pw].sum(dtype=np.float64))
                      + float(luma[ph:h - ph, w - pw:].sum(dtype=np.float64)))
        edge_pixels = 2 * ph * (w - 2 * pw) + 2 * (h - 2 * ph) * pw
        edges = (top_bot + left_right) / edge_pixels
    else:
        edges = float(luma.mean(dtype=np.float64))
    return float(edges - corners)


def _vignette_drop(frames):
    """Mean 4-corner darkening relative to adjacent mid-edges (positive = darker corners)."""
    return float(np.mean([_frame_vignette_drop(frame) for frame in frames]))


def _pair_mae(a, b):
    """Exact 1:1 mean absolute pixel difference between two frames without allocating full-clip float64 stacks."""
    arr_a, arr_b = np.asarray(a), np.asarray(b)
    if arr_a.dtype == np.uint8 and arr_b.dtype == np.uint8:
        return float(np.abs(arr_b.astype(np.int16) - arr_a.astype(np.int16)).mean(dtype=np.float64))
    return float(np.abs(arr_b.astype(np.float32) - arr_a.astype(np.float32)).mean(dtype=np.float64))


def _unavailable_video(reason):
    return {"status": "unavailable", "reason": reason,
            "boundary_frame_mae": None, "nearby_frame_mae": [], "boundary_index": None,
            "boundary_luma_step": None, "ramp_luma_step": None, "ramp_luma_profile": [],
            "tail_step_mae": None, "duplicate_tail": False, "seam_freeze": False,
            "join_pop_ratio": None, "before_motion": None, "after_motion": None, "speed_ratio": None,
            "contrast_drop_ratio": None, "seam_flash": False,
            "before_vignette": None, "after_vignette": None, "vignette_delta": None}


def video_join(before, after, *, fps=24.0):
    fps_scale = max(1.0, float(fps or 24.0) / 24.0)
    ramp_window = max(4, round(4 * fps_scale))
    side_cap = max(12, ramp_window)
    before_seq = [np.asarray(frame) for frame in before[-side_cap:]]
    after_seq = [np.asarray(frame) for frame in after[:side_cap]]
    if not before_seq or not after_seq:
        return _unavailable_video("Both sides need a delivered frame.")
    shape = before_seq[0].shape
    if any(frame.shape != shape for frame in before_seq) or any(frame.shape != shape for frame in after_seq):
        return _unavailable_video("Delivered frame geometry differs across this cut.")
    all_seq = before_seq + after_seq
    for frame in all_seq:
        if np.issubdtype(frame.dtype, np.floating) and not np.isfinite(frame).all():
            return _unavailable_video("Video contains non-finite values.")

    # Compute pairwise MAEs one pair at a time to keep peak RAM small on 3K/4K clips.
    before_steps = np.array([_pair_mae(before_seq[i], before_seq[i + 1]) for i in range(len(before_seq) - 1)],
                            dtype=np.float64)
    after_steps = np.array([_pair_mae(after_seq[i], after_seq[i + 1]) for i in range(len(after_seq) - 1)],
                           dtype=np.float64)
    join_step = _pair_mae(before_seq[-1], after_seq[0])

    near_before = min(6, len(before_seq))
    near_after = min(6, len(after_seq))
    near_before_steps = before_steps[-(near_before - 1):].tolist() if near_before > 1 else []
    near_after_steps = after_steps[:near_after - 1].tolist() if near_after > 1 else []
    nearby_steps = near_before_steps + [join_step] + near_after_steps
    boundary = near_before - 1

    # Infer unit scale so thresholds work identically on uint8 [0..255] and float [0..1] inputs.
    is_float_unit = (all(np.issubdtype(frame.dtype, np.floating) for frame in all_seq)
                     and max(float(frame.max()) for frame in all_seq) <= 1.0 + 1e-6)
    unit = (1.0 / 255.0) if is_float_unit else 1.0

    # Block-averaged (~240 px) luma per frame: tiny footprint, used for luma steps and motion speed.
    before_blk = np.stack([_frame_block_luma(frame) for frame in before_seq], axis=0)
    after_blk = np.stack([_frame_block_luma(frame) for frame in after_seq], axis=0)
    before_luma_last = float(_frame_luma_2d(before_seq[-1]).mean(dtype=np.float64))
    ramp_count = min(ramp_window, len(after_seq))
    after_ramp_luma = np.array([float(_frame_luma_2d(frame).mean(dtype=np.float64)) for frame in after_seq[:ramp_count]],
                               dtype=np.float64)
    boundary_luma_step = float(after_ramp_luma[0] - before_luma_last)
    ramp = after_ramp_luma - before_luma_last
    ramp_profile = [float(v) for v in ramp]
    ramp_luma_step = float(ramp[int(np.argmax(np.abs(ramp)))])

    tail_step_mae = float(before_steps[-1]) if len(before_steps) else None
    med_after = float(np.median(after_steps)) if len(after_steps) else 0.0
    if len(before_steps) >= 2:
        prev_motion = float(np.median(before_steps[:-1]))
    elif len(before_steps) == 1:
        prev_motion = max(med_after, join_step)
    else:
        prev_motion = 0.0
    duplicate_tail = bool(
        tail_step_mae is not None
        and prev_motion >= 0.5 * unit
        and tail_step_mae <= min(0.5 * unit, 0.15 * prev_motion)
    )

    if len(before_steps) >= 2 and duplicate_tail:
        med_before = float(np.median(before_steps[:-1]))
    elif len(before_steps):
        med_before = float(np.median(before_steps))
    else:
        med_before = 0.0
    baseline = max(med_before, med_after)
    join_pop_ratio = float(join_step / baseline) if baseline > 1e-6 else None
    seam_freeze = bool(
        duplicate_tail
        or (baseline >= 0.5 * unit and (
            join_step <= 0.25 * baseline
            or (len(after_steps) >= 1 and float(after_steps[0]) <= 0.25 * baseline)
        ))
    )

    before_blk_steps = (np.abs(np.diff(before_blk, axis=0)).mean(axis=(1, 2), dtype=np.float64)
                        if len(before_blk) > 1 else np.array([], dtype=np.float64))
    after_blk_steps = (np.abs(np.diff(after_blk, axis=0)).mean(axis=(1, 2), dtype=np.float64)
                       if len(after_blk) > 1 else np.array([], dtype=np.float64))
    if duplicate_tail and len(before_blk_steps) >= 2:
        before_blk_steps = before_blk_steps[:-1]
    before_motion = float(np.median(before_blk_steps)) if len(before_blk_steps) else None
    after_motion = float(np.median(after_blk_steps)) if len(after_blk_steps) else None
    speed_ratio = (float(after_motion / before_motion)
                   if before_motion is not None and after_motion is not None and before_motion > 1e-6 else None)

    before_vig = _vignette_drop(before_seq[-4:])
    after_vig = _vignette_drop(after_seq[:4])
    vignette_delta = float(after_vig - before_vig)

    std_before = float(np.asarray(before_seq[-1], dtype=np.float32).std()) / unit
    std_after0 = float(np.asarray(after_seq[0], dtype=np.float32).std()) / unit
    std_after_settle = float(np.asarray(after_seq[min(3, len(after_seq) - 1)], dtype=np.float32).std()) / unit
    std_ref = min(std_before, std_after_settle)
    contrast_drop_ratio = float(std_after0 / std_ref) if std_ref >= 15.0 else None
    seam_flash = bool(contrast_drop_ratio is not None and contrast_drop_ratio < 0.70)

    return {
        "status": "ok",
        "boundary_frame_mae": join_step,
        "nearby_frame_mae": nearby_steps,
        "boundary_index": boundary,
        "boundary_luma_step": boundary_luma_step,
        "ramp_luma_step": ramp_luma_step,
        "ramp_luma_profile": ramp_profile,
        "tail_step_mae": tail_step_mae,
        "duplicate_tail": duplicate_tail,
        "seam_freeze": seam_freeze,
        "join_pop_ratio": join_pop_ratio,
        "before_motion": before_motion,
        "after_motion": after_motion,
        "speed_ratio": speed_ratio,
        "contrast_drop_ratio": contrast_drop_ratio,
        "seam_flash": seam_flash,
        "before_vignette": before_vig,
        "after_vignette": after_vig,
        "vignette_delta": vignette_delta,
    }


def audio_join(before, after, sample_rate):
    result = {"status": "unavailable", "before_rms": None, "after_rms": None, "rms_step_db": None,
              "sample_jump": None, "before_samples": 0, "after_samples": 0}
    if before is None or after is None or sample_rate is None or sample_rate <= 0:
        return {**result, "reason": "Both saved waveforms and a common sample rate are required."}
    count = max(1, round(sample_rate * 0.5))
    before, after = np.asarray(before[:, -count:], dtype=np.float64), np.asarray(after[:, :count], dtype=np.float64)
    result.update(before_samples=before.shape[-1], after_samples=after.shape[-1])
    if not before.size or not after.size:
        return {**result, "reason": "An audio side is empty."}
    if not np.isfinite(before).all() or not np.isfinite(after).all():
        return {**result, "reason": "Audio contains non-finite values."}
    a, b = float(np.sqrt(np.mean(before ** 2))), float(np.sqrt(np.mean(after ** 2)))
    result.update(before_rms=a, after_rms=b, sample_jump=float(np.abs(after[:, 0] - before[:, -1]).mean()))
    if a == 0 or b == 0:
        return {**result, "status": "partial", "reason": "Zero-energy audio has no finite level ratio."}
    result["rms_step_db"] = float(20 * np.log10(b / a))
    if min(before.shape[-1], after.shape[-1]) < count:
        return {**result, "status": "partial", "reason": "Less than 500 ms is available on a side."}
    return {**result, "status": "ok"}


def overlap_lag(reference, replay, sample_rate):
    """Positive delay means replay is delayed; only compare the same known source interval."""
    result = {"status": "unavailable", "delay_samples": None, "delay_ms": None,
              "correlation": None, "windows": 0}
    if sample_rate <= 0:
        return {**result, "reason": "A positive sample rate is required."}
    reference, replay = np.asarray(reference, dtype=np.float64), np.asarray(replay, dtype=np.float64)
    channels = max(reference.shape[0], replay.shape[0])
    reference, replay = np.broadcast_to(reference, (channels, reference.shape[-1])), np.broadcast_to(replay, (channels, replay.shape[-1]))
    window, hop = max(1, round(sample_rate * 0.05)), max(1, round(sample_rate * 0.025))
    limit = round(sample_rate * 0.04)
    stop = min(reference.shape[-1], replay.shape[-1]) - window - limit
    if stop < limit:
        return {**result, "reason": "Not enough known overlap for the window and lag search."}
    if not np.isfinite(reference).all() or not np.isfinite(replay).all():
        return {**result, "reason": "Known overlap contains non-finite values."}
    profiles = []
    for start in range(limit, stop + 1, hop):
        anchor = reference[:, start:start + window]
        anchor = anchor - anchor.mean(axis=-1, keepdims=True)
        anchor_energy = float(np.square(anchor).sum())
        if anchor_energy <= 1e-20:
            continue
        search = replay[:, start - limit:start + window + limit]
        sums = np.pad(np.cumsum(search, axis=-1), ((0, 0), (1, 0)))
        squares = np.pad(np.cumsum(np.square(search), axis=-1), ((0, 0), (1, 0)))
        means = sums[:, window:] - sums[:, :-window]
        energy = (squares[:, window:] - squares[:, :-window] - means ** 2 / window).sum(axis=0)
        norm = np.sqrt(anchor_energy * np.maximum(energy, 0))
        numerator = sum(np.correlate(row, template, mode="valid") for row, template in zip(search, anchor))
        correlation = np.divide(numerator, norm, out=np.zeros_like(numerator), where=norm > 1e-20)
        profiles.append(np.clip(correlation, -1, 1))
    result["windows"] = len(profiles)
    if not profiles:
        return {**result, "reason": "Known overlap has no usable energy."}
    scores = np.mean(profiles, axis=0)
    best = int(np.argmax(scores))
    score = float(scores[best])
    result["correlation"] = score
    if score < 0.8:
        return {**result, "reason": "Correlation is too weak to establish a lag."}
    separate = np.abs(np.arange(len(scores)) - best) >= max(1, round(sample_rate * 0.005))
    if np.any(scores[separate] >= score - 0.02):
        return {**result, "status": "ambiguous", "reason": "Competing lag peaks; periodic content cannot establish alignment."}
    delay = best - limit
    return {**result, "status": "ok", "delay_samples": delay, "delay_ms": 1000 * delay / sample_rate}


def phase_drift(previous, current, carried_tokens, *, ending_tokens=0):
    previous, current = previous.detach().cpu().float(), current.detach().cpu().float()
    pairs = []
    for phase in range(5):
        source = list(range(phase, previous.shape[2], 5))
        target = [i for i in range(carried_tokens, current.shape[2] - ending_tokens) if i % 5 == phase]
        if not source or not target:
            continue
        a = previous[0, :, source[-1]].flatten(1)
        b = current[0, :, target[0]].flatten(1)
        if not torch.isfinite(a).all() or not torch.isfinite(b).all():
            return {"status": "unavailable", "pairs": [], "reason": "Compared latent rows contain non-finite values."}
        pairs.append({"phase": phase, "source_token": source[-1], "target_token": target[0],
                      "mean_delta": float((b.mean(dim=1) - a.mean(dim=1)).abs().mean()),
                      "spread_delta": float((b.std(dim=1, unbiased=False) - a.std(dim=1, unbiased=False)).abs().mean())})
    return {"status": "ok" if pairs else "unavailable", "pairs": pairs,
            **({} if pairs else {"reason": "No free matching-phase token pair is available."})}


def latent_overlap_mismatch(previous, current, carried_tokens, *, threshold=STALE_OVERLAP_MAD):
    """Compare the carried video tokens of `current` (`[:carried_tokens]`) against the exit tail of `previous`
    (`[-carried_tokens:]`) to detect stale continuations whose predecessor was re-rendered."""
    tokens = int(carried_tokens or 0)
    base = {"status": "unavailable", "carried_tokens": tokens, "overlap_mad": None, "overlap_max": None, "stale": False}
    if tokens <= 0:
        return {**base, "reason": "No carried tokens to compare."}
    if previous is None or current is None:
        return {**base, "reason": "Both video latents are required."}
    prev = previous.detach().cpu().float()
    curr = current.detach().cpu().float()
    if prev.ndim != 5 or curr.ndim != 5 or prev.shape[1] != curr.shape[1] or prev.shape[3:] != curr.shape[3:]:
        return {**base, "reason": "Latent geometry differs across this continuation."}
    if prev.shape[2] < tokens or curr.shape[2] < tokens:
        return {**base, "reason": "Latents are shorter than the carried overlap."}
    a = prev[0, :, -tokens:]
    b = curr[0, :, :tokens]
    if not torch.isfinite(a).all() or not torch.isfinite(b).all():
        return {**base, "reason": "Compared overlap latents contain non-finite values."}
    diff = (b - a).abs()
    mad = float(diff.mean().item())
    peak = float(diff.max().item())
    return {"status": "ok", "carried_tokens": tokens, "overlap_mad": mad, "overlap_max": peak,
            "stale": bool(mad > float(threshold))}
