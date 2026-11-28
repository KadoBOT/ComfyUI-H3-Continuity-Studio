"""Segment videos and full-movie assembly with PyAV."""

import datetime
import math
import os
from fractions import Fraction

import av
import numpy as np
import torch

from comfy_api.latest._input_impl.video_types import set_video_color_properties, video_stream_color_space

from .timing import sample_at_frame

AUDIO_BIT_RATE = 192000
CROSSFADE_SECONDS = 0.1
EXIT_MOTION_THRESHOLD = 1.5
OVERLAP_EXPOSURE_GAIN_MIN = 0.88
OVERLAP_EXPOSURE_GAIN_MAX = 1.12
OVERLAP_EXPOSURE_DECAY_SECONDS = 1.0
OVERLAP_MAX_ALIGNED_MAD = 0.12
OVERLAP_MAX_RAW_MAD = 0.25
_BT709 = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
_BT2020 = np.array([0.2627, 0.6780, 0.0593], dtype=np.float32)


def _layout(channels):
    return "mono" if channels == 1 else "stereo"


def window_at_fps(first, count, fps):
    """A window of `count` frames from `first` on the 24 fps timeline, as frame numbers in a video saved at `fps`
    (interpolated segments hold more frames per timeline frame). Both ends are rounded, so rounding never accumulates."""
    if not fps or fps == 24:
        return first, count
    start = round(first * fps / 24)
    return start, max(1, round((first + count) * fps / 24) - start)


def fit_frame_count(images, count):
    """Drop extra frames or repeat the last one so `images` has exactly `count` frames."""
    if images.shape[0] >= count:
        return images[:count]
    return torch.cat([images, images[-1:].expand(count - images.shape[0], -1, -1, -1)])


def _fps_multiplier(fps):
    """Integer interpolation factor relative to 24 fps when `fps` is an integer multiple of 24, else 1."""
    if not fps or float(fps) <= 24.0 + 1e-3:
        return 1
    ratio = float(fps) / 24.0
    nearest = round(ratio)
    return max(1, nearest) if abs(ratio - nearest) < 1e-2 else 1


def _native_tail_indices(count, fps, tail_frames=6):
    """Up to `tail_frames` frame indices spaced on the 24 fps clock at the end of a `count`-frame clip at `fps`
    (skipping trailing duplicate padding frames on integer-multiplied streams such as 48/72 fps)."""
    if count <= 1:
        return list(range(count))
    rate = float(fps or 24.0)
    mult = _fps_multiplier(rate)
    if mult > 1:
        return list(range(0, count, mult))[-tail_frames:]
    if rate > 24.0 + 1e-3:
        total_24 = max(2, int(round(count * 24.0 / rate)))
        start_24 = max(0, total_24 - tail_frames)
        return [min(count - 1, int(round(i * rate / 24.0))) for i in range(start_24, total_24)]
    return list(range(max(0, count - tail_frames), count))


