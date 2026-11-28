"""The continuity check's results, by box, in the sequence folder's checks.json. A result is for the render it was
made for: the manifest entry's layout key and render time."""

import datetime
import json
import os

FILE = "checks.json"
VERSION = 1


def load(folder):
    """The results by box id; {} for a missing or unreadable file."""
    try:
        with open(os.path.join(folder, FILE), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    boxes = data.get("boxes") if isinstance(data, dict) else None
    if not isinstance(boxes, dict):
        return {}
    return {box_id: record for box_id, record in boxes.items() if isinstance(record, dict)}


def save(folder, box_id, record):
    """Saves box `box_id`'s result, keeping the others'."""
    boxes = load(folder)
    boxes[box_id] = record
    path = os.path.join(folder, FILE)
    with open(path + ".tmp", "w", encoding="utf-8") as handle:
        json.dump({"version": VERSION, "boxes": boxes}, handle, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


def record(entry, model, problems, drift, error=None, holds=None, seams=None):
    """The result for the render of manifest entry `entry`. `problems` is None when no Vision model ran or its reply
    couldn't be read, which `error` then says; `drift` is {"box", "words", "texture"} or None; `holds` lists still
    holds ({"start_ms", "frames", "join"}) or is None when they couldn't be measured."""
    made = {"layout": (entry.get("timeline") or {}).get("layout"), "created": entry.get("created"),
            "checked": datetime.datetime.now().isoformat(timespec="seconds"), "model": model or None,
            "problems": problems, "drift": drift}
    if error:
        made["error"] = error
    if holds is not None:
        made["holds"] = holds
    if seams is not None:
        made["seams"] = seams
    return made


def stale_continuation_problem(folder, parsed, index, entry, entries_by_index, *, files=None):
    """Return a structured warning dict if continuing box `index` has a stale or mismatched carried overlap, else None."""
    from . import seam_checks, store, timeline as rules, timing

    if rules.is_fresh(parsed, index):
        return None
    prev_idx = rules.previous_index(parsed, index)
    if prev_idx is None:
        return None
    previous = entries_by_index.get(prev_idx + 1)
    if previous is None:
        return None
    context = int(entry.get("context_frames") or 0)
    if context <= 0:
        return None
    src_dir = files or folder
    prev_box = parsed.boxes[prev_idx].id
    prev_created = previous.get("created")
    curr_created = entry.get("created")
    carried_from = entry.get("carried_from")
    prev_ending = int((previous.get("timeline") or {}).get("ending_context_frames") or 0)

    if store.has_segment_latents(src_dir, previous) and store.has_segment_latents(src_dir, entry):
        try:
            ctx_tok = timing.tokens_for_frames(context)
            prev_tok = store.video_tokens(src_dir, previous)
            curr_tok = store.video_tokens(src_dir, entry)
            if prev_tok >= ctx_tok and curr_tok >= ctx_tok:
                prev_tail = store.load_video_window(src_dir, previous, prev_tok - ctx_tok, ctx_tok)
                curr_head = store.load_video_window(src_dir, entry, 0, ctx_tok)
                check = seam_checks.latent_overlap_mismatch(prev_tail, curr_head, ctx_tok)
                if check["status"] == "ok":
                    if not check["stale"]:
                        return None
                    if parsed.context_noise and carried_from and prev_created and carried_from == prev_created:
                        return None
                    return {
                        "kind": "stale_continuation",
                        "previous": prev_box,
                        "previous_index": prev_idx + 1,
                        "overlap_mad": round(check["overlap_mad"], 4),
                        "previous_created": prev_created,
                        "created": curr_created,
                        "message": (f"Box {index + 1}'s carried overlap does not match box {prev_idx + 1} "
                                    f"(latent MAD {check['overlap_mad']:.3f}); regenerate box {index + 1} to restore continuity."),
                    }
        except (OSError, ValueError, RuntimeError):
            pass

    if prev_ending == context:
        return None
    if carried_from and prev_created and carried_from != prev_created:
        return {
            "kind": "stale_continuation",
            "previous": prev_box,
            "previous_index": prev_idx + 1,
            "overlap_mad": None,
            "previous_created": prev_created,
            "created": curr_created,
            "message": (f"Box {prev_idx + 1} was re-rendered after box {index + 1} carried its frames; "
                        f"regenerate box {index + 1} to restore continuity."),
        }
    if prev_created and curr_created and str(prev_created) > str(curr_created):
        return {
            "kind": "stale_continuation",
            "previous": prev_box,
            "previous_index": prev_idx + 1,
            "overlap_mad": None,
            "previous_created": prev_created,
            "created": curr_created,
            "message": (f"Box {prev_idx + 1} is newer than continuing box {index + 1}; "
                        f"regenerate box {index + 1} to restore continuity."),
        }
    return None


def is_post_processed_video(entry):
    """True when `entry`'s saved video was interpolated (`fps != 24`) or resized relative to its latent geometry."""
    video = (entry or {}).get("video")
    if not isinstance(video, dict):
        return False
    fps = video.get("fps")
    if fps is not None and abs(float(fps) - 24.0) > 1e-3:
        return True
    lw, lh = entry.get("latent_width"), entry.get("latent_height")
    vw, vh = video.get("width"), video.get("height")
    if lw and lh and vw and vh and (abs(int(vw) - int(lw)) > 1 or abs(int(vh) - int(lh)) > 1):
        return True
    return False


def _is_protection_reset(box):
    """True when `box` intentionally resets continuity protection (plate change or non-cut new scene)."""
    return bool(getattr(box, "plate_changes", None)) or (bool(getattr(box, "new_scene", False)) and not bool(getattr(box, "cut", False)))


def _protection_subchain_root(parsed, index):
    """Index of the nearest appearance-reset or fresh root governing `index`'s protection sub-chain."""
    from . import timeline as rules

    chain = rules.continuation_chain(parsed, index)
    root = chain[0]
    for member in chain:
        if _is_protection_reset(parsed.boxes[member]):
            root = member
    return root


def seam_warnings(folder, parsed, placed_by_index):
    """Inspect placed segments for stale continuations, mixed continuity protection, and missing guide_frames.
    Returns {box_index (0-based): [warning_dict, ...]} containing only boxes with warnings."""
    from . import store, timeline as rules

    warnings_by_box = {}

    def add(idx, warning):
        warnings_by_box.setdefault(idx, []).append(warning)

    # Precompute which reset-bounded continuation sub-chains contain any protected box.
    subchain_has_protection = {}
    for index in range(len(parsed.boxes)):
        entry = placed_by_index.get(index + 1)
        if not entry:
            continue
        if (entry.get("timeline") or {}).get("degradation_protection"):
            subroot = _protection_subchain_root(parsed, index)
            subchain_has_protection[subroot] = True

    for index in range(len(parsed.boxes)):
        if rules.is_fresh(parsed, index):
            continue
        entry = placed_by_index.get(index + 1)
        prev_idx = rules.previous_index(parsed, index)
        previous = placed_by_index.get(prev_idx + 1) if prev_idx is not None else None

        if entry is not None:
            stale = stale_continuation_problem(folder, parsed, index, entry, placed_by_index)
            if stale is not None:
                add(index, stale)
            if not _is_protection_reset(parsed.boxes[index]):
                subroot = _protection_subchain_root(parsed, index)
                protected = bool((entry.get("timeline") or {}).get("degradation_protection"))
                if not protected and subchain_has_protection.get(subroot):
                    add(index, {
                        "kind": "mixed_protection",
                        "message": (f"Box {index + 1} was rendered without continuity protection while other boxes in its "
                                    "continuing chain use it, which can cause brightness or color jumps."),
                    })

        if previous is not None and parsed.continuation_guide is not False:
            if is_post_processed_video(previous) and not store.has_guide_frame(folder, previous):
                add(index, {
                    "kind": "missing_guide_frames",
                    "previous": parsed.boxes[prev_idx].id,
                    "previous_index": prev_idx + 1,
                    "message": (f"Box {prev_idx + 1} was saved post-processed/interpolated without guide_frames; "
                                f"connect the 24 fps first-pass decode to guide_frames so box {index + 1} does not "
                                "guide from finished frames."),
                })

    return warnings_by_box


def current(record, entry):
    """Whether `record` is for the render of manifest entry `entry`."""
    return bool(record and entry) and (record.get("layout") == (entry.get("timeline") or {}).get("layout")
                                       and record.get("created") == entry.get("created"))


def status(record, entry):
    """What the Timeline's status shows for a box: its result without the render's key when current, {"stale": True}
    when it was for an earlier render, None without a result or a rendered video."""
    if not record or not entry or not entry.get("video"):
        return None
    if not current(record, entry):
        return {"stale": True}
    return {key: value for key, value in record.items() if key not in ("layout", "created")}
