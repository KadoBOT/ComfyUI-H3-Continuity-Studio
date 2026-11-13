"""Video layers: up to four H3 generations in one clip, all spanning its time, and the switch plan that says which is
on screen. The main video is the box itself; the others ("layers" here, "videos" in the Studio) live beside the boxes,
so the clock, "the clip before" and every box plan stay as they are."""

import math
import zlib

# Defined before importing timeline, whose REQUIRES reads it while timeline is first imported.
FEATURE = "video-layers-1"
MAX_LAYERS = 3
MAX_FADE = 12
FIELDS = ("id", "seed", "prompt", "first", "last", "previews", "memory", "memories", "dialogue")
CLIP_FIELDS = ("frames", "seconds", "cut", "new_scene", "exact", "join", "plate_changes", "schedule", "source", "cast",
               "flf_refmods", "layers", "switch")

from . import timeline as rules  # noqa: E402


def _error(message):
    return rules._error(message)


def validate(parsed, raw_boxes, requires):
    """Fills `parsed.layers` and `parsed.switches`, by clip id, for the clips that hold several videos."""
    parsed.layers, parsed.switches = {}, {}
    used = {box.id for box in parsed.boxes}
    for index, (raw, box) in enumerate(zip(raw_boxes, parsed.boxes)):
        n = index + 1
        items = raw.get("layers")
        if items is None or items == []:
            if raw.get("switch") is not None:
                raise _error(f"box {n} has a switch but no other videos")
            continue
        if FEATURE not in requires:
            raise _error(f"video layers require {FEATURE}")
        if not isinstance(items, list):
            raise _error(f"box {n} layers must be a list of videos")
        if len(items) > MAX_LAYERS:
            raise _error(f"box {n} has {len(items) + 1} videos; a clip holds at most {MAX_LAYERS + 1}")
        found = []
        for number, item in enumerate(items, 2):
            found.append(_layer(item, n, number, used))
        parsed.layers[box.id] = found
        if raw.get("switch") is None:
            raise _error(f"box {n} has several videos, so it needs a switch")
        parsed.switches[box.id] = _switch(raw["switch"], n, [box.id, *(item["id"] for item in found)],
                                          rules.played_frames(parsed, index))
    for index in range(len(parsed.boxes) - 1):
        if stacked(parsed, index) and not rules.is_fresh(parsed, index + 1):
            raise _error(continue_after(index))


def continue_after(index):
    """Why the clip after stacked clip `index` can't continue it."""
    return (f"Clip {index + 2} continues from clip {index + 1}. With several videos in clip {index + 1}, "
            f"clip {index + 2} must start with a Cut.")


def _layer(item, n, number, used):
    what = f"box {n} video {number}"
    if not isinstance(item, dict):
        raise _error(f"{what} must be a JSON object")
    for key in item:
        if key in CLIP_FIELDS:
            raise _error(f"{what} has {key}, which a video takes from its clip")
        if key not in FIELDS:
            raise _error(f"{what} has an unknown field {key!r}")
    layer_id = item.get("id")
    if not isinstance(layer_id, str) or not layer_id:
        raise _error(f"{what} needs an id")
    if layer_id in used:
        raise _error(f"video id {layer_id!r} is already used")
    used.add(layer_id)
    seed = item.get("seed")
    if seed is None:
        seed = zlib.crc32(layer_id.encode("utf-8"))
    elif isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= rules.MAX_SEED:
        raise _error(f"{what} seed must be a whole number from 0 to {rules.MAX_SEED}")
    memory = item.get("memory", "off")
    if memory not in ("off", "scene", "selected"):
        raise _error(f"{what} memory must be off, scene or selected")
    memories = item.get("memories", [])
    if not isinstance(memories, list) or len(memories) > 3:
        raise _error(f"{what} can remember at most 3 earlier moments")
    for moment in memories:
        if not isinstance(moment, dict) or type(moment.get("frame")) is not int or moment["frame"] < 0:
            raise _error(f"{what} memories need a source box and a nonnegative frame")
        rules._text(moment.get("label"), "memory description")
    dialogue = item.get("dialogue", "cues")
    if dialogue not in ("cues", "manual"):
        raise _error(f"{what} dialogue must be cues or manual")
    return {"id": layer_id, "seed": seed, "prompt": rules._text(item.get("prompt"), f"{what} prompt"),
            "first": rules._image_slot(item.get("first"), f"{what} first frame"),
            "last": rules._image_slot(item.get("last"), f"{what} last frame"),
            "previews": rules._previews(item.get("previews", []), n), "memory": memory, "memories": memories,
            "dialogue": dialogue}


