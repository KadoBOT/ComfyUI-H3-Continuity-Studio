---
name: h3-continuity-joins
description: Use when choosing or debugging how H3 Timeline clips connect or overlap — including continue vs cut vs new_scene, seam hiccups or freezes, brightness and exposure drift, visual memory (cast, scene, selected, off), multi-track video cutaways (tracks and overlap_switches), multi-video clip layers (layers and switch), insertion bridges, Shot splitting, continuation_guide and H3C_ContinuityProtection.
---

# Joins, visual memory, cutaways and bridges

Choose each box's join and visual memory for what that shot needs. A long film mixes continuations, cuts, cutaways, and new scenes rather than forcing one mode everywhere.

## The joins

| Join | Box / Timeline fields | What H3 gets |
| --- | --- | --- |
| Continue | `cut: false, new_scene: false` | Last `context_frames` frozen video latents + 40 Hz tick-aligned `carry_audio`. `continuation_guide: "auto"` (default) adds previous last image at frame 0 on calm exits (`< 1.5` luma diff) and omits it on moving exits to avoid freezes. `<name>_overlap.mp4` crossfades seams and keeps interpolated midpoints. |
| Cut | `cut: true, new_scene: false` | Starts fresh (no carried context) in the same scene; keeps scene/cast visual memory. |
| New scene | `cut: true, new_scene: true` | Starts a fresh scene root for scene memory; prompt defines the new place, time, or look. |
| Transition | `join: {"kind": "transition", "note": "…"}` on continuing box (with `bible`) | Writer guidance for an in-scene motivated transition (`transitions` / `native-transitions` guides); rendering still follows `cut`/`new_scene`. |
| Bridge | Top-level `bridges[]` entry | `12`, `29`, or `46` generated frames inserted on a cut between two rendered boxes. |

- **Continuation prompt rules:** Continue from the actual rendered ending (pose, framing scale, camera/subject speed, lighting/exposure). Keep camera/subject motion moving through outgoing boxes instead of braking to a hold, and **never** jump framing scale (wide to close-up) or flip slow/fast pace across `cut: false` (`h3_inspect` `prompt_fields` lints both; use `cut: true` for framing jumps).
- **Continuation limits:** A box **cannot** continue after a predecessor that drops frames (`exact: true` off-grid), plays `< context_frames`, or uses multi-video `layers` — make the follower `cut: true`.
- **Scene resets:** A scene begins at track start, at every `cut: true, new_scene: true`, and at every box with `plate_changes`. (`new_scene: true` without `cut: true` still continues!)

## Cutaways and multi-angle coverage without losing continuity

1. **Independent video `tracks` + `overlap_switches` (`requires: ["timeline-tracks-1"]`):**
   - `tracks: [{id, name, type: "video"|"audio"|"text"}]`; every clip sets `track` and integer `start` (`>= 0`, non-overlapping per track). `Continue` requires an immediately adjacent clip on the **same** track.
   - `overlap_switches: [{id, from, to, at, fade, sound}]` crossfades (`fade: 0..12` frames, `sound: "screen"|from|to`) between overlapping clips on different video tracks — ideal for B-roll / cutaways on Video 2 over a single unbroken performance on Video 1.
2. **Multiple videos per clip (`layers` + `switch`, `requires: ["video-layers-1"]`):**
   - Add up to 3 extra takes in `box.layers[]` (`{id, seed, prompt, first, last, previews, memory: "off"|"scene"|"selected", memories, dialogue}`) sharing the clip's `frames` and clock, plus `switch: {cuts: [{at, to}], fade: 0..12, sound: "screen"|id, align?: {id: {x, y, scale}}}`. Render individual layers via `render_layer`. Every added layer must appear in `cuts`, and the box immediately after a stacked box **must** be `cut: true`.

## Long chains & `H3C_ContinuityProtection`

