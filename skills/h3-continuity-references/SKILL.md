---
name: h3-continuity-references
description: Use when writing H3 Timeline clip prompts or wiring visual, video or audio references — including t2va, flf2va and ref2va mode selection, flf_refmods, native prompt sections, <Subject N> definitions, [Shot N] stages, CFG=1 clean-frame lints, @image/@video/@audio mentions, pictures (image17+), first/last frames, Shot preview guides, still generation (h3_stills), RefMods, plates and reference_replacements.
---

# Prompts, references, guides and stills

## Native mode selection (`box_slots`)

| Condition | Resolved mode | Endpoint (`first` / `last`) behavior |
| --- | --- | --- |
| Mentions non-endpoint `@image`, any `@video`/`@video_audio`/`@audio`, active audio/voice lane, or RefMod | `ref2va` (default) | `first` / `last` insert frame-0 / last-frame guides without trajectory planning (may snap at endpoints). |
| Has `first`, `last`, or endpoint guide — and NO extra refs/audio/video above | `flf2va` | Works smoothly toward `last` (`last` frame in frame-dropping exact boxes needs frame-0 guide or `flf_refmods`). |
| Continues (or has `first`/frame-0 guide), NO raw video, and **`flf_refmods: true`** | `flf2va` | Keeps `flf2va` endpoint trajectory while converting pics to cached RefMods + passing raw/RefMod audio. |
| None of the above | `t2va` | Text + audio generation only. |

