---
name: h3-continuity-video
description: Use when authoring, planning, rendering, reviewing or debugging MiniMax H3 video in ComfyUI H3 Continuity Studio, H3 Timeline, H3 Story, .h3c projects, Timeline API v1 or MCP — including long seamless sequences, music videos, multi-track cutaways (tracks), multi-angle clip layers, joins, visual memory, references, soundtracks and continuity checks.
---

# H3 Continuity Studio

H3 Continuity Studio arranges a film as **boxes** (called clips in the Studio) on an **H3 Timeline**. Each box is one MiniMax H3 generation. This entry skill routes to six scoped skills — read the host guidance first, then open only the skills your task touches.

## Read the host first

- **MCP:** call `h3_capabilities`, then `h3_read_guidance` (`skill://h3-continuity-video/SKILL.md` and `h3c://docs/MCP.md`). Load scoped skills via `skill://<name>/SKILL.md`.
- **HTTP:** read `GET /h3c/timeline/instructions` before authoring. Prefer its `skills` and `guides[]` (`base`, `ref`, `prompt-writing`, `transitions`, `native-transitions`, `external-timeline`, `timeline-text`, `timeline-audio`, `timeline-references`, `timeline-api`, `limits`, `clients`) over local copies so guidance matches the running host.

## Skill pack

| Skill | Load it when the work involves |
| --- | --- |
| `h3-continuity-joins` | continue vs cut vs new_scene, seam freezes or brightness drift, `H3C_ContinuityProtection`, `continuation_guide`, visual memory (`cast`/`scene`/`selected`/`off`), multi-track `tracks` + `overlap_switches`, multi-video `layers` + `switch`, insertion bridges, splitting at `[Shot N]` |
| `h3-continuity-timing` | `17k+5` / `17k` frame grid, beat/lip-sync/music-video phrasing without over-cutting, `exact` lengths, `carry_conflict`, `max_frames` > 362 (`H3C_ContextWindows`), `long_merge`, `H3C_JoinChain`, `H3C_DiskCache` |
| `h3-continuity-references` | `t2va`/`flf2va`/`ref2va` modes, `flf_refmods`, prompt sections, `<Subject N>` rules, CFG=1 clean-frame lints, `@` mentions, pictures (`image17+`), guides, `h3_stills` (`P-H3-Image Still`), RefMods, plates, `video_slices` |
| `h3-continuity-sound` | `audio_clips` (`@audio1..3`), master soundtrack (`in_full_video`), `box_windows`, `disabled_refs`, `dialogue` cues vs `<d>`, `carry_audio`, `audio_feather`, `voice_clips` (`audio4+`), `timed_text` and `text_lanes` |
| `h3-continuity-story` | `H3C_Story` writer, `user/h3c_templates`, idea images, Story `bible`, Cast (`looks`, `schedules`, `pins`, `assign`), `memory: "cast"`, Vision QC (`checks.json`), CIELAB exposure/colour drift |
| `h3-continuity-api` | `h3c-mcp` tools, `h3_inspect` / `h3_plan_video` / `h3_render_video`, Timeline API v1 (`/h3c/api/v1`), `/h3c/timeline/prepare`, `requires` flags, revisions, held jobs, takes, workflow export |

## Seamless continuity decision table

Pick the right Timeline tool before chopping a sequence into hard cuts:

| Creative need | Best Continuity tool | Avoid |
| --- | --- | --- |
| Continuous action, singing or dialogue in one setting | Grid-aligned **`cut: false` continue** (`17k+5` fresh, `+17k` continuing) or **timed `[Shot N] At MM:SS.mmm,` stages** in one box | Making 1 lyric/dialogue line = 1 off-grid `exact: true` cut |
| B-roll or cutaways over an unbroken performance (music video, interview) | **Independent video `tracks`** (`timeline-tracks-1`) + `overlap_switches`: continuous performance on Track 1, cutaways on Track 2 | Breaking Track 1 performance continuity with cuts |
| Multi-angle coverage of the exact same clip window | **Multi-video `layers` + `switch`** (`video-layers-1`): up to 4 parallel H3 takes switched on-beat inside one box | Duplicating the clock with off-grid cuts |
| New camera angle in the same scene | **`cut: true, new_scene: false`** with `memory: "cast"` (if `bible` exists) or `"scene"`, plus `H3C_ContinuityProtection` | `memory: "off"` or guessing `selected` frame numbers on unrendered boxes |
| New location, time of day, or wardrobe change | **`cut: true, new_scene: true`** (or `plate_changes` for an in-scene look/prop change) | Keeping `new_scene: false` across locations |
| Soften an existing cut between rendered grid boxes (audio NOT locked) | Insertion **`bridges`** (`12`, `29`, `46` frames) | Adding bridges inside a locked `in_full_video` soundtrack |

