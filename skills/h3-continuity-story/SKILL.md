---
name: h3-continuity-story
description: Use when authoring or checking stories with H3 Story, a Story bible, Cast entities or continuity diagnostics — including LLM prompt writing/rewriting/feedback, story templates (user/h3c_templates), idea images, characters/places/props, looks, cast schedules, Add from Cast (assign), memory "cast" and pins, CFG=1 vignette/grain prompt lints, Vision QC (checks.json) and CIELAB exposure/colour drift.
---

# H3 Story, the bible, Cast and continuity checks

Everything here is optional: timelines render from native box prompts directly, while Story (`H3C_Story`), the `bible`, and checks help plan consistent casts and catch continuity regressions.

## H3 Story writer & templates

- **Node (`H3C_Story`):** Connects `story` -> Timeline `story` (renders never block on it). Calls configured OpenAI-compatible story/vision endpoints (API keys live on the ComfyUI server, never in workflows; `thinking` sets reasoning effort; `free_vram` yields GPU VRAM before LLM calls).
- **Actions:** `Write story` (plans up to 60 s when empty and fills scoped boxes), `Rewrite selected clip`, `Rewrite entire Timeline`, `Feedback` (patches from a sentence while leaving unrelated timing/boxes untouched), `Undo last Write` (browser), and `Saved stories`.
- **Structured compilation:** Model outputs structured shot/state data (`terminal_state`: setting, lighting, positions, camera/subject motion, props); Python compiles prompts so shot timestamps stay valid, dialogue lands verbatim, continuing exits emit carry-through motion (not stop/hold), and over-compressed or stretched slow-motion stages fail validation instead of corrupting prompts. `guide` ranks above idea, `bible`, box plan, and general rules.
- **Idea images & templates:** Connected idea images guide palette/lighting/composition without consuming the 9-pic limit unless `@imageN` mentioned (**Send pictures to the writer** caches descriptions). Story **Templates** live in `user/h3c_templates` (`*.md` or folder with `SKILL.md`, `<= 100,000` chars; bundled read-only **Music video** and **Trailer** examples; `docs/STORY-TEMPLATES.md`).

## Pre-render hygiene (CFG=1 & `prompt_fields` lints)

- Turbo H3 graphs use `BasicGuider` at `CFG=1` with **no negative prompt**: unsolicited `35mm`, `16mm`, `anamorphic`, `film grain`, `vignette`, `crackle`, `vintage`, `lens flare`, or `overlay` words in `bible.style` or box prompts trigger dark corner vignettes and grain/crackle spikes (`crackling` ambience can also induce visual crackle). Keep clean modern positive wording unless film FX is requested.
- Always inspect `h3_inspect` `prompt_fields` before queueing GPU renders — it catches unbound `<Subject N>`, `unsolicited_screen_fx`, `continuation_framing_jump`, `continuation_speed_flip`, and `lighting_drift`.

## Story bible, Cast & `memory: "cast"`

- **`timeline.bible` + per-box `cast` / `schedule` / `join`:** Tracks characters, places, and props with descriptions, pictures, voices, and `looks` (outfit/state changes starting at a box, optional new picture). **Build bible** links existing `<Subject N>` lines to entities; Cast edits recompile Story-written boxes cleanly (`Update prose with the writer` patches contradicting hand-edited prose). Appearance belongs to Cast, not per-box invention.
- **Prefer `Add from Cast` (`assign`):** Given `box` and `entity`, picks the next unused `<Subject N>` (avoiding `<Subject N>` numbering collisions), adds `subject_definitions:` + `cast` + `schedule`, and keeps atomic changes undoable — never adds shots/actions.
- **Always use `memory: "cast"` when a `bible` exists:**
  - Automatically sends up to 3 five-frame latent references (capped lower if RefMods videos exist): (1) scheduled characters without a current-look picture in the box (from their latest `pin` since that look began, else mid-shot/exit of the look's first box), then (2) the scheduled `place` (unless continuing in the same place). At a cut, the preceding shot still leads (unless the cut speaks/sings; see `h3-continuity-joins`).
  - **Pin moment for…** in Studio lets you pin an ideal frame of a character or place once rendered; Write automatically promotes `scene` boxes using a bible to `cast` (while respecting explicit `off`/`selected`).

## Post-render continuity check (`checks.json`) & MCP tools

- **Metrics + Vision QC:** Checks up to 5 shot midpoints + last frame + Cast pics + predecessor last frame (`new_scene` skips prior join). Vision reports `character`, `prop`, `place`, `join`, and `fx` defects; quantitative checks run even without a vision model: CIELAB drift from scene start (`a*b* >= 8`, `L* >= 4.5`, texture `>= +25%`), adjacent `Box N-1` -> `Box N` `L*` exposure steps, corner-vs-edge vignette + HF grain/crackle spikes, and **native-FPS** 1-step duplicate/freeze hitches + `v_after / v_before` speed ratio.
- **Results & Retakes:** Cached in `checks.json` (re-render invalidates; never auto-renders; `Retake` tries a new seed while saving the old take). Always watch rendered joins directly too.
- **MCP (`h3_story`, `h3_library`):** `h3_story` exposes write/rewrite/feedback/templates/bible/checks/still-prep against a saved graph + snapshot (keep request keys; poll `h3_job_status`; save explicit revisions; late results never overwrite newer saves; `taken` acknowledges without saving; `writing_mode` & Guide Recheck retired). `h3_library` manages versions, checkpoints (immutable; restore opens editable copy), `duplicate` under a new title, and export/import (installation media verified, no old job replay).