- Continuing boxes ignore `first` (`continuation_guide: true` default places predecessor's last frame at frame 0; explicit frame-0 guide overrides). Timed **Shot guides** (`previews[]` inside a box) insert guidance frames without planning trajectory toward them; avoid packing many into short boxes. Inspect resolved mode, `tags`, and `effective_prompt` via `h3_plan_video` / `h3_inspect` instead of guessing.

## Prompt structure & per-box `<Subject N>` rules

- **Per-box `<Subject N>` completeness (critical):** Every `<Subject N>` named anywhere in `[Shot ...]` or `Dialogue:` of a box **MUST** be defined in **that same box's** `subject_definitions:` (or shared `prompt`), with exact matching numbers (`<Subject 2>` defined with `@image19` while `[Shot 1]` uses `<Subject 1>` leaves `<Subject 1>` unbound and jumps at seams!). Never define unused subjects or leave bare `<Subject N>` without `@imageN`. Prefer Story `bible` + `cast`/`schedule` or `Add from Cast` (`assign`), and verify with `h3_inspect` `prompt_fields`.
- **Clean-frame CFG=1 rule:** Turbo H3 runs at `CFG=1` with no negative prompt. Never include unsolicited `35mm`, `16mm`, `anamorphic`, `vignette`, `grain`, `crackle`, `vintage`, `analog`, `scratches`, `light leak`, `lens flare`, `letterbox`, `VHS`, `CRT`, `flicker`, or `overlay` (or `crackling` room tone) unless explicitly requested.
- **Section layouts:**
  - `t2va`/`flf2va`: `integrated_multimodal_description:` (`[Shot N]` stages) + `overall_soundscape:` + `non_diegetic_music:`.
  - `ref2va`: `subject_definitions:`, `summary:`, `retention_analysis:`, `detailed_description:`, `overall_soundscape:`, `non_diegetic_music:` (keep partial subsets valid; Studio edits recognized fields and preserves unknown `snake_case:` sections).
- **Timed `[Shot N]` stages:** `[Shot 1]` has no timestamp; later `[Shot N]` start `At MM:SS.mmm,` (increasing, distinct frames inside played length, followed by `the camera cuts to a new shot.` or `the view continues without a cut.`). On continuing boxes, timestamps use **H3's clock** = `playback_seconds + carried_frames / 24`. Give every move natural playable time (~0.8–1.5 s per turn/step); lock lighting/exposure across same-scene boxes.
- **Field syntax:**
  - Definition: `<Subject 1> is Mara in a blue coat; appearance reference: @image17` (or standalone `@image17 is the opening frame.`).
  - Retention: `<Subject 1> (appears in [Shot 1]): fully_preserved|partially_preserved|attribute_transfer|weak_reference - ...` (audio: `fully_copy|partially_copy|reference|weak_reference`).
  - Manual dialogue (`dialogue: "manual"`): `<Subject 1> (S1), calmly, says: <d>[English] Hello.</d>` (or `sings`, or `says in an off-screen voiceover while the corresponding on-screen characters' lips remain completely closed.`). On-screen text belongs in `timed_text`, never `<d>`.
  - Optional detail cues inside a shot (one per line, outside `<d>`): `Style:`, `Composition:`, `Action:`, `Camera movement:`, `Camera speed:`, `Camera amplitude:`, `Dialogue:`, `Scene sound:` (plus Advanced cues like `Lighting:`, `Colour and contrast:`, `Continuity:`, `End state:`). Timeline's shared `prompt` inserts before `[Shot 1]`. `semantic_boxes` may supply structured prompts if `box.prompt` is left empty.

## References, mentions & swaps

| Source | Slots | Mention | Cap / note |
| --- | --- | --- | --- |
| Connected images | `image1`..`image16` | `@imageN` | Max **9 pictures total per box** (`first`/`last` + mentions) |
| Timeline pictures | `pictures[]` from `image17` up | `@image17`… | Unlimited slots in `input/h3_pictures` or `picture` assets |
| Videos / soundtracks | `video1..3`, `video_audio1..3` | `@videoN`, `@video_audioN` | Max **3**; `@video_audioN` also selects `videoN` |
| Audio / voice clips | `audio1..3`, `voice_clips` `audio4+` | `@audioN` | Max **3**; needs `audio_vae` connected to decode sound |

- `disabled_refs`: omits slot from H3 conditioning and rewrites mentions to plain nouns (note: does NOT remove `in_full_video: true` audio playback; see `h3-continuity-sound`). `reference_replacements`: swaps a slot with another slot or file (paired `video_audioN` follows `videoN`).
- **One long video (`video_slices: ["video1"]`):** slices `video1` / `video_audio1` per box (carried overlap included) to restyle long footage box-by-box. Timeline `image_1..` outputs emit the selected box's final `<Picture N>` tensors.

## Guides, still generation, RefMods & plates

- **Guides (`previews[]`):** `{shot, frame, guide}` (or `target: {kind: "first"|"last"|"shot", shot}`, PNG in `output/h3_previews`, optional `visible_text`/`text_contract`). On a continue join, accepting B's First sets A's Last if both are unrendered, or converts B to a cut if rendered (`Use saved predecessor ending` restores continue).
- **Still workflows (`still_image` vs `still_recipe`):** Connect a subgraph to `still_image` with `prompt` + `seed` (optional `width`/`height`/`negative` and `IMAGE` refs; labels `<image1>` Qwen / `<Picture 1>` P-H3/MiniMax / override `h3c_still_reference_label`). Or connect `still_recipe` (`H3C_PH3ImageStill` at 8 MP/4 MP/custom with `lora_stack`; `H3C_MiniMaxH3ImageStill` which splits 2×2 location sheets into `<Picture 1..4>` and keeps `prompt_enhancer: off` by default). Candidate generation always uses the clip's prompt verbatim and never mutates renders until explicitly accepted.
- **MCP `h3_stills`:** `prepare` builds prompts/graphs; `generate` submits one owned candidate (`h3_job_status`); save/accept explicitly under the current revision.
- **RefMods (`refmods[]`):** Encoded H3 conditioning via ComfyUI-MiniMaxH3Mod; forces `ref2va` unless `flf_refmods: true` (needs H3 image VAE for cached conversion + audio VAE for raw audio; no raw `@video`).
- **Plates (`plates[]` + `plate_changes[]`):** Swaps a slot image starting at local `{frame, slot, revision}` (`""` restores original); starts a new scene for scene memory. Preserve `plate_edits`.
- **Scene maps (`box.scene_map`, `requires: ["scene-map-1"]`, `H3C_SceneMap` node):** Top-down opening/end camera and Cast-linked marker plans that inject blocking prose and optional 1 MP map references into fresh video/still prompts (continuing clips borrow from predecessor's end).