## Timeline in brief & authoring invariants

- **Frame grid (24 fps):** Fresh boxes (`cut: true` or track start) generate `17k + 5` (`>= 22`, max `362`); continuing boxes add `17k` new frames (`>= 17`, max `362 - context_frames`) and carry `context_frames` (`22`, `39`, `90`, `141`) + tick-aligned `carry_audio`. Raising `max_frames` (up to `991`) enables `H3C_ContextWindows`.
- **Owned fields:** Box keys: `id`, `frames`, `seconds`, `exact`, `prompt`, `seed`, `cut`, `new_scene`, `first`, `last`, `previews`, `memory`, `memories`, `dialogue`, `flf_refmods`, `plate_changes`, `plate_edits`, `cast`, `schedule`, `join`, `source`, `track`, `start`, `layers`, `switch`. Timeline keys: `prompt` (shared header), `requires`, `tracks`, `overlap_switches`, `text_lanes`, `pictures`, `audio_clips`, `voice_clips`, `timed_text`, `dialogue`, `bible`, `refmods`, `plates`, `disabled_refs`, `reference_replacements`, `bridges`, `max_frames`, `continuation_guide`, `context_noise`, `audio_feather`, `video_slices`. Store extra custom metadata under another key (e.g. `edit`); never hand-author `source`.
- **Box lengths belong to the author:** Never alter `frames`, `seconds`, `exact`, or flip `cut` on an un-exact box just to make a dependent frame, bridge, or prompt stage fit — move the dependent item instead, or ask the user before shifting downstream boxes.
- **JSON vs Studio defaults:** Studio/Story clips default to `memory: "scene"`; raw JSON clips without `memory` default to `"off"`. Always set `memory` deliberately (`"cast"` with a `bible`, `"scene"` in-scene, `"selected"` for callbacks, `"off"` on continuations needing no earlier recall). Un-`exact` boxes snap to the grid unless `exact: true`.
- **Self-contained `<Subject N>` & CFG=1 hygiene:** Every `<Subject N>` used in a box's `[Shot ...]` or `Dialogue:` MUST be defined in that box's `subject_definitions:` (or shared `prompt`), with exact matching numbers. Never put unsolicited `35mm`, `vignette`, `grain`, `crackle`, `vintage`, `lens flare`, or `overlay` words in prompts unless explicitly requested (`h3_inspect` `prompt_fields` lints both).
- **Current vs Outdated, Takes & Full Video:** A box is current while its saved MP4 + latent `.safetensors` + last-frame PNG in `output/h3_sequences/<name>/` match its inputs and predecessor. Outdated takes stay playable until explicitly regenerated (`render_box` / Studio Regenerate). Earlier takes stay in `takes/` with ratings (`0..5`) and tags; restore good takes rather than deleting blindly. When all clips have takes, `<name>_full.mp4` builds asynchronously (`full_video_building`); mixed resolutions resize to the smallest pixel-count clip (preserve matching aspect ratios). `<name>_partial.mp4` and `<name>_overlap.mp4` aid review but do not prove all boxes are current.
- **Revisions, Browser & Human Boundaries:** `h3_library` tracks immutable named checkpoints and server revisions; browser Undo/Redo, autosave, layout, playback, and waveform/beat snap stay browser-side (unsaved browser edits are invisible to MCP). Read before writing on revision conflicts. Never abandon a held job, delete takes, or spend extra GPU time without explicit human approval.
- **Pre-render check:** Run `h3_inspect` (`prompt_fields`, `status`) and `h3_plan_video` before queueing GPU renders; verify technical completion (files, frames, duration) separately from creative acceptance (watching the joins).
- **Install pack:** Run `python skills/install.py` from the ComfyUI node checkout so `~/.agents/skills`, `~/.claude/skills`, and `~/.codex/skills` link every skill to the running code.
