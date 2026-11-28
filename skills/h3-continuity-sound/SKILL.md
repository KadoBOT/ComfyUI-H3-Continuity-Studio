---
name: h3-continuity-sound
description: Use when an H3 Timeline uses music, singing, lip sync, dialogue, ambience, voice cloning or on-screen lyrics/subtitles — including audio_clips (@audio1..3), master soundtrack muxing (in_full_video), box_windows (box-audio-windows-1), dialogue cues (dialogue-cues-1) vs <d> tags, disabled_refs behavior, carry_audio, audio_feather, voice_clips (audio4+) and Whisper timed_text or text_lanes.
---

# Audio lanes, soundtracks, dialogue and timed text

Read `timeline-audio`, `timeline-text`, and `examples/whisper-source30.json` in the instruction bundle for full schemas. Waveform inspection, beat analysis/snap, and preview playback stay in the browser Studio.

## Audio lanes (`audio_clips` on `audio1`..`audio3`)

```json
"audio_clips": [{"slot": "audio1", "start": 0, "source_start": 30, "duration": 24,
                 "description": "Main track", "layer": "music", "in_full_video": true, "file": {…}}]
```

- **Clock mapping:** `start` is movie seconds; `source_start` is recording seconds (`movie = start + source - source_start`). `duration` is placed length; `layer` is `"music" | "soundscape" | "shot"`. Keep uploaded `file` OR wired `audios.audioN`, never both; short sources pad (never stretch/loop).
- **Rendering:** Each box hears active lanes over its carried replay + new frames (`audio_vae` must be connected on Timeline, or `@audioN` only labels text). Audio lanes default a box to `ref2va` unless `flf_refmods: true` applies (`h3-continuity-references`). Across `cut: false` continuations, `carry_audio: true` aligns seamlessly on H3's 40 Hz audio tick grid (`audio_feather: N` lets the last `N` carried ticks regenerate).
- **Ref generation:** H3 generates audio conditioned on the lane; boxes needing silence need silence in their window. Moving/trimming a lane marks covered boxes outdated.

## Master soundtrack (`in_full_video: true`), `disabled_refs` & `box_windows`

- Individual clip takes (`00001.mp4`) always keep H3's generated audio. In `<name>_partial.mp4` and `<name>_full.mp4`, setting **`"in_full_video": true`** on one or more `audio_clips` replaces H3's audio track with **only** those marked recordings (silent where none play, summed cleanly without fades). Toggling `in_full_video` rebuilds the full video without re-rendering boxes.
- **Avoid the two soundtrack traps:**
  1. **`box_windows` (`requires: ["box-audio-windows-1"]`) restricts `in_full_video` too!** Mapping `by_box` on an `in_full_video: true` clip limits both H3 conditioning AND exported full-video playback to only those mapped boxes — unmapped intro/outro clips turn silent.
  2. **`disabled_refs` disables H3 conditioning, NOT `in_full_video` playback.** Adding a slot to `disabled_refs` stops H3 from hearing/conditioning on it while still letting `in_full_video: true` play cleanly in the exported movie.
- **Recommended music-video setup:**
  - **Standard (single slot):** One full-song `audio1` clip (`in_full_video: true`, no `box_windows`) so non-vocal intro/outro boxes still feel the real beat while vocal boxes sync lips & lyrics.
  - **Silent-ref non-vocal boxes + unbroken master soundtrack:** `audio1` (`box_windows` on vocal clips only, `in_full_video: false`) + `audio2` (full song span, `in_full_video: true`, and `"audio2"` in `disabled_refs`).
- **Locked recording vs bridges:** Never insert `bridges` inside a locked `in_full_video` recording — bridges add visual frames without stretching the recording, causing picture-to-music drift (`timing_conflicts` warns you). Preserve `box_windows` ownership (`by_box`, `source`, `placement`); unlock before editing placement.

## Lip sync, singing & dialogue (`dialogue-cues-1` vs `<d>`)

- **Dialogue cues (`timeline.dialogue`, `requires: ["dialogue-cues-1"]`):** Stores exact recording `{version: 1, cues: [{id, recording: {slot, file}, start, end, text, speaker, portrayal}], observed}` on the recording's source clock. H3 compiles each clip's active cues into its prompt automatically (handling cues crossing cuts/continuations; `portrayal`: `on_screen | voiceover | unknown`).
- **One source per box:** A box uses compiled `dialogue` cues by default (`dialogue: "cues"`) OR its own `<d>[Language] ...</d>` lines (`box.dialogue: "manual"`). Leaving `"cues"` while also hand-typing `<d>` raises an error instead of doubling speech.
- **Do NOT chop every line into an off-grid cut:** Group 2–4 consecutive lines into grid-aligned continuing boxes (`h3-continuity-timing`) — cues and `audio_clips` handle exact intra-box timestamps. Never claim a dialogue cue was checked without inspecting/listening.

## Character `voice_clips` (`audio4+`) & on-screen `timed_text`

- **`voice_clips` (`audio4` up, API `voice_clip`):** Attached to Cast entities; sent automatically when that character has a line/voiceover (uses leftover capacity in H3's 3-audio-slot cap; never plays in full video; keep samples `<= 30 s`; requires `audio_vae`).
- **On-screen lettering (`timed_text`, or `text_lanes` under `timeline-tracks-1`):** `{source_name, source_sha256, enabled, sync_audio, audio_slot, start, source_start, duration, direction, cues: [{id, start, end, text}], words}` imported cleanly with `h3_continuity.timed_text.import_whisper`. Keep transcript text verbatim without H3 tokens (`<d>`, `<|…|>`, `<scenetrans>`, `<cutoff>`). With `sync_audio: true`, transcript tracks follow their `audio_slot` (`audio1..3`). Guides/plates may store `visible_text` + `text_contract`; changing timed text stops renders if a contract mismatches. These are model rendering requests, not burned overlays — visually verify spelling and clearing.