def _switch(raw, n, videos, played):
    if not isinstance(raw, dict):
        raise _error(f"box {n} switch must be a JSON object")
    fade = raw.get("fade")
    if type(fade) is not int or not 0 <= fade <= MAX_FADE:
        raise _error(f"box {n} fade must be a whole number of frames from 0 to {MAX_FADE}")
    before, after = fade // 2, math.ceil(fade / 2)
    cuts = raw.get("cuts")
    if not isinstance(cuts, list) or not cuts:
        raise _error(f"box {n} switch needs at least one swap")
    screen, shown, last = videos[0], {videos[0]}, None
    for cut in cuts:
        if not isinstance(cut, dict) or type(cut.get("at")) is not int or not isinstance(cut.get("to"), str):
            raise _error(f"box {n} swaps need a frame and the video they switch to")
        at, to = cut["at"], cut["to"]
        if to not in videos:
            raise _error(f"box {n} switch names {to!r}, which is not one of its videos")
        if last is not None and at <= last:
            raise _error(f"box {n} swaps must be in order of their frames")
        if at - before < 1 or at + after > played or at >= played:
            raise _error(f"box {n} swap at frame {at} needs {before} frames of fade before it and {after} after, "
                         f"inside frames 1 to {played}")
        if last is not None and at - last < fade:
            raise _error(f"box {n} swaps at frames {last} and {at} are closer than the {fade}-frame fade")
        if to == screen:
            raise _error(f"box {n} swap at frame {at} switches to the video already on screen")
        screen, last = to, at
        shown.add(to)
    for number, video in enumerate(videos[1:], 2):
        if video not in shown:
            raise _error(f"box {n} video {number} is never on screen; add a swap to it")
    sound = raw.get("sound", "screen")
    if sound != "screen" and sound not in videos:
        raise _error(f"box {n} switch names {sound!r}, which is not one of its videos")
    result = {"cuts": [{"at": cut["at"], "to": cut["to"]} for cut in cuts], "fade": fade, "sound": sound}
    if "align" in raw:
        align = raw["align"]
        if not isinstance(align, dict):
            raise _error(f"box {n} alignment must map videos to x, y and scale")
        for video, shift in align.items():
            if video not in videos:
                raise _error(f"box {n} switch names {video!r}, which is not one of its videos")
            if (not isinstance(shift, dict) or any(isinstance(shift.get(key), bool)
                                                   or not isinstance(shift.get(key), (int, float))
                                                   or not math.isfinite(shift[key]) for key in ("x", "y", "scale"))
                    or shift["scale"] <= 0):
                raise _error(f"box {n} alignment of {video!r} needs numbers x and y and a positive scale")
        result["align"] = {video: {key: shift[key] for key in ("x", "y", "scale")} for video, shift in align.items()}
    return result


def stacked(timeline, index):
    return timeline.boxes[index].id in timeline.layers


def videos(timeline, index):
    """The ids of clip `index`'s videos, the main one first."""
    box_id = timeline.boxes[index].id
    return [box_id, *(item["id"] for item in timeline.layers.get(box_id, []))]


def layer_of(timeline, layer_id):
    """(clip index, layer) of the layer with id `layer_id`, or None."""
    for index, box in enumerate(timeline.boxes):
        for item in timeline.layers.get(box.id, []):
            if item["id"] == layer_id:
                return index, item
    return None


def weight(switch, cut, frame):
    """How much of `cut`'s incoming video frame `frame` shows: the fade is centred on the swap, and a hard cut shows it
    from the swap on."""
    fade = switch["fade"]
    if not fade:
        return 1 if frame >= cut["at"] else 0
    return min(1, max(0, (frame - (cut["at"] - fade // 2)) / fade))


def on_screen(timeline, index, frame):
    """The video on screen at clip `index`'s frame `frame`: an incoming video is from its swap frame on."""
    box_id = timeline.boxes[index].id
    screen = box_id
    for cut in (timeline.switches.get(box_id) or {}).get("cuts", []):
        if frame >= cut["at"]:
            screen = cut["to"]
    return screen


def closing(timeline, index):
    """The video on screen at clip `index`'s last frame."""
    return on_screen(timeline, index, rules.played_frames(timeline, index) - 1)
