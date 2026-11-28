"""The frames a continuity check looks at, and the drift measures: the mean CIELAB colour and the fine-texture energy
of a box's frames against its scene's first box."""

import os

import av
import numpy as np

from . import media
from . import timeline as rules

LIGHTNESS_STEP = 4.5
COLOR_STEP = 8.0
TEXTURE_STEP = 0.25
TEXTURE_BANDS = ((2, 8), (8, 32), (32, 128))
HOLD_STEPS = 2
HOLD_RATIO = 0.35
HOLD_FLOOR = 2.0
VIGNETTE_THRESHOLD = 0.15
VIGNETTE_STEP = 0.08
CRACKLE_THRESHOLD = 0.006
CRACKLE_REF_WIDTH = 1024
CRACKLE_RATIO = 1.6
CRACKLE_FLOOR = 0.0015
SPEED_RATIO_HIGH = 2.0
SPEED_RATIO_LOW = 0.5
SPEED_MOTION_FLOOR = 1.0
SEAM_MOTION_FLOOR = 0.5
SEAM_FREEZE_FLOOR = 0.25
SEAM_FREEZE_RATIO = 0.20
MAX_SHOTS = 5
_SRGB_TO_XYZ = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                         [0.0193339, 0.1191920, 0.9503041]])
_WHITE = np.array([0.95047, 1.0, 1.08883])


def shot_starts(source):
    """The shots' start_ms of a box's saved source, or None when it has no shots or a start isn't a whole number."""
    reply = source.get("reply") if isinstance(source, dict) else None
    shots = reply.get("shots") if isinstance(reply, dict) else None
    if not isinstance(shots, list) or not shots:
        return None
    starts = [shot.get("start_ms") if isinstance(shot, dict) else None for shot in shots]
    return starts if all(type(value) is int for value in starts) else None


