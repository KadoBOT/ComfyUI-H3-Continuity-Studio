# Changelog

All notable changes to H3 Continuity Studio are recorded here. Versions follow [Semantic Versioning](https://semver.org/).

## [0.2.1] - 2026-11-03

### Added

- **Free aspect ratio for configured Timeline workflows.** A configured workflow can render at another aspect ratio while keeping its saved pixel count, for example 3:4 instead of only its saved 1920x1088. Sizes snap to multiples of 32 and stay within 5% of the saved pixel count. Delivered videos are checked against the production size.
- **Box reuse on project updates.** An asset that only one box reads (a guide, plate, timed audio clip, voice clip, Studio picture or reference replacement) now counts only toward that box's identity. Replacing one box's guide re-renders that box instead of the whole film.

## [0.2.0] - 2026-11-03

### Fixed

- **Saved stories keep their frame guides.** Loading a saved story into a workflow whose generator settings differ (for example a seed set to randomize after each run) no longer discards accepted frame guides. The scene anchors pinned to those guides are kept too. Still candidates, in-flight still jobs and links to saved takes are still skipped, because they belong to the old generator and sequence.
- **Uploading a guide no longer marks a saved story as rewired.** The Timeline's uploaded-guide and uploaded-asset lists are no longer compared as generator wiring, so a guide upload alone doesn't make a later load skip the saved renders.

## [0.1.0] - 2026-11-02

Initial public release, with the memory demo.

- **H3 Timeline:** frame, token and audio timing, segment encoding, full-movie assembly, exact-length boxes and windowed long boxes.
- **H3 Story:** an OpenAI-compatible writer (local or cloud) that plans and writes boxes from an idea, with revisions and Undo.
- **Story bible and continuity:** entities, looks, cast linking, pinned cast moments and scene anchors keep characters and places consistent across scenes and camera angles.
- **Studio:** one editing surface for Story, Timeline, pictures, references, takes and audio.
- **Frame images:** still prompts, candidate generation, guide acceptance and uploaded guides.
- **References, timed text and audio:** reference replacement and preparation, RefMods, Whisper timing, timed text and voice references.
- **Saved Story library** and the headless **Timeline API**.

[0.2.1]: https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/releases/tag/v0.2.1
[0.2.0]: https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/releases/tag/v0.2.0
[0.1.0]: https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/releases/tag/v0.1.0
