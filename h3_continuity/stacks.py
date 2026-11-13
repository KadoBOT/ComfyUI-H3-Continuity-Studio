"""Stacks: a clip with several videos composited into one, which the full video and "so far" play in its place.

The picture blends the videos by the switch's fade weights at the main video's size and frame rate; the sound follows
the video on screen (or plays one video's sound throughout). A stack is saved as `stack@<clip id>` and rebuilt only
when a video it uses, or the switch, changes."""

import datetime
import hashlib
import os
import re
from fractions import Fraction

import av
import numpy as np
import torch
from comfy_api.latest._input_impl.video_types import set_video_color_properties
from PIL import Image

from . import layers, media, store
from . import timeline as rules
from .timing import FPS


def stem(clip_id):
    """The stack's file stem, unique the way bridges.stem is."""
    if re.fullmatch(r"[a-z0-9]{1,40}", clip_id):
        return f"stack@{clip_id}"
    return "stack@_" + hashlib.sha1(clip_id.encode("utf-8")).hexdigest()[:12]


def _switch(timeline, index, switch):
    return timeline.switches[timeline.boxes[index].id] if switch is None else switch


def _used(clip_id, switch):
    """The videos a switch plays, the main one first."""
    sound = [switch["sound"]] if switch["sound"] != "screen" else []
    return list(dict.fromkeys([clip_id, *(cut["to"] for cut in switch["cuts"]), *sound]))


def sources(folder, timeline, index, main_entry, layer_entries, switch=None):
    """Fingerprint of what the stack is made of: each video it plays, by its files, and the switch. None when a video
    has no saved files."""
    switch = _switch(timeline, index, switch)
    clip_id = timeline.boxes[index].id
    entries = {**layer_entries, clip_id: main_entry}
    stamps = []
    for video in _used(clip_id, switch):
        entry = entries.get(video)
        if entry is None or not entry.get("video"):
            return None
        path = os.path.join(folder, entry["video"]["file"])
        if not os.path.isfile(path) or not store.has_segment_latents(folder, entry):
            return None
        stat = os.stat(path)
        stamps.append([video, entry["stem"], entry.get("created"), stat.st_size, stat.st_mtime_ns,
                       store.latent_stamp(folder, entry), entry.get("context_frames", 0), entry["video"].get("fps")])
    return rules._digest({"switch": switch, "played": rules.played_frames(timeline, index), "videos": stamps})


def current(folder, manifest, timeline, index, main_entry, layer_entries, switch=None):
    """The saved stack of clip `index` while it is made of these videos and switch and its files exist, or None."""
    clip_id = timeline.boxes[index].id
    entry = next((item for item in manifest.get("stacks", []) if item.get("stack") == clip_id), None)
    if entry is None or entry.get("sources") != sources(folder, timeline, index, main_entry, layer_entries, switch):
        return None
    if not os.path.isfile(os.path.join(folder, entry["video"]["file"])) or not store.has_segment_latents(folder, entry):
        return None
    return entry


def record(manifest, entry):
    """Records stack `entry` in `manifest`, replacing the earlier one of its clip."""
    manifest["stacks"] = [*(item for item in manifest.get("stacks", []) if item.get("stack") != entry["stack"]), entry]


def _frames(path, picks, size, fmt):
    """The frames of the video at `path` at source numbers `picks` (ascending, repeats allowed), at `size`. A pick
    past the end gets the last frame."""
    position, last = 0, None
    with av.open(path) as container:
        for number, frame in enumerate(container.decode(video=0)):
            if position >= len(picks):
                break
            if number < picks[position]:
                continue
            last = frame.reformat(width=size[0], height=size[1], format=fmt).to_ndarray()
            while position < len(picks) and picks[position] == number:
                yield last
                position += 1
    if last is None:
        raise ValueError(f"{os.path.basename(path)} has no frames")
    for _ in range(position, len(picks)):
        yield last


def _aligned(array, shift):
    """`array` shifted by x, y pixels and scaled about its centre; the uncovered edge is black."""
    if shift is None or (shift["x"], shift["y"], shift["scale"]) == (0, 0, 1):
        return array
    height, width = array.shape[:2]
    scale, middle_x, middle_y = shift["scale"], width / 2, height / 2
    coefficients = (1 / scale, 0, middle_x - (middle_x + shift["x"]) / scale,
                    0, 1 / scale, middle_y - (middle_y + shift["y"]) / scale)
    channels = [np.asarray(Image.fromarray(array[..., c].astype(np.float32), mode="F").transform(
        (width, height), Image.Transform.AFFINE, coefficients, resample=Image.Resampling.BILINEAR, fillcolor=0))
        for c in range(array.shape[2])]
    return np.clip(np.rint(np.stack(channels, axis=-1)), 0, np.iinfo(array.dtype).max).astype(array.dtype)