def exit_motion_score(images, fps=24.0, tail_frames=6):
    """Median block-averaged luma frame diff (0..255 scale) over the last ~`tail_frames` native-24fps frames."""
    if images is None:
        return 0.0
    count = int(images.shape[0]) if hasattr(images, "shape") else len(images)
    if count < 2:
        return 0.0
    indices = _native_tail_indices(count, fps, tail_frames)
    if len(indices) < 2:
        return 0.0
    if isinstance(images, torch.Tensor):
        sample = images[indices, ..., :3].detach().float().cpu().numpy()
        scale = 255.0 if float(sample.max()) <= 1.0 + 1e-6 else 1.0
        sample = sample * scale
    else:
        arr = np.asarray([images[i] for i in indices], dtype=np.float32)[..., :3]
        raw_dtype = np.asarray(images[indices[0]]).dtype
        scale = 255.0 if (np.issubdtype(raw_dtype, np.floating) and float(arr.max()) <= 1.0 + 1e-6) else 1.0
        sample = arr * scale
    luma = sample @ _BT709 if sample.shape[-1] >= 3 else sample[..., 0]
    h, w = luma.shape[1], luma.shape[2]
    k = max(1, w // 240)
    bh, bw = max(1, h // k) * k, max(1, w // k) * k
    small = (luma[:, :bh, :bw].reshape(luma.shape[0], bh // k, k, bw // k, k).mean(axis=(2, 4))
             if bh <= h and bw <= w else luma)
    steps = np.abs(np.diff(small, axis=0)).mean(axis=(1, 2))
    return float(np.median(steps)) if len(steps) else 0.0


def read_tail_exit_motion(folder, entry, tail_frames=6):
    """Fallback exit-motion measurement directly from `entry`'s saved segment video, or None if unavailable."""
    video = (entry or {}).get("video")
    if not isinstance(video, dict) or not video.get("file"):
        return None
    path = os.path.join(folder, video["file"])
    if not os.path.isfile(path):
        return None
    try:
        fps = float(video.get("fps") or 24.0)
        count = int(video.get("frames") or 0) or _source_frames(path, 0, None)
        if count < 2:
            return 0.0
        indices = _native_tail_indices(count, fps, tail_frames)
        if len(indices) < 2:
            return 0.0
        found = read_frames(path, indices)
        frames = np.stack([found[i] for i in indices], axis=0)
        return exit_motion_score(frames, fps=24.0, tail_frames=len(frames))
    except (OSError, ValueError, av.error.FFmpegError):
        return None


# Delivery codecs of saved videos. H.264 plays everywhere; HEVC (Main10 for HDR, tagged hvc1) is what phones
# decode in hardware for 10-bit HDR and what Apple players need to show HLG.
CODECS = {"H.264": "libx264", "HEVC": "libx265"}
CODEC_OF_STREAM = {"h264": "H.264", "hevc": "HEVC"}


def video_codec(path):
    """The CODECS name of the video at `path`; H.264 for anything else."""
    with av.open(path) as container:
        return CODEC_OF_STREAM.get(container.streams.video[0].codec_context.name, "H.264")


def _add_video_stream(container, fps, width, height, crf, color_space="sRGB", codec="H.264"):
    if codec not in CODECS:
        raise ValueError(f"Unknown video codec {codec!r}; choose one of {', '.join(CODECS)}.")
    stream = container.add_stream(CODECS[codec], rate=Fraction(fps).limit_denominator(1001))
    stream.width, stream.height = width, height
    stream.pix_fmt = "yuv420p10le" if color_space in ("HDR", "HDR PQ") else "yuv420p"
    set_video_color_properties(stream.codec_context, color_space)
    stream.options = {"crf": str(crf), "preset": "medium"}
    if codec == "HEVC":
        stream.codec_tag = "hvc1"
        stream.options["x265-params"] = "log-level=error:bframes=0"
    # decode order must equal presentation order so segments can be joined by packet copy
    stream.codec_context.max_b_frames = 0
    return stream


def _add_audio_stream(container, waveform, sample_rate):
    stream = container.add_stream("aac", rate=sample_rate, layout=_layout(waveform.shape[0]))
    stream.bit_rate = AUDIO_BIT_RATE
    return stream


def _mux_audio(container, stream, waveform, sample_rate):
    frame = av.AudioFrame.from_ndarray(np.ascontiguousarray(waveform.float().cpu().numpy()), format="fltp",
                                       layout=_layout(waveform.shape[0]))
    frame.sample_rate = sample_rate
    frame.pts = 0
    container.mux(stream.encode(frame))
    container.mux(stream.encode(None))


def write_segment_video(path, images, fps, crf, audio=None, color_space="sRGB", size=None, codec="H.264"):
    """Encode `images` ([N, H, W, C], 0-1) with optional `audio` = (waveform [C, S], sample_rate) in `codec`
    (a CODECS name). Returns the encoded (width, height); odd sizes are padded by one edge pixel, unless
    `size` = (width, height) scales every frame to it."""
    height, width = images.shape[1], images.shape[2]
    pad_h, pad_w = (0, 0) if size else (height % 2, width % 2)
    out_width, out_height = size or (width + pad_w, height + pad_h)
    hdr = color_space in ("HDR", "HDR PQ")
    with av.open(path, mode="w") as container:
        video_stream = _add_video_stream(container, fps, out_width, out_height, crf, color_space, codec)
        audio_stream = _add_audio_stream(container, *audio) if audio is not None else None
        for image in images:
            array = (image[..., :3].float().clamp(0, 1) * (65535 if hdr else 255)).round().cpu().numpy().astype(np.uint16 if hdr else np.uint8)
            if pad_h or pad_w:
                array = np.pad(array, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
            frame = av.VideoFrame.from_ndarray(array, format="rgb48le" if hdr else "rgb24")
            frame = frame.reformat(width=out_width, height=out_height, format=video_stream.pix_fmt,
                                   dst_colorspace=video_stream.codec_context.colorspace)
            set_video_color_properties(frame, color_space)
            container.mux(video_stream.encode(frame))
        container.mux(video_stream.encode(None))
        if audio_stream is not None:
            _mux_audio(container, audio_stream, *audio)
    return out_width, out_height


def read_frames(path, indices):
    """The frames at `indices` of the video at `path`, as RGB uint8 arrays by index, decoded in order up to the last
    one wanted. An index past the end gets the last frame."""
    wanted = set(indices)
    end = max(wanted)
    found, last = {}, None
    with av.open(path) as container:
        for number, frame in enumerate(container.decode(video=0)):
            if number in wanted:
                found[number] = frame.to_ndarray(format="rgb24")
            if number >= end:
                break
            last = frame
        if wanted - found.keys():
            if last is None:
                raise ValueError(f"{os.path.basename(path)} has no frames")
            final = last.to_ndarray(format="rgb24")
            found.update({index: final for index in wanted - found.keys()})
    return found


def assemble_audio(parts, crossfade_seconds=CROSSFADE_SECONDS):
    """Join segment audio on the 24 fps timeline.

    `parts` holds (frames, context_frames, waveform [C, S] or None, sample_rate or None) per segment.
    Each segment fills the span of its new frames from its own waveform, starting after its carried
    frames, and fades in over the end of the previous segment from its own decode of that moment.
    Returns (waveform, sample_rate), or None when no segment has audio."""
    with_audio = [(waveform, rate) for _, _, waveform, rate in parts if waveform is not None]
    if not with_audio:
        return None
    sample_rate = with_audio[0][1]
    channels = min(2, max(waveform.shape[0] for waveform, _ in with_audio))
    out = torch.zeros(channels, sample_at_frame(sum(f - c for f, c, _, _ in parts), sample_rate))
    position = 0
    for index, (frames, context, waveform, rate) in enumerate(parts):
        start = sample_at_frame(position, sample_rate)
        position += frames - context
        end = sample_at_frame(position, sample_rate)
        if waveform is None:
            continue
        waveform = waveform.float().cpu()
        if rate != sample_rate:
            import comfy.audio
            waveform = comfy.audio.resample(waveform, rate, sample_rate)
        waveform = waveform[:channels] if waveform.shape[0] >= channels else waveform.repeat(channels, 1)
        local = sample_at_frame(context, sample_rate)
        piece = waveform[:, local:local + end - start]
        out[:, start:start + piece.shape[1]] = piece
        fade = min(round(crossfade_seconds * sample_rate), local, start) if index and waveform.shape[1] >= local else 0
        if fade > 0:
            ramp = torch.linspace(0, 1, fade)
            out[:, start - fade:start] = out[:, start - fade:start] * (1 - ramp) + waveform[:, local - fade:local] * ramp
    return out, sample_rate


def _signature(path):
    with av.open(path) as container:
        stream = container.streams.video[0]
        context = stream.codec_context
        return (context.name, bytes(context.extradata or b""), context.width, context.height, stream.average_rate,
                video_stream_color_space(stream) or "sRGB")


def _replace(temporary, path):
    try:
        os.replace(temporary, path)
        return path, ""
    except PermissionError:
        alternative = "{}_{}.mp4".format(os.path.splitext(path)[0], datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
        os.replace(temporary, alternative)
        return alternative, f"{os.path.basename(path)} is open in another program, so this version is {os.path.basename(alternative)}."


def _source_frames(path, start, frames):
    """How many frames a window of video `path` from `start` holds: `frames`, or the rest of the video."""
    if frames is not None:
        return frames
    with av.open(path) as container:
        count = sum(1 for packet in container.demux(video=0) if packet.pts is not None and packet.size)
    return max(0, count - start)


def _picks(start, count, source_rate, rate, begin):
    """(source frame numbers a window plays at the join's `rate`, the running clock after it). The window holds `count`
    frames from `start` at `source_rate` and begins at `begin` seconds; frames are rounded on the running clock, so
    no window drifts, and a slower video repeats frames."""
    end = begin + Fraction(count) / Fraction(source_rate)
    wanted = round(end * Fraction(rate)) - round(begin * Fraction(rate))
    return [start + min(count - 1, int((number + Fraction(1, 2)) * Fraction(source_rate) / Fraction(rate)))
            for number in range(wanted)], end


def _frame_to_rgb(frame, source_space, target_space, width, height, color_mod):
    """Decode PyAV `frame` into float32 [H, W, 3] in [0, 1] in `target_space` at `(width, height)`."""
    hdr_src = source_space in color_mod.HDR_SPACES
    hdr_dst = target_space in color_mod.HDR_SPACES
    if source_space != target_space:
        array = frame.to_ndarray(format="rgb48le", src_colorspace="bt2020" if hdr_src else "itu709")
        rgb = color_mod.convert(torch.from_numpy(array.astype(np.float32) / 65535.0), source_space, target_space)
        if (rgb.shape[1], rgb.shape[0]) != (width, height):
            rgb = torch.nn.functional.interpolate(
                rgb.permute(2, 0, 1).unsqueeze(0), size=(height, width), mode="bilinear", align_corners=False
            )[0].permute(1, 2, 0)
        return rgb.clamp(0.0, 1.0).numpy()
    if (frame.width, frame.height) != (width, height):
        frame = frame.reformat(width=width, height=height)
    if hdr_dst:
        array = frame.to_ndarray(format="rgb48le", src_colorspace="bt2020")
        return array.astype(np.float32) / 65535.0
    return frame.to_ndarray(format="rgb24", src_colorspace="itu709").astype(np.float32) / 255.0


def _rgb_to_frame(rgb, video_stream, target_space, hdr):
    rgb = np.clip(rgb, 0.0, 1.0)
    if hdr:
        array = np.rint(rgb * 65535.0).astype(np.uint16)
        frame = av.VideoFrame.from_ndarray(array, format="rgb48le")
    else:
        array = np.rint(rgb * 255.0).astype(np.uint8)
        frame = av.VideoFrame.from_ndarray(array, format="rgb24")
    frame = frame.reformat(width=video_stream.width, height=video_stream.height,
                           format=video_stream.pix_fmt,
                           dst_colorspace=video_stream.codec_context.colorspace)
    set_video_color_properties(frame, target_space)
    return frame


def _decode_overlap(overlap_path, target_space, width, height, rate, color_mod):
    """Decode saved overlap sidecar into float32 [M, H, W, 3] in `target_space`, or None if incompatible."""
    try:
        with av.open(overlap_path) as container:
            stream = container.streams.video[0]
            if stream.average_rate is not None and abs(float(stream.average_rate) - float(rate)) > 1e-2:
                return None
            source_space = video_stream_color_space(stream) or "sRGB"
            decoded = [_frame_to_rgb(frame, source_space, target_space, width, height, color_mod)
                       for frame in container.decode(stream)]
    except (OSError, ValueError, IndexError, av.error.FFmpegError):
        return None
    return np.stack(decoded, axis=0) if decoded else None


def _blend_continuation_seam(tail_frames, overlap_frames, k, hdr):
    """Blend `tail_frames` (end of Box A) into `overlap_frames` (Box B's decoded overlap right before trim).

    Replaces Box A's trailing `k - 1` duplicate/pad frames with Box B's true cross-seam interpolated midpoints,
    linearly crossfades the preceding `min(available, 3 * k)` identical carried frames, and computes a bounded
    exposure gain (`[0.88, 1.12]`) to carry into Box B's opening frames. Skipped cleanly if the overlap does not
    match Box A's tail (e.g. a stale re-render).
    Returns `(output_frames, incoming_gain_for_next_box, applied)` preserving `len(tail_frames)` exactly."""
    if not tail_frames or overlap_frames is None or len(overlap_frames) == 0:
        return tail_frames, 1.0, False
    t_tail = len(tail_frames)
    m = len(overlap_frames)
    replace_tail = min(max(0, k - 1), max(0, m - 1), max(0, t_tail - 1))
    carried = overlap_frames[:m - replace_tail]
    blend_len = min(len(carried), 3 * max(1, k), t_tail - replace_tail)
    if blend_len < 1:
        return tail_frames, 1.0, False

    a_start = t_tail - replace_tail - blend_len
    a_end = t_tail - replace_tail
    a_match = np.stack(tail_frames[a_start:a_end], axis=0)
    o_match = carried[-blend_len:]

    weights = _BT2020 if hdr else _BT709
    y_a = float((a_match @ weights).mean())
    y_o = float((o_match @ weights).mean())
    if y_a >= 0.02 and y_o >= 0.02:
        gain = float(np.clip(y_a / y_o, OVERLAP_EXPOSURE_GAIN_MIN, OVERLAP_EXPOSURE_GAIN_MAX))
        if abs(gain - 1.0) < 0.005:
            gain = 1.0
    else:
        gain = 1.0

    o_adj = np.clip(o_match * gain, 0.0, 1.0)
    aligned_mad = float(np.abs(a_match - o_adj).mean())
    raw_mad = float(np.abs(a_match - o_match).mean())
    if aligned_mad > OVERLAP_MAX_ALIGNED_MAD or raw_mad > OVERLAP_MAX_RAW_MAD:
        return tail_frames, 1.0, False

    out = list(tail_frames)
    for j in range(blend_len):
        alpha = (j + 1) / (blend_len + 1)
        out[a_start + j] = np.clip((1.0 - alpha) * a_match[j] + alpha * o_adj[j], 0.0, 1.0)
    if replace_tail > 0:
        o_mid = np.clip(overlap_frames[m - replace_tail:] * gain, 0.0, 1.0)
        for r in range(replace_tail):
            out[a_end + r] = o_mid[r]
    return out, gain, True


def _active_seams(windows, signatures, rate, seams):
    """Validate optional per-window incoming continuation seams aligned with `windows`."""
    if not seams:
        return [None] * len(windows)
    result = [None] * len(windows)
    if float(rate) < 24.0 - 1e-3:
        return result
    for idx in range(1, min(len(windows), len(seams))):
        seam = seams[idx]
        if not isinstance(seam, dict) or not seam.get("overlap") or not os.path.isfile(seam["overlap"]):
            continue
        if windows[idx][1] != 0:
            continue
        if signatures[idx - 1][4] != rate or signatures[idx][4] != rate:
            continue
        prev_video, prev_start, prev_frames = windows[idx - 1]
        if prev_frames is not None:
            prev_total = _source_frames(prev_video, 0, None)
            if prev_start + prev_frames < prev_total:
                continue
        result[idx] = seam
    return result


def build_full_video(path, videos, audio, crf, size=None, temporary=None, *, seams=None):
    """Concatenate segment videos into `path` with `audio` = (waveform, sample_rate) or None. Each video is a path, or
    (path, first frame, frames) for a window of it.
    Videos may differ in frame rate, size, aspect ratio, colour space and codec: the join takes
    the best of them (the highest frame rate, repeating frames of slower videos; HDR when any video is HDR, converting
    SDR into it; the smallest clip's dimensions, or `size` = (width, height) when given). Larger clips are resized
    to those dimensions, including when their aspect ratios differ. Every window keeps its duration.
    When `seams` provides saved continuation overlap sidecars, matching continuation boundaries replace trailing
    interpolator duplicate frames with true cross-seam midpoints, crossfade the overlapping carried frames, and
    smoothly decay residual exposure steps across the join.
    Packets are copied when every file has the same encoding, every window starts at its first frame, and no seam
    blending is needed (segments have no B-frames, so a prefix is its first packets); otherwise the frames are
    re-encoded in the first video's codec, so a sequence saved as HEVC stays HEVC.
    Returns (written path or None, note)."""
    from . import color
    windows = [(video, 0, None) if isinstance(video, str) else tuple(video) for video in videos]
    signatures = [_signature(video) for video, _, _ in windows]
    first = signatures[0]
    rate = max(signature[4] for signature in signatures)
    space = color.target_space([signature[5] for signature in signatures])
    hdr = space in color.HDR_SPACES
    width, height = size or min((signature[2:4] for signature in signatures), key=lambda pair: pair[0] * pair[1])
    active_seams = _active_seams(windows, signatures, rate, seams)
    has_seams = any(item is not None for item in active_seams)
    formats_match = (all(signature[:2] == first[:2] and signature[2:4] == (width, height) and signature[4:] == first[4:]
                         for signature in signatures)
                     and all(start == 0 for _, start, _ in windows))
    copy = formats_match and not has_seams
    k_mult = _fps_multiplier(float(rate))
    decay_len = max(1, round(OVERLAP_EXPOSURE_DECAY_SECONDS * float(rate)))
    temporary = temporary or path + ".tmp.mp4"
    converted = set()
    blended_seams = 0
    try:
        with av.open(windows[0][0]) as template, av.open(temporary, mode="w") as container:
            if copy:
                video_stream = container.add_stream_from_template(template.streams.video[0], opaque=True)
                if first[0] == "hevc":
                    video_stream.codec_tag = "hvc1"  # the mp4 muxer would otherwise write hev1, which Apple refuses
            else:
                video_stream = _add_video_stream(container, rate, width, height, crf, space,
                                                 CODEC_OF_STREAM.get(first[0], "H.264"))
            audio_stream = _add_audio_stream(container, *audio) if audio is not None else None
            offset, encoded, clock = Fraction(0), 0, Fraction(0)
            incoming_gain = 1.0
            for idx, ((video, start, frames), signature) in enumerate(zip(windows, signatures)):
                with av.open(video) as source_container:
                    source = source_container.streams.video[0]
                    if not copy:
                        source_space = signature[5]
                        picks, clock = _picks(start, _source_frames(video, start, frames), signature[4], rate, clock)
                        convert = source_space != space
                        if convert:
                            converted.add(os.path.basename(video))
                        next_seam = active_seams[idx + 1] if idx + 1 < len(active_seams) else None
                        tail_keep = min(len(picks), 3 * k_mult + max(0, k_mult - 1)) if next_seam is not None else 0
                        tail_start = len(picks) - tail_keep
                        tail_buf = []
                        position = 0
                        for number, frame in enumerate(source_container.decode(source)):
                            if position >= len(picks):
                                break
                            if number < picks[position]:
                                continue
                            rgb_cached = None
                            base_frame = None
                            while position < len(picks) and picks[position] == number:
                                needs_gain = incoming_gain != 1.0 and position < decay_len
                                in_tail = tail_keep > 0 and position >= tail_start
                                if needs_gain or in_tail:
                                    if rgb_cached is None:
                                        rgb_cached = _frame_to_rgb(frame, source_space, space, width, height, color)
                                    rgb = rgb_cached
                                    if needs_gain:
                                        w_decay = 0.5 * (1.0 + math.cos(math.pi * (position + 1) / (decay_len + 1)))
                                        frame_gain = 1.0 + (incoming_gain - 1.0) * w_decay
                                        rgb = np.clip(rgb * frame_gain, 0.0, 1.0)
                                    if in_tail:
                                        tail_buf.append(rgb.copy())
                                        position += 1
                                        continue
                                    out = _rgb_to_frame(rgb, video_stream, space, hdr)
                                else:
                                    if base_frame is None:
                                        if convert:
                                            array = frame.to_ndarray(format="rgb48le", src_colorspace="bt2020"
                                                                     if source_space in color.HDR_SPACES else "itu709")
                                            rgb = color.convert(torch.from_numpy(array.astype(np.float32) / 65535),
                                                                source_space, space)
                                            base_frame = av.VideoFrame.from_ndarray(
                                                (rgb * 65535).round().numpy().astype(np.uint16), format="rgb48le")
                                            base_frame = base_frame.reformat(
                                                width=width, height=height, format=video_stream.pix_fmt,
                                                dst_colorspace=video_stream.codec_context.colorspace)
                                            set_video_color_properties(base_frame, space)
                                        elif (frame.width, frame.height) != (width, height):
                                            base_frame = frame.reformat(width=width, height=height)
                                        else:
                                            base_frame = frame
                                    # each output frame gets its own object: a decoded frame keeps its source time base,
                                    # so it is renumbered on the join's clock
                                    out = base_frame if position + 1 >= len(picks) or picks[position + 1] != number \
                                        else base_frame.reformat(format=base_frame.format.name)
                                out.pts, out.time_base = encoded, 1 / rate
                                encoded += 1
                                position += 1
                                container.mux(video_stream.encode(out))
                        incoming_gain = 1.0
                        if next_seam is not None and tail_buf:
                            overlap_rgb = _decode_overlap(next_seam["overlap"], space, width, height, rate, color)
                            blended, incoming_gain, applied = _blend_continuation_seam(tail_buf, overlap_rgb, k_mult, hdr)
                            if applied:
                                blended_seams += 1
                            for rgb in blended:
                                out = _rgb_to_frame(rgb, video_stream, space, hdr)
                                out.pts, out.time_base = encoded, 1 / rate
                                encoded += 1
                                container.mux(video_stream.encode(out))
                        continue
                    origin, count = None, 0
                    end = None if frames is None else start + frames
                    for packet in source_container.demux(source):
                        if packet.pts is None or packet.size == 0:
                            continue
                        if end is not None and count >= end:
                            break
                        if origin is None:
                            origin = packet.pts
                        shift = offset / packet.time_base - origin
                        packet.pts = round(packet.pts + shift)
                        packet.dts = round(packet.dts + shift) if packet.dts is not None else packet.pts
                        packet.stream = video_stream
                        container.mux(packet)
                        count += 1
                    offset += Fraction(count) / source.average_rate
            if not copy:
                container.mux(video_stream.encode(None))
            if audio_stream is not None:
                _mux_audio(container, audio_stream, *audio)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise
    written, note = _replace(temporary, path)
    if not copy:
        details = []
        if len({signature[4] for signature in signatures}) > 1:
            details.append(f"clips joined at {float(rate):g} fps")
        if converted:
            details.append(f"{len(converted)} clip{'s' if len(converted) > 1 else ''} converted to {space}")
        if len({signature[2:4] for signature in signatures}) > 1 or size:
            details.append(f"scaled to {width}x{height}")
        if blended_seams:
            details.append(f"blended {blended_seams} continuation seam{'s' if blended_seams != 1 else ''}")
        if formats_match and blended_seams:
            joined = f"Blended {blended_seams} continuation seam{'s' if blended_seams != 1 else ''}."
        elif formats_match:
            joined = "Skipped mismatched continuation seam overlap; re-encoded full video."
        else:
            joined = ("Segment encodings differ, so the full video was re-encoded"
                      + (f" ({', '.join(details)})" if details else "") + ".")
        note = (joined + " " + note).strip()
    return written, note