- **`H3C_ContinuityProtection` node (opt-in graph guidance):** Connect sampling `MODEL` + native Timeline `latent`/`segment` -> `H3C_ContinuityProtection` -> `model` to guider, `latent` to sampler, **returned `segment` to `H3C_SaveSegment`**.
  - Defaults: `enabled: true`, `strength: 0.70`, `mode: "full"` (clamps latent std + replicate-padded 3×3 HF overshoot + mean matching against the clean scene root's exit tail on continuations, and full clip on `ctx=0` `cut_memory` shots; stabilizes `cond_video_latents` video refs too). Switch to `"contrast_only"` for intentional dark-to-bright pans so exposure isn't locked dark. Optional `attention_balance`/`attention_blocks` work on native dense attention only (not Veda sparse attention).
  - Rules: Disable old pixel `context_noise`; incompatible with `H3C_ContextWindows`. Protected shots bypass `H3C_DiskCache` while fresh/disabled/bridge/`plate_changes`/layer paths pass through with cache intact. Graph edits do not mark takes outdated — Regenerate explicitly.
- **Timeline chain settings & 2-pass wiring:** `"continuation_guide": "auto"|true|false` (`false` removes calm-exit holds on moving shots), `"context_noise": true` (pixel stabilization alternative when NOT using `H3C_ContinuityProtection`, optionally paired with `H3C_SigmasTail`), `"audio_feather": N` (lets last `N` carried audio ticks regenerate), `H3C_ContinuationModel`. On 2-pass / frame-interpolated workflows, always wire the 24 fps first-pass decode to `H3C_SaveSegment.guide_frames` so later clips don't inherit interpolated frames or fail `missing_guide_frames`. Watch `seam_warnings` for `mixed_protection` or `stale_continuation`.

## Visual memory

Each remembered moment is a 5-frame native video latent (`<Video N>`) snapped to a 17-frame boundary inside the source box's played footage (never inside carried overlap). Remembered sources must render first, and re-rendering/switching takes on a source marks dependents outdated.

| `memory` | What H3 sees | Best used when |
| --- | --- | --- |
| `cast` | Scheduled entities' current looks + place (up to 3 slots via Story `bible`; see `h3-continuity-story`) | **Default choice whenever a `bible` exists** (no manual frame guessing) |
| `scene` | Scene root frame 0 + mid-view of previous clip (Studio/Story default without `bible`) | In-scene shots without a `bible` |
| `selected` | Up to 3 explicit `memories: [{box, frame, label}]` across any earlier box/scene | Callbacks to a specific prop/place in an earlier box |
| `off` | Nothing (default in raw JSON when omitted!) | Intentionally unrelated new scenes, or continuations needing no earlier recall |

- **At a cut (`scene`/`selected`/`cast`):** H3 normally supplies the whole preceding shot's original latent first to carry layout/clothing across the cut. **Exception:** if the incoming cut speaks or sings (`dialogue` cues or `<d>`), H3 automatically falls back to a short 5-frame moment before the cut so it doesn't mimic old lip movements!

## Insertion bridges & splitting

- **Insertion `bridges`:** `[{"before": "box4", "frames": 29, "seed": 4410, "prompt": "..."}]` (`frames`: `12`, `29`, or `46` on a `cut`/`new_scene` box after an on-grid box). Pure `t2va` (shared + bridge prompt only; `@mentions` read as generic descriptions, no images/guides/memory). **Adds time to the full video only** — do NOT insert bridges inside a locked `in_full_video` soundtrack or picture will drift off-beat. Render after both neighbours via `render_bridge`. (Replacement bridges are unavailable.)
- **Splitting:** **Split before Shot N** splits timed `[Shot N]` (`At MM:SS.mmm,`) into two boxes (second becomes `cut: true`, guides stay with their shots). Keep a single continuous camera move inside one box. Split-at-guide and Guide Recheck are retired.
- **MCP:** Inspect dependencies with `h3_plan_video`, seam warnings with `h3_inspect`, and submit `selection_json.rebuild_continuity` fingerprint explicitly when a replacement take requires rebuilding downstream continuations; never delete dependent takes without consent.