def _sound(folder, clip_id, switch, entries, played):
    """(waveform, sample rate) of the stack, or None when no video it plays has sound."""
    def part(start, end, video):
        entry, carried = entries[video], entries[video].get("context_frames", 0)
        waveform = store.load_waveform(folder, entry)
        return end + carried, start + carried, waveform, entry.get("audio_sample_rate") if waveform is not None else None

    if switch["sound"] != "screen":
        return media.assemble_audio([part(0, played, switch["sound"])])
    spans = [(0, clip_id), *((cut["at"], cut["to"]) for cut in switch["cuts"])]
    return media.assemble_audio([part(start, spans[k + 1][0] if k + 1 < len(spans) else played, video)
                                 for k, (start, video) in enumerate(spans)])


def build(folder, timeline, index, main_entry, layer_entries, crf, switch=None):
    """Writes the stack of clip `index` from its saved videos and returns its entry (not yet recorded). `switch`
    defaults to the clip's own."""
    switch = _switch(timeline, index, switch)
    clip_id = timeline.boxes[index].id
    played = rules.played_frames(timeline, index)
    entries = {**layer_entries, clip_id: main_entry}
    main_path = os.path.join(folder, main_entry["video"]["file"])
    codec, _, width, height, rate, space = media._signature(main_path)
    hdr = space in ("HDR", "HDR PQ")
    fmt = "rgb48le" if hdr else "rgb24"
    count = media.window_at_fps(0, played, main_entry["video"].get("fps"))[1]
    used = _used(clip_id, switch)
    streams = {}
    for video in used:
        entry = entries[video]
        fps = entry["video"].get("fps") or FPS
        picks, _ = media._picks(0, media.window_at_fps(0, played, fps)[1], fps, rate, Fraction(0))
        picks = (picks + picks[-1:] * count)[:count]
        streams[video] = _frames(os.path.join(folder, entry["video"]["file"]), picks, (width, height), fmt)
    align = switch.get("align", {})
    sound = _sound(folder, clip_id, switch, entries, played)
    name = stem(clip_id)
    path, temporary = os.path.join(folder, name + ".mp4"), os.path.join(folder, name + ".tmp.mp4")
    try:
        with av.open(temporary, mode="w") as container:
            stream = media._add_video_stream(container, rate, width, height, crf, space,
                                             media.CODEC_OF_STREAM.get(codec, "H.264"))
            audio_stream = media._add_audio_stream(container, *sound) if sound is not None else None
            for number in range(count):
                arrays = {video: _aligned(next(frames), align.get(video)) for video, frames in streams.items()}
                frame_time = number * FPS / float(rate)
                picture = arrays[clip_id]
                for cut in switch["cuts"]:
                    weight = layers.weight(switch, cut, frame_time)
                    if weight <= 0:
                        break
                    incoming = arrays[cut["to"]]
                    picture = incoming if weight >= 1 else picture.astype(np.float32) * (1 - weight) + incoming * weight
                picture = np.clip(np.rint(picture), 0, 65535 if hdr else 255).astype(np.uint16 if hdr else np.uint8)
                frame = av.VideoFrame.from_ndarray(picture, format=fmt).reformat(
                    format=stream.pix_fmt, dst_colorspace=stream.codec_context.colorspace)
                set_video_color_properties(frame, space)
                container.mux(stream.encode(frame))
            container.mux(stream.encode(None))
            if audio_stream is not None:
                media._mux_audio(container, audio_stream, *sound)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise
    entry = {"stack": clip_id, "stem": name, "frames": played, "context_frames": 0, "played": played,
             "video": {"file": name + ".mp4", "fps": main_entry["video"].get("fps") or FPS, "width": width,
                       "height": height, "frames": count},
             "audio_sample_rate": sound[1] if sound is not None else None,
             "sources": sources(folder, timeline, index, main_entry, layer_entries, switch),
             "created": datetime.datetime.now().isoformat(timespec="seconds"), "timeline": {"box": clip_id}}
    store.save_segment(folder, entry, torch.zeros(1, 1, 1, 1, 1), torch.zeros(1, 1, 1, 1),
                       sound[0] if sound is not None else None)
    return entry