def picks(source, frames, carried):
    """(shot, frame) pairs for a box of `frames` frames whose first `carried` replay the box before; `frame` counts the
    frames after the replay. The middle of each shot after the replay, by the shot's number from 1 (more than 5 give
    5, evenly chosen), then the last frame as shot 0. Without a usable source, 3 evenly spaced frames after the
    replay, the last of them the last frame. Shot times count the replay, as the source's do."""
    own = frames - carried
    starts = shot_starts(source)
    if starts is None:
        return [(0, -(-own * k // 3) - 1) for k in (1, 2, 3)]
    replay, end = round(carried * 1000 / rules.FPS), round(frames * 1000 / rules.FPS)
    middles = []
    for number, start in enumerate(starts, 1):
        stop = starts[number] if number < len(starts) else end
        start = max(start, replay)
        if stop > start:
            middles.append((number, min(max((start + stop) * rules.FPS // 2000 - carried, 0), own - 1)))
    if len(middles) > MAX_SHOTS:
        span, steps = len(middles) - 1, MAX_SHOTS - 1
        middles = [middles[(2 * k * span + steps) // (2 * steps)] for k in range(MAX_SHOTS)]
    if not middles or middles[-1][1] != own - 1:
        middles.append((0, own - 1))
    return middles


def read(folder, entry, picks):
    """The frames of `picks` from the manifest entry's segment video, in order; frame numbers scale by the video's
    fps over 24. Raises ValueError when the video can't be read."""
    video = entry["video"]
    count = video.get("frames") or 1
    indices = [min(count - 1, round(frame * video["fps"] / rules.FPS)) for _, frame in picks]
    try:
        found = media.read_frames(os.path.join(folder, video["file"]), indices)
    except (OSError, av.error.FFmpegError) as error:
        raise ValueError(f"{video['file']} can't be read: {error}") from None
    return [found[index] for index in indices]


def _lab(frame):
    """The mean CIELAB colour (D65) of an sRGB frame's pixels."""
    rgb = frame.reshape(-1, 3).astype(np.float64) / 255.0
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = linear @ _SRGB_TO_XYZ.T / _WHITE
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1).mean(axis=0)


def lab_mean(frames):
    """The mean CIELAB colour (L, a, b) of `frames`: each frame's pixels averaged in CIELAB, then the frames."""
    return np.mean([_lab(frame) for frame in frames], axis=0)


def texture(frame):
    """Luma texture energy (RMS) in the TEXTURE_BANDS wavelengths, in pixels, after removing a linear lighting
    gradient under a Hann window. A port of PrefixStream's texture_band_rms; not a quality score."""
    rgb = frame[..., :3].astype(np.float64) / 255.0
    luma = rgb @ np.array([0.2126, 0.7152, 0.0722])
    h, w = luma.shape
    x, y = np.arange(w) - (w - 1) / 2, (np.arange(h) - (h - 1) / 2)[:, None]
    trend = luma.mean() + (luma * x).mean() / (x * x).mean() * x + (luma * y).mean() / (y * y).mean() * y
    window = np.hanning(h)[:, None] * np.hanning(w)
    power = np.abs(np.fft.fft2((luma - trend) * window)) ** 2
    radius = np.hypot(np.fft.fftfreq(h)[:, None], np.fft.fftfreq(w))
    norm = (h * w) ** 2 * (window ** 2).mean()
    return np.array([np.sqrt(power[(radius >= 1 / hi) & (radius < 1 / lo)].sum() / norm) for lo, hi in TEXTURE_BANDS])


def texture_mean(frames):
    return np.mean([texture(frame) for frame in frames], axis=0)


def drift_words(lab, first, texture=None, first_texture=None):
    """How the colour `lab` differs from its scene's first box's `first`: a shift of COLOR_STEP or more on the a*b*
    plane names its larger axis, and a lightness change of LIGHTNESS_STEP L* units or more reads in percent of the
    first box's lightness, as in "warmer and 12% darker"; "" below both. With textures, a rise of TEXTURE_STEP or more
    in the finest band adds "30% grainier". A drop is not named: motion blur in a moving shot lowers it too."""
    lightness, da, db = lab[0] - first[0], lab[1] - first[1], lab[2] - first[2]
    words = []
    if np.hypot(da, db) >= COLOR_STEP:
        words.append(("warmer" if db > 0 else "cooler") if abs(db) >= abs(da) else ("redder" if da > 0 else "greener"))
    if abs(lightness) >= LIGHTNESS_STEP:
        percent = round(abs(lightness) / max(first[0], 1.0) * 100)
        words.append(f"{percent}% {'brighter' if lightness > 0 else 'darker'}")
    if texture is not None and first_texture is not None and first_texture[0] > 0:
        change = texture[0] / first_texture[0] - 1
        if change >= TEXTURE_STEP - 1e-9:
            words.append(f"{round(change * 100)}% grainier")
    return " and ".join(words)


def _luma(frame):
    """Rec.709 luma in [0, 255] from an RGB(A) frame."""
    return frame[..., :3].astype(np.float64) @ np.array([0.2126, 0.7152, 0.0722])


def vignette_score(frame):
    """Symmetric 4-corner radial darkening score in [0, 1].

    Compares each pair of corners against their shared edge center while requiring corner falloff on at
    least one horizontal edge (top/bottom) AND at least one vertical edge (left/right), plus local edge-strip
    falloff. Returns 0.0 for flat frames, any linear lighting gradient, single-corner objects, centered edge
    highlights, and interior corridor walls, and >0 for symmetric radial corner vignetting.
    """
    y = _luma(frame)
    h, w = y.shape
    if h < 16 or w < 16:
        return 0.0
    ph, pw = max(4, h // 8), max(4, w // 8)
    tl, tr = y[:ph, :pw].mean(), y[:ph, -pw:].mean()
    bl, br = y[-ph:, :pw].mean(), y[-ph:, -pw:].mean()
    top_mid = y[:ph, w // 4:w - w // 4].mean()
    bot_mid = y[-ph:, w // 4:w - w // 4].mean()
    left_mid = y[h // 4:h - h // 4, :pw].mean()
    right_mid = y[h // 4:h - h // 4, -pw:].mean()

    def pair_drop(mid, c1, adj1, c2, adj2):
        if max(adj1 - c1, adj2 - c2) <= 0.0:
            return 0.0
        drop = min(mid - c1, mid - c2)
        return float(max(0.0, drop) / max(mid, 32.0))

    top_s = pair_drop(top_mid, tl, y[:ph, pw:2 * pw].mean(), tr, y[:ph, -2 * pw:-pw].mean())
    bot_s = pair_drop(bot_mid, bl, y[-ph:, pw:2 * pw].mean(), br, y[-ph:, -2 * pw:-pw].mean())
    left_s = pair_drop(left_mid, tl, y[ph:2 * ph, :pw].mean(), bl, y[-2 * ph:-ph, :pw].mean())
    right_s = pair_drop(right_mid, tr, y[ph:2 * ph, -pw:].mean(), br, y[-2 * ph:-ph, -pw:].mean())
    return float(min(max(top_s, bot_s), max(left_s, right_s)))


def vignette_mean(frames):
    return float(np.mean([vignette_score(frame) for frame in frames])) if frames else 0.0


def vignette_step(before_frames, after_frames):
    """Signed change in symmetric corner darkening from `before_frames` to `after_frames`."""
    return float(vignette_mean(after_frames) - vignette_mean(before_frames))


def _area_resize_2d(plane, gh, gw):
    """Area-average 2D float64 array `plane` to `(gh, gw)` via integral image (exact full-frame pooling)."""
    fh, fw = plane.shape
    if fh == gh and fw == gw:
        return plane
    row_edges = np.linspace(0, fh, gh + 1, dtype=int)
    col_edges = np.linspace(0, fw, gw + 1, dtype=int)
    row_idx = np.clip(row_edges[:-1], 0, fh - 1)
    row_end = np.maximum(row_edges[1:], row_idx + 1)
    col_idx = np.clip(col_edges[:-1], 0, fw - 1)
    col_end = np.maximum(col_edges[1:], col_idx + 1)
    cs = np.pad(plane, ((1, 0), (1, 0)), mode="constant").cumsum(axis=0).cumsum(axis=1)
    sums = (cs[row_end[:, None], col_end[None, :]] - cs[row_idx[:, None], col_end[None, :]]
            - cs[row_end[:, None], col_idx[None, :]] + cs[row_idx[:, None], col_idx[None, :]])
    areas = (row_end - row_idx)[:, None] * (col_end - col_idx)[None, :]
    return sums / areas


def crackle_score(frame):
    """High-frequency 2D Laplacian RMS measured on smooth image regions at a normalized reference width.

    Frames wider than CRACKLE_REF_WIDTH are area-downsampled first so upscaled grain/crackle clumps are
    measured on the same spatial scale as native renders. Flat frames, linear gradients, and crisp geometric
    edges score near 0; smooth-area grain/crackle spikes produce elevated scores.
    """
    y = _luma(frame) / 255.0
    h, w = y.shape
    if h < 6 or w < 6:
        return 0.0
    if w > CRACKLE_REF_WIDTH:
        th = max(6, round(h * CRACKLE_REF_WIDTH / w))
        y = _area_resize_2d(y, th, CRACKLE_REF_WIDTH)
    smooth = (y[:-2, :-2] + y[:-2, 1:-1] + y[:-2, 2:]
              + y[1:-1, :-2] + y[1:-1, 1:-1] + y[1:-1, 2:]
              + y[2:, :-2] + y[2:, 1:-1] + y[2:, 2:]) / 9.0
    gx = np.abs(smooth[1:-1, 2:] - smooth[1:-1, :-2]) * 0.5
    gy = np.abs(smooth[2:, 1:-1] - smooth[:-2, 1:-1]) * 0.5
    grad = gx + gy
    lap = y[2:-2, 2:-2] - 0.25 * (y[1:-3, 2:-2] + y[3:-1, 2:-2] + y[2:-2, 1:-3] + y[2:-2, 3:-1])
    cutoff = max(0.015, float(np.percentile(grad, 35)))
    mask = grad <= cutoff
    sample = lap[mask] if mask.any() else lap
    return float(np.sqrt(np.mean(sample ** 2)))


def crackle_mean(frames):
    return float(np.mean([crackle_score(frame) for frame in frames])) if frames else 0.0


def adjacent_luma_step(before_frames, after_frames, *, fps=None):
    """Signed CIELAB L* jump from `before_frames` (previous box end) to `after_frames` (current box start).

    When multiple `after_frames` are given, scans the first ~167 ms ramp window (`round(4 * fps / 24)` frames)
    and returns the peak signed L* delta against the end of `before_frames` so 48 fps post-seam ramps are
    captured without dilution.
    """
    if not before_frames or not after_frames:
        return 0.0
    base_l = float(lab_mean(before_frames[-min(len(before_frames), 2):])[0])
    if len(after_frames) == 1:
        return float(_lab(after_frames[0])[0] - base_l)
    scale = max(1.0, float(fps or rules.FPS) / rules.FPS)
    window = max(1, min(len(after_frames), round(4 * scale)))
    deltas = [float(_lab(frame)[0] - base_l) for frame in after_frames[:window]]
    return max(deltas, key=abs)


def _to_common_grid(frame, gh, gw):
    """Area-average RGB(A) `frame` to grayscale `(gh, gw)` via integral image (handles mixed resolutions without cropping)."""
    return _area_resize_2d(frame[..., :3].astype(np.float64).mean(axis=2), gh, gw)


def _block_steps(frames, *, zero_mean=False):
    """Consecutive greyscale block-mean absolute differences (about 240 px wide), safe for tiny or mixed-resolution frames.

    With `zero_mean=True`, subtracts each frame's spatial mean luma before differencing so pure exposure ramps
    do not inflate measured spatial motion.
    """
    if len(frames) < 2:
        return np.array([], dtype=np.float64)
    shapes = {frame.shape[:2] for frame in frames}
    if len(shapes) == 1:
        fh, fw = next(iter(shapes))
        if fh == 0 or fw == 0:
            return np.array([], dtype=np.float64)
        k = max(1, min(fw // 240 or 1, fh, fw))
        h, w = fh // k * k, fw // k * k
        small = np.array([frame[:h, :w, :3].mean(axis=2).reshape(h // k, k, w // k, k).mean(axis=(1, 3))
                          for frame in frames])
    else:
        min_h = min(frame.shape[0] for frame in frames)
        min_w = min(frame.shape[1] for frame in frames)
        if min_h == 0 or min_w == 0:
            return np.array([], dtype=np.float64)
        gw = max(1, min(240, min_w))
        gh = max(1, min(round(gw * frames[0].shape[0] / max(frames[0].shape[1], 1)), min_h))
        small = np.array([_to_common_grid(frame, gh, gw) for frame in frames])
    if zero_mean:
        small = small - small.mean(axis=(1, 2), keepdims=True)
    return np.abs(np.diff(small, axis=0)).mean(axis=(1, 2))


def holds(frames):
    """(first frame, frames held) for each run of at least HOLD_STEPS consecutive frame steps whose mean absolute
    difference (greyscale block means, about 240 px wide) is below HOLD_RATIO of the clip's median step; [] for a static shot,
    whose median step is below HOLD_FLOOR."""
    steps = _block_steps(frames)
    if not len(steps) or np.median(steps) < HOLD_FLOOR:
        return []
    still = np.append(steps < HOLD_RATIO * np.median(steps), False)
    found, start = [], None
    for index, value in enumerate(still):
        if value and start is None:
            start = index
        elif not value and start is not None:
            if index - start >= HOLD_STEPS:
                found.append((start, index - start + 1))
            start = None
    return found


def seam_freeze(before_tail, after_head, *, fps=None, before_fps=None, after_fps=None):
    """Detect a 1-step duplicate or freeze at the seam between `before_tail` and `after_head` at native FPS.

    Normalizes per-frame motion to 24 fps step equivalents when `fps` or `before_fps`/`after_fps` are given so
    48 fps interpolated clips are not dropped below the motion floor. Catches single-frame last-frame
    duplicates, exact seam repeats, or first-frame head stalls while ignoring genuinely static shots.
    """
    if not before_tail or not after_head:
        return {"frozen": False, "seam_diff": 0.0, "tail_duplicate": False, "seam_duplicate": False,
                "head_duplicate": False, "ref_motion": 0.0}
    if fps is not None:
        before_fps = before_fps or fps
        after_fps = after_fps or fps
    scale_b = float(before_fps or rules.FPS) / rules.FPS
    scale_a = float(after_fps or rules.FPS) / rules.FPS
    scale_seam = 0.5 * (scale_b + scale_a)
    before_steps = _block_steps(before_tail) * scale_b
    after_steps = _block_steps(after_head) * scale_a
    seam_diff_raw = float(_block_steps([before_tail[-1], after_head[0]])[0])
    seam_diff = seam_diff_raw * scale_seam
    interior = np.concatenate([
        before_steps[:-1] if len(before_steps) >= 2 else before_steps,
        after_steps[1:] if len(after_steps) >= 2 else after_steps,
    ])
    ref_motion = float(np.median(interior)) if len(interior) else 0.0
    if ref_motion < SEAM_MOTION_FLOOR:
        return {"frozen": False, "seam_diff": round(seam_diff_raw, 3), "tail_duplicate": False,
                "seam_duplicate": False, "head_duplicate": False, "ref_motion": round(ref_motion, 3)}
    cutoff = max(SEAM_FREEZE_FLOOR, SEAM_FREEZE_RATIO * ref_motion)
    tail_duplicate = bool(len(before_steps) and before_steps[-1] < cutoff)
    seam_duplicate = bool(seam_diff < cutoff)
    head_duplicate = bool(len(after_steps) and after_steps[0] < cutoff)
    return {
        "frozen": bool(tail_duplicate or seam_duplicate or head_duplicate),
        "seam_diff": round(seam_diff_raw, 3),
        "tail_duplicate": tail_duplicate,
        "seam_duplicate": seam_duplicate,
        "head_duplicate": head_duplicate,
        "ref_motion": round(ref_motion, 3),
    }


def motion_speed_ratio(before_tail, after_head, *, before_fps=None, after_fps=None):
    """Compare native-FPS exit motion velocity of Box N-1 against entry motion velocity of Box N.

    Subtracts per-frame mean luma before computing block diffs so pure exposure ramps do not inflate
    motion, normalizes per-frame differences to 24 fps step equivalents, and flags jumps outside
    (SPEED_RATIO_LOW, SPEED_RATIO_HIGH) on moving seams.
    """
    before_steps = _block_steps(before_tail, zero_mean=True)
    after_steps = _block_steps(after_head, zero_mean=True)
    if not len(before_steps) or not len(after_steps):
        return {"v_before": 0.0, "v_after": 0.0, "ratio": 1.0, "flagged": False}
    scale_before = float(before_fps or rules.FPS) / rules.FPS
    scale_after = float(after_fps or rules.FPS) / rules.FPS
    v_before = float(np.median(before_steps)) * scale_before
    v_after = float(np.median(after_steps)) * scale_after
    if max(v_before, v_after) < SPEED_MOTION_FLOOR:
        return {"v_before": round(v_before, 3), "v_after": round(v_after, 3), "ratio": 1.0, "flagged": False}
    ratio = v_after / max(v_before, 0.25)
    flagged = bool(ratio >= SPEED_RATIO_HIGH or ratio <= SPEED_RATIO_LOW)
    return {"v_before": round(v_before, 3), "v_after": round(v_after, 3),
            "ratio": round(float(ratio), 3), "flagged": flagged}


def hold_records(found, joined):
    """checks.json entries for `found` holds. With `joined`, frame 0 is the previous box's last frame, so a hold
    starting there is at the join and later frames count from the box's first played frame."""
    return [{"start_ms": round(max(0, first - joined) * 1000 / rules.FPS), "frames": count,
             "join": bool(joined and first == 0)} for first, count in found]


def scene_start(timeline, index):
    """The index of the box that starts box `index`'s scene: the nearest one at or before it that cuts to a new
    scene, else box 1."""
    while index > 0 and not (timeline.boxes[index].cut and timeline.boxes[index].new_scene):
        index -= 1
    return index
