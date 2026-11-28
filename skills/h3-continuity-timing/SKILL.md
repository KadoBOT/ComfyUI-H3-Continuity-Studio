---
name: h3-continuity-timing
description: Use when setting or troubleshooting H3 Timeline clip durations, start frames, lip-sync or music-video beat timing, the 17k+5 and 17k frame grids, exact off-grid lengths and dropped frames, carry_conflict errors, long clips above 362 frames with H3C_ContextWindows, chain merging (long_merge, H3C_JoinChain) or H3C_DiskCache and guide_frames.
---

# Lengths, phrasing, exact edits and long boxes

## The 24 fps grid & clock

- **Fresh box (`cut: true`, box 1, or track start):** generates **`17k + 5`** frames (`>= 22`):
  `22, 39, 56, 73, 90, 107, 124, 141, 158, 175, 192, 209, 226, 243, 260, 277, 294, 311, 328, 345, 362` (default `max_frames`: `362` = `15.08 s`).
- **Continuing box (`cut: false`):** generates **`17k` new frames** (`>= 17`) after `context_frames`:
  `17, 34, 51, 68, 85, 102, 119, 136, 153, 170, 187, 204, 221, 238, 255, 272, 289, 306, 323` (up to `max_frames - context_frames`).
- Without `exact: true`, `frames` (or `seconds`) snaps to the nearest grid length, shifting downstream boxes on sequential Timelines (`tracks` mode places boxes explicitly by `start`). Read `delivered_range`, `generated_range`, and `carry_range` from `h3_plan_video` / `prepare` instead of computing by hand.

## Music-video, dialogue & lip-sync phrasing

- **Never put 1 lyric/dialogue line = 1 off-grid `exact: true` box.** Off-grid `exact: true` drops tail frames and **forces the next box to be a hard cut**, turning a continuous song or dialogue scene into jump cuts.
- **How to keep exact lip sync AND seamless motion:**
  1. **Group consecutive same-scene lines into grid-aligned `cut: false` chains** (e.g. `107` / `124` / `141` fresh -> `+102` / `+119` / `+136` continuing). `audio_clips` slices each box's exact audio window automatically, while `dialogue` cues (`dialogue-cues-1`) or timed `[Shot N] At MM:SS.mmm,` + `<d>` lines place every sung/spoken phrase at its exact timestamp inside the box.
  2. **Beat cuts & B-roll during a verse:** Keep the main performance continuous on Track 1 and cut to B-roll on Track 2 with `tracks` + `overlap_switches`, or put parallel angles in multi-video `layers` + `switch` on a grid-aligned clip (see `h3-continuity-joins`).
  3. **Snap near-grid edits when authoring:** A `140`-frame clip drops 1 frame (42 ms shy of `141`) and blocks continuation; round new scenes onto `17k + 5` / `17k` wherever a 1–2 frame tolerance is acceptable.
  4. **Reserve off-grid `exact: true` for intentional cuts** — montage beat edits, scene endings, or matching an external cut list where the next clip genuinely starts with `cut: true`.

## Exact lengths & `carry_conflict`

- `"exact": true` plays `frames` (`1..limit`), renders the next grid length up, and truncates played video/audio/`last` PNG while keeping full latents internally.
- **Rules:**
  - Any box that drops frames (`dropped_frames > 0`) **cannot** be continued and **cannot** precede an insertion bridge — its follower must be `cut: true`.
  - An `"exact": true` box whose length sits **on the grid** drops `0` frames and **can** be continued seamlessly.
  - **`carry_conflict`:** A continuing box requires its predecessor to play `>= context_frames`.
  - **Author's length rule:** When fixing either conflict on an existing Timeline with approved timings, set the following box to `cut: true` rather than changing lengths; ask the user first before shifting downstream boxes.

## Long edits, > 362 frames, merging & disk cache

- **Long edits of many cuts:** Stage unlimited still frames in `pictures[]` from `image17` up (`limits.saved_picture_slots`, max `9` per box), referenced via `first`, `last`, and `@imageN` mentions.
- **Boxes past `362` frames (`H3C_ContextWindows`):** Raise `max_frames` (a `17k + 5` integer up to `991`) in JSON / API (no Studio widget; Story plans `<= 362`), and insert `H3C_ContextWindows` between model and sampler (`context_length: 124`, `context_overlap: 39`, `fuse_method: "pyramid"`, optional `freenoise` / `split_conds_to_windows`). Guides only steer their local window; keep prompts grounded so middle windows stay on-scene. Memory with windows, last guides on frame-dropping boxes, and > 498f are unverified.
- **Merge / refine chains:** `h3_continuity.long_merge.merge_continuing(timeline_json, first_id, last_id)` merges un-cut, non-exact continuing boxes (without middle `first` frames) into one box for `H3C_ContextWindows`. **`H3C_JoinChain`** loads `first_segment`..`last_segment` of a non-cut, non-dropping rendered chain into one latent for low-denoise `< 1` refinement through `H3C_ContextWindows` (does not write back segments).
- **`H3C_DiskCache` & Save Segment `guide_frames`:** Place `H3C_DiskCache` (`use`/`refresh`/`off` under `output/h3c_cache`) after the first-pass sampler, keyed on Timeline positive + latent + seed, and wire the first-pass 24 fps decode to `H3C_SaveSegment.guide_frames` so second-pass changes or upscaling never corrupt the next clip's first-pass guide or codec/colour. Inspect node schemas via `h3_inspect` `nodes` before editing workflows.
