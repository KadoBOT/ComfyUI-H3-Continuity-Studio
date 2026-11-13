# Changelog

All notable changes to H3 Continuity Studio are recorded here. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Several videos in one clip.** **+ Video** adds up to three more H3 generations of a clip's time, each with its own prompt, seed, First and Last frames, memory and dialogue setting. Pick a video with its button above the clip's tabs, or its row on the Timeline, to edit and generate it. The clip's switch says which video is on screen: drag a swap's handle on the Timeline (it snaps to beats) or type its frame, set a fade of 0 to 12 frames, and choose whether the sound follows the screen or stays with one video. The full video plays the clip as a stack of its videos, blended without encoding the rest of the video again; the video so far plays the main video until the others render, and the Viewer plays the stack or the picked video. The clip after a stack starts with a Cut. Managed jobs refuse these Timelines for now, and Shot images and takes lists for the other videos come later. See [Videos in one clip](docs/TIMELINE-VIDEO-LAYERS.md).

## [0.24.0] - 2026-11-13

### Added

- **MiniMax H3 Image Still has a megapixels setting.** Above 0, width and height only set the aspect ratio and the still is generated at that area, each side a multiple of 32. Connect the video size and set 20 to get a 20 MP still at the video's aspect ratio without size math in the workflow. At 0, width and height are used exactly, as before.

### Fixed

- **Generate candidates no longer repeats the same image.** With the Image seed field empty, every candidate request now gets a new random seed. Before, it used the generator node's own seed, often 0, so each click returned the same picture. Enter a seed to repeat one exactly; each candidate still records the seed it used.
- **Stills use Cast sheets and location grids as references instead of editing them.** The still prompt now describes a new image composed for the requested camera, and asks that no reference's framing, panel grid, color grading or rendering carry over. MiniMax H3 Image and Qwen prompts no longer start with `Edit <Picture 1>.` or call the location the canvas. P-H3-Image keeps that opening because its core node adds it to every prompt.

## [0.23.0] - 2026-11-13

### Changed

- **Cast references are character sheets; location references are four-angle grids.** **Prepare references** now asks the connected still generator for a character sheet on a plain ivory background, with the face on the left and the full body on the right, for each character and look. Each location is one image split into 2 rows and 2 columns, showing the same empty place from four camera positions with no people or animals. Before, both came out as an ordinary scene picture.
- **The Story style no longer paints other characters into references.** Style sentences that name another character are left out of a reference prompt. Location sheets also leave out style sentences about characters or people. A line such as "orange belongs only to her jacket" used to put that character into location and creature pictures.
- **Stills no longer add scene anchors or previous guides on their own.** First, Last and Shot requests receive relevant Cast images, images mentioned in the still prompt and images connected to the Still Recipe. The saved continuity source picker is gone; the image details keep only the seed.

## [0.22.2] - 2026-11-13

### Fixed

- **Generate candidates with the video prompt.** Leave the image prompt blank to use the clip’s assembled video prompt. Explicit image prompts still take precedence.

- **Imported audio without source duration opens safely.** The Studio reads the recording's metadata without changing its placed window, and keeps trimming disabled with a clear message if the source cannot be read. The API schema and native parser now explicitly validate optional `source_duration`; older stories remain supported.

## [0.22.1] - 2026-11-12

### Fixed

- **A Timeline from a newer version opens read-only.** When its `requires` list names a feature this version doesn't know, the Studio says so at the top: "This Timeline needs a newer H3 Continuity (…). It is open read-only so nothing in it is lost; update the node pack to edit or render it." Edits are undone at once; **+ Clip**, Render and Generate are off. Story Write's apply and Undo, still and reference updates, and undo and redo of the Studio's history leave the Timeline's text exactly as it was. Before, this version dropped every field it didn't know as soon as it wrote the Timeline, even without an edit: opening a converted clip or changing the context length was enough.

## [0.22.0] - 2026-11-12

### Changed

- **A saved story runs in the workflow you load it into.** Loading a story that belongs to a managed Timeline API project into a different workflow now makes an independent copy there: it keeps the clips, prompts and pictures, gets its own sequence, and renders with the open workflow's models and settings. The managed project is left unchanged. The story stays attached only in the project's own workflow (one wired the same, or one whose Timeline is already attached to that project). Before, any workflow became attached, so edits and renders went through the project's saved workflow whatever was open.

### Fixed

- **An attached Timeline whose size comes from other nodes can save.** Settings fed by a link are no longer sent as empty values, a dropdown number such as the context length is sent as a number, and only settings changed in the Timeline go back to the project. Such a workflow failed every save with "Value does not satisfy type constraint", which also blocked loading any other story.
- **A refused project save names the field.** The message now includes the path the server reports, for example `(/settings/width)`.
- **The Cast page opens for entries saved without looks.** A character, place or prop whose saved entry has no `looks` list no longer stops the Cast page from drawing.

## [0.21.1] - 2026-11-11

### Fixed

- **MiniMax H3 Image Still accepts LoRA stacks.** Connect an optional `LORA_STACK`, as with P-H3 Still, to apply ordered model and CLIP strengths to direct images and Studio candidates. Empty and disabled stacks leave generation unchanged.

## [0.21.0] - 2026-11-10

### Added

- **MiniMax H3 Image Still.** A ready-made node connects the official MiniMax H3 Image model directly to the Timeline's `still_recipe` input. It uses the native six-step image workflow, preserves scene and character reference roles, and supports Studio candidates and standalone images. A wired example and installation guide cover the model, shared Qwen3-VL text encoder and separate image VAE. ComfyUI must include `MiniMaxH3ImageConditioning` (native support added November 10, 2026); an older core reports how to update before loading weights.

## [0.20.0] - 2026-11-08

### Added

- **MCP tools and the existing H3 skills for AI agents.** A standalone stdio adapter connects Codex or Claude Code to a local or remote Studio. It supports saved native and managed projects, explicit render plans, retained submission receipts, Story/still proposals, takes and library workflows. The host serves its seven canonical skills through the MCP Skills extension and ordinary resources. README and the Automation guide include separate uv/venv installation, both clients, authentication and recovery instructions; client skill activation is reported separately from tool connectivity.

## [0.19.7] - 2026-11-08

### Fixed

- **Saved stories recover managed attachments already lost by older versions.** Opening a story whose attachment was previously stripped now verifies its reserved sequence through the project API and restores missing bindings. Local content and settings are preserved; a failed lookup leaves the destination untouched. Refresh the browser and reopen the Saved story to reconnect an already-detached workflow.

## [0.19.6] - 2026-11-08

### Fixed

- **Manual checkpoints accept redundant identical preview records.** Repeated copies of the same First, Last or Shot preview no longer fail with “previews need unique targets.” Checkpoint copies keep one record; differing records for the same target still fail validation, and the source workflow stays unchanged.

- **Saved stories reconnect to their managed API project.** Opening an attached story keeps its project identity and asset bindings, so status and rendering use the project API instead of failing the native Timeline ownership check. If the saved content or current settings differ from the API project, the existing conflict choices preserve local edits until you choose which to keep. Native imports and forks keep their existing behavior and generator wiring.

## [0.19.5] - 2026-11-08

### Fixed

- **Assigned first and last frames appear in Timeline and Shots.** Images chosen in a clip's Settings now fill its frame markers and the Shots image preview, including the enlarged view. Accepted still guides keep priority over reference images, and unaccepted candidates no longer hide an assigned frame.

### Removed

- **`SHA256SUMS.json`.** It listed file checksums from the first published version and was never updated afterwards, so 101 of its 232 entries no longer matched the files they named, and 191 of the pack's 423 files were not listed. Nothing in the node pack read it. Each release's Git tag already identifies its exact files.

## [0.19.4] - 2026-11-07

### Fixed

- **A normal browser refresh now loads every updated Studio file.** ComfyUI lets the browser keep the Studio's helper files (`.mjs`) cached, so after an update a normal refresh, or a new tab, could keep running an older copy of a file that had changed, mixed with newer ones. Each file's import now carries a tag computed from its contents and everything it imports, so any change gives every file that depends on it a new address and the browser fetches it again, while unchanged files still come from the cache. `node tools/module_versions.mjs --write` stamps the tags and the test suite fails while any tag is out of date.

## [0.19.3] - 2026-11-07

### Fixed

- **Loading a workflow no longer floods ComfyUI with still-source requests.** While a workflow with a Timeline loaded, its still panel redrew once per connection, and each redraw sent the whole Timeline to the server to list the saved continuity sources again: 44 requests of about 360 KB on an 88-clip workflow, keeping the server busy for over two seconds. A request now stops as soon as a newer redraw replaces it, so loading a workflow asks once and picking a still target asks once instead of twice. The listed sources are unchanged.

## [0.19.2] - 2026-11-07

### Fixed

- **No more second-long freezes after a run of edits.** On a long Timeline, a few length edits or clip selections in a row could freeze the Studio for one to two seconds while the browser cleaned up. Each redraw started loading a fresh copy of every clip thumbnail and still, even the copies it then threw away; now only the images that are shown load. Over 20 length edits on an 88-clip Timeline the longest freeze drops from about 1.6 seconds to about 0.1 second, and each edit builds about half as much temporary data.

## [0.19.1] - 2026-11-07

### Fixed

- **Typing keeps up on long Timelines.** Each key in a clip prompt, its sections, the shared prompt, a bridge prompt or an audio direction shows at once instead of waiting for the whole Timeline to redraw (about a second per key on an 88-clip Timeline, now about 35 milliseconds). The saved Timeline still follows every key; the Timeline redraws and Undo records the edit once typing pauses, and Undo or Redo during typing first keeps what was typed.
- **Other edits respond faster.** Changing a clip's length, selecting or dragging redraws the Timeline once instead of twice and updates the clips and stills already shown rather than rebuilding them. The ComfyUI graph under the Studio stops redrawing while the Studio is open and resumes when it closes. The current video stays in the player while an edit's status refreshes.

## [0.19.0] - 2026-11-07

### Added

- **LoRA stacks for P-H3 stills.** Connect a `LORA_STACK` output (such as Easy Use's stack) to the P-H3-Image Still node's optional `lora_stack` input. LoRAs apply in stack order with separate model and CLIP strengths to both direct images and Studio candidates. Empty or unconnected stacks keep the existing behavior.

## [0.18.0] - 2026-11-06

### Added

- **Lock audio to boxes.** The opt-in switch in Audio settings keeps each box's assigned part of a recording through length, order and insertion edits. Extending a box adds silence after its assignment; shortening hides the tail so extending again restores it. New and duplicated boxes start without assigned audio. Moving a box carries its audio, and splitting partitions its assignment without copying a neighbor's sound. Audio lanes show the assigned segments and silence gaps while retaining one source recording.
- **Source timing stays aligned.** Linked dialogue cues, synced text, detected beats, audio references and the selected original soundtrack follow the same box-bound ranges. Unlocking restores the original continuous placement with confirmation when playback changes; Undo restores the bindings. Locking is off by default, and existing projects keep their behavior.

## [0.17.0] - 2026-11-06

### Added

- **Start a new generation** in **Project settings** keeps the Timeline, prompts, seeds, render settings and references while every clip and bridge starts unrendered in a separate render folder. The previous generation's clips, full video and Takes remain untouched. **Previous generations** links to earlier joined videos and individual clips, including unfinished generations. Nothing renders until you ask.

### Fixed

- **Regenerating a clip with incompatible saved continuity now offers recovery before queueing.** The confirmation names the affected clips and explains that their videos will be kept in Takes. Once the replacement saves successfully, only dependent clips and bridges are archived; independent clips stay rendered. **Render remaining** rebuilds the missing clips. Cancelling, stale confirmation or a failed save leaves existing renders in place. Recovery starts with one take; compatible regeneration still supports batches.

## [0.16.1] - 2026-11-06

### Fixed

- **Visible preview assembly.** The viewer shows a loading indicator and build status above the player, including while watching an individual clip. Failed builds show their reason beside the video controls. An existing preview stays playable while the next version builds.
- **Mixed-size previews and exports.** Joined clips resize to the smallest clip's dimensions, including when their aspect ratios differ. Re-rendering the smaller clip at higher resolution automatically rebuilds the preview at the new common size; original clip files are preserved.
- **Beats for the selected lane.** Select an audio lane to find **Detect beats · @audioN** and **Snap to beats** in its right-hand audio settings. Detection reads only that lane's file, with results labelled by lane.

## [0.16.0] - 2026-11-06

### Added

- **Keep the first pass, re-render the second.** The new **H3 Disk Cache** node goes after the first-pass sampler and saves its result on disk, keyed by the Timeline's `positive`, `latent` and `seed` and by the settings above the sampler. Render the whole Timeline without a second pass, turn the second pass on, and render again: every clip loads its first pass from disk and goes straight to the second pass. Its `info` output says why a result was sampled again or could not be cached. See [Keep the first pass](guide/output/first-pass-cache.md).
- **H3 Save Segment `guide_frames`.** Connect the first-pass decode, and a continuing clip is guided from the last frame of the clip before as it was sampled, not as finished, so a second-pass change no longer changes every later clip's first pass.

## [0.15.0] - 2026-11-06

### Added

- **Named checkpoints with videos.** In **Saved stories**, **Save checkpoint…** preserves the current workflow, Timeline, rendered videos and takes as a named snapshot, separate from automatic versions. Later edits and renders cannot overwrite it. Loading a checkpoint opens an independent editable copy with its own media. Checkpoints and restored copies use additional disk space; existing versions are kept.
- **Optional autosave.** The **Autosave** checkbox in **Saved stories**, also available in **H3 Continuity → Story → Autosave** settings, persistently disables background Story and Timeline saving across workflows, including attached projects. Explicit actions that require saving still save their state. Checkpoint saving captures local edits directly, without first restoring another workflow's autosave.

## [0.14.0] - 2026-11-06

### Added

- **Video so far.** Before every clip has rendered, the Viewer's switch reads **Video so far · 5/90** and plays the clips rendered from the first one on, joined with their bridges and the ticked audio clips (or H3's audio), so a timing problem against the soundtrack shows after a few clips instead of after the whole render. It is built in the background, grows as clips render, keeps playing from the same moment when it grows, and is saved as `<name>_sofar.mp4`.
- **Playhead.** A playhead follows the playing video along the ruler, the clips and the audio lanes, holding at a cut while an inserted bridge plays. Click or drag the ruler to play from that moment.
- **Detailed waveforms.** Audio clips draw their file's waveform at any zoom, decoded once per file in the browser, instead of a 256-point outline.
- **Snap to beats.** **Detect beats** finds the beats of the audio lanes and draws them under the waveforms; with **Snap to beats** ticked, dragging a clip's edge lands it on the nearest beat (Shift drags freely).

## [0.13.1] - 2026-11-06

### Fixed

- **The Studio no longer changes clip lengths behind your back.** Every edit (a prompt, a remembered moment, a setting) re-checked all clip lengths and quietly cut any clip over 362 frames, or over the continuing limit after `context_frames` changed, down to the limit, which moved every later clip off its recording or beat map. Lengths now stay as saved, a clip over the limit shows the problem instead, and the Studio keeps a Timeline's `max_frames` (it used to drop it on save) and lets clips reach it.
- **Errors no longer suggest changing a clip's length to fit something that depends on it.** A remembered moment past its source clip now says which frames that clip plays, and a plate change or guide past a clip's end says to move it earlier rather than lengthen the clip. Where a length change is one of two fixes (dropped frames before a continuation or a bridge, too few frames to carry), the message says it moves every later clip, and offers a cut or a replacement bridge first. The agent skills now say that lengths belong to the author: an agent moves the dependent memory, guide or prompt timing, or asks before changing a length.

## [0.13.0] - 2026-11-06

### Changed

- **Rendered clips no longer disappear from the Timeline.** A clip whose prompt, settings or remembered clip changed after it rendered is now *outdated*: it keeps its thumbnail and video, plays in the full video, and shows what changed in its tooltip. **Render N remaining** renders only clips with no take; regenerate an outdated clip from its own button.
- **Saved takes follow their clip, not its position.** Inserting, removing or moving a clip no longer marks every later clip unrendered, rendering a clip moves only that clip's earlier take to `takes/` (never the clips after it), and takes of removed clips stay in place.
- **The full video builds in the background.** Status checks no longer wait for the encode (about 10 minutes for 88 boxes), which made every clip look unrendered until it finished. A failed or timed-out status check keeps the last known clips on screen.
- **Clips of different formats join.** The full video takes the best of its clips: the highest frame rate (24 fps clips repeat frames beside interpolated ones, keeping their duration), HDR when any clip is HDR (SDR clips converted), and the largest size. Only a different aspect ratio is refused. The continuity check reads interpolated clips too.
- **One saved story, not many copies.** Loading a saved story continues that story, with its own sequence folder and renders, even when this workflow's wiring differs; clips whose render settings changed show as outdated. The story picker groups entries that share a sequence folder or a title as versions of one story, and each version shows its folder and how many clips it has rendered.

### Added

- H3 Save Segment has a `codec` choice: H.264 (default, unchanged) or HEVC. HEVC saves 10-bit Main10 for HDR, tagged `hvc1` so Apple players show HLG, still without B-frames so segments join by packet copy. A re-encoded full video keeps the segments' codec.

### Fixed

- **Full video of frame-interpolated boxes.** A box saved at a higher frame rate (for example 48 fps after interpolation) played only the first half of its clip in the full video, the partial video and replacement previews, so each scene changed before it ended and the audio drifted. Box windows are now converted to each clip's own frame rate. Rebuild the full video of an interpolated story to fix it.
- **Render N remaining** no longer puts every run in ComfyUI's queue at once. Each queued run renders the next box that needs it, so when one run failed (a 70-box story ran the machine out of memory), every run behind it retried the same box and failed the same way. Render now keeps 3 runs in ComfyUI's queue, adds one as each succeeds, and stops at the first failed or interrupted run, taking its own waiting runs out of the queue. The setting **Runs kept in ComfyUI's queue while Render all works** changes the number; 0 restores the old behavior. Keep the page open while a long Render works.

[Changes since v0.12.10](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.12.10...v0.13.0).

## [0.12.5] - 2026-11-05

### Fixed

- P-H3 Studio stills default to 8 MP at the workflow's aspect ratio instead of inheriting a small video canvas. The generator offers 4 MP and custom dimensions; explicit still-size requests remain authoritative.
- P-H3 reference pictures retain their original pixels and aspect before native conditioning, including the first character sheet. Cast roles, picture titles and saved descriptions reach the image prompt.
- P-H3 native video prompts without authored snapshots require still-prompt preparation or manual still text. Snapshot prompts retain subject designs and scene style instead of dropping them while keeping a whole video action.

[Changes since v0.12.4](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.12.4...v0.12.5).

## [0.12.4] - 2026-11-05

### Fixed

- The Viewer shows a live render preview only when its rendering box is selected. Selecting another box shows that box's video or empty state.
- First and Last frame guides are recognized as endpoints after converting to FLF2VA, including clips already converted. Accepting an endpoint guide replaces a free guide on the same frame.
- Removing, moving or uploading Frame guides now records an Undo step.
- P-H3-Image Still recipes now accept empty autogrow image sockets, so the Timeline can supply still references without manual image connections.

[Changes since v0.12.3](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.12.3...v0.12.4).

## [0.12.3] - 2026-11-05

### Fixed

- **Shot thumbnails on the Timeline now start where their Shot starts.** A Shot at 00:01.500 no longer paints over the first 1.5 s of its box: each Shot thumbnail spans from its own start to the next Shot (or the end of the box). Boxes whose Shots sit too close together keep the earlier packed layout.

[Changes since v0.12.2](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.12.2...v0.12.3).

## [0.12.2] - 2026-11-04

### Fixed

- Story's image planner, snapshot writer and still-prompt preparation now use Pruna P-H3-Image prompting guidance when that still generator is selected: concrete medium and composition, directional lighting, exact requested text and explicit reference edits, without video prompt markup or quality-word padding.

[Changes since v0.12.1](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.12.1...v0.12.2).

## [0.12.1] - 2026-11-04

### Fixed

- **Revision tags no longer split a saved story.** A trailing revision tag such as ` · r2` or ` · r3 · r3` is ignored when saved stories are grouped, so "Heavy Things Fall Up v07 (one story) · r1" and "· r2" are versions of one story. Before, each tag made a group of its own.

[Changes since v0.12.0](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.12.0...v0.12.1).

## [0.12.0] - 2026-11-04

### Changed

- **Saved stories are grouped.** The Saved stories list now has two selectors: the story, then its version. Saved entries with the same title (ignoring case and spacing) are versions of one story, so a story saved many times no longer fills the list. Versions are numbered from v1, newest first, and the one open in this workflow is marked *open now*. **Delete permanently** is now **Delete version** and removes only the selected version. Nothing is renamed or moved on disk.

### Added

- **Rename story and Delete story.** **Rename story** shows a name you choose in place of the title; the story is still found by its title, so new saves with that title join it, and an empty name goes back to the title. Names are kept on the server in `user/__h3c_state`. **Delete story** removes every version and its generated media after one confirmation; if a version cannot be deleted (for example a render is running) it stops there and says how many were removed.

[Changes since v0.11.0](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.11.0...v0.12.0).

## [0.11.0] - 2026-11-04

### Added

- **P-H3-Image Still node.** One node generates Timeline stills with Pruna AI's P-H3-Image (derived from MiniMax H3). Select the installed `p-h3-image` model, text encoder and VAE, connect its `still_recipe` output to the Timeline, and generate First, Last and Shot candidates in the Studio; no sampler graph or bindings to write. It expands into the official ComfyUI workflow (8 steps, euler, no CFG), takes up to 8 reference pictures as `<Picture N>` with the scene placed first, and has an optional prompt upsampler (off by default, not with references yet). A video render never runs it. Missing files, an old ComfyUI, bad sizes and too many references give messages that say what to fix. New: `examples/ph3_image_story_studio.json` and the guide page *Stills with P-H3-Image*, which also covers the license (the weights exclude the EU, UK, South Korea and the US without a separate MiniMax license). Existing Still Recipe setups are unchanged.

[Changes since v0.10.1](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.10.1...v0.11.0).

## [0.10.1] - 2026-11-04

### Changed

- **Long continuing chains guide: the model matters most.** The burn table is now labelled as FastH3 omniref int8's. A new table shows the same chain on MiniMax REF2VA (int8 ConvRot and bf16, with the ref2v turbo LoRA v1.1): it barely burns (clip 6 texture 1.19 against 2.04), and the anti-burn LoRA through **H3 Continuation Model** is safe there at 0.5 (no cut, clip 6 at 1.04). FastH3 v2 with turbo LoRA v1.0, which the Story Studio examples use, did not burn either (clip 6 at 0.97), but clip 2 cut to a closer framing at the first join, with or without the anti-burn LoRA, with the examples' res_multistep sampler as well as euler, and on a second seed.

[Changes since v0.10.0](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.10.0...v0.10.1).

## [0.10.0] - 2026-11-04

### Added

- **Undo, redo and history.** Studio controls and keyboard shortcuts step through Timeline edits. History lists named states and jumps directly backward or forward. Typing in one field and dragging a clip form one edit; making a new edit after a jump replaces the redo branch. The latest 100 edits stay available until the project/workflow changes or the page reloads. On phones, the controls are under More.
- History restores clips, prompts, guides, Cast, pictures, references, audio, timed text and Timeline settings through the existing save path. Writer results applied to the Timeline are included; live job receipts keep following the server. Independent Story inputs, graph wiring, job cancellation and permanent file deletion remain outside this history.

- **Partial video while repainting.** Until every clip of a Timeline that splits a video is rendered, the Studio's **Full video** and **Download video** use `<name>_partial.mp4`: the rendered clips, and the split video's own frames and sound for the others, at the Timeline's full length. The Timeline node saves the split video at render size (`<name>_source.mp4`) for it.

[Changes since v0.9.0](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.9.0...v0.10.0).

## [0.9.0] - 2026-11-04

### Added

- **Audio in FLF2VA + cached RefMods.** A clip with this switch on no longer falls back to REF2VA because it mentions audio or has an audio-lane clip under it. The raw audio is encoded by the H3 audio VAE into the same reference REF2VA uses and numbered before any audio RefMods, so **Convert to FLF2VA** now works on clips with a soundtrack. Raw video still needs REF2VA. The Timeline needs its audio VAE connected for this.

[Changes since v0.8.1](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.8.1...v0.9.0).

## [0.8.1] - 2026-11-04

### Fixed

- **Frame guide list layout.** Each guide in the Shots tab is a card with its thumbnail, name, **Frame** field and **Remove**. **Guide another frame** is its own drop box. A guide from an older project that still renders at its saved frame after its shot was removed reads **Frame guide** instead of **Removed Shot N**.

[Changes since v0.8.0](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.8.0...v0.8.1).

## [0.8.0] - 2026-11-04

### Added

- **Guides at any frame.** In a clip's **Shots** tab, **Guide another frame** uploads a guide for a chosen frame without adding a `[Shot N]` line, and every listed guide has a **Frame** field that moves it. A guide whose Shot marker was removed now reads **unused** instead of claiming a frame, and can be given a frame again.
- **Convert to FLF2VA.** A REF2VA clip's **Settings** tab has a button that turns on **FLF2VA + cached RefMods**: its First and Last frames become the start and end frames, and its images become cached RefMods. When the clip mentions a raw video or raw audio, which the Studio cannot convert to RefMods, or a fresh clip has no First frame, the button is disabled and says why.
- **Drop images on guide targets.** Dropping an image file on a First, Last or Shot marker, on the frame panel's image area, on **First frame** or **Last frame** in **Settings**, or on **Guide another frame** uses it as that guide.
- **Texture drift and holds in the continuity check.** Drift also compares fine-detail energy with the scene's first clip and names a rise of 25% or more ("Drift: 104% grainier than box 1."); a drop is stored but not named, since motion blur lowers it too. The check reports still holds of two or more near-still frames, including the step into a continuing clip ("Holds still: 3 frames at the join."). Holds enable Retake.
- **Settings for long continuing chains** (off by default; in the Studio under **Project settings → Long continuing chains**, or as Timeline JSON): `context_noise` (paired context noise on the carried frames; on a six-clip chain, clip 6's texture rose to 1.75x instead of 2.04x, about 10% slower), `continuation_guide: false` (no last-frame guide at the first new frame; removes the 3-frame join hold in moving shots) and `audio_feather` (the last carried audio ticks regenerate). See *Long continuing chains* in the guide.
- **H3 Sigmas Tail** node: raises the last noise levels before zero, optionally on continuing clips only (texture 1.93x alone, 1.67x with context noise).
- **H3 Continuation Model** node: samples continuing clips and bridges with another model, for a continuation LoRA.
- **Take ratings, tags and lineage.** Each take has five stars and a short tag (`takes_marks.json`), and a continuing take says which take of the clip before it came from.
- **Fork as a copy** in the Studio's **Project settings**: downloads the generation (the way back), then continues on a copy with every render and take.
- **`video_slices`** (**Split @video1 across clips** in the same Studio section): each clip receives only its own window of a long reference video and its soundtrack, for repainting a long video clip by clip.
- **Measurement tool.** `tools/measure.py` prints texture, colour drift and holds per saved segment; scenario S5 (one long reference video split across clips) joins the others in `examples/prefixstream_scenes/`.
- External Timeline preparation is `external-instructions-v10` and lists the new fields; the Timeline API schema declares them.

### Changed

- The Studio's **Feedback** button is now **Revise story**: it asks the Story writer to change the written story and doesn't send feedback to the node's author.

### Fixed

- **Project settings in narrow windows.** Below 900 px the Inspector and References panels float over the page that **Project settings** (and Story, Cast, Pictures and RefMods) opens, which made the button look like it did nothing. Opening one of those pages now closes them.

[Changes since v0.7.0](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.7.0...v0.8.0).

## [0.7.0] - 2026-11-04

### Added

- **Smoke comparisons.** `tools/smoke.py` runs a scene with named variations of Timeline settings, prompts or graph nodes, records each run's timing and status, and copies the full videos with duration, frame-count and audio-presence metadata into a JSON summary. When every variation produces a video, it also creates a side-by-side comparison. Use `--arm` to select variations and `--cap` to bound each render request.
- **Four comparison scenarios.** `examples/prefixstream_scenes/` includes a talking continuation chain, a walking phone conversation, a rooftop landing and two alternative story branches, with smoke specifications under `smoke/`.

### Removed

- **Split at guide.** Splitting inside a shot repeated its opening action in both prompts, which could restart a camera move. Use **Split before Shot N** at a timed shot boundary; the second clip starts with a **Cut**. First, Last and interior frame guides remain available, and saved projects keep their existing boxes, prompts, guides and joins.

### Fixed

- **Portable smoke output paths.** The smoke tool defaults to `$COMFY_ROOT/output` when `COMFY_ROOT` is set; otherwise it requires `--output`, instead of assuming one machine's folder.
- **Portable ComfyUI test setup.** The test runner supplies `COMFY_ROOT` from a detected Windows portable ComfyUI installation when the variable is unset, so CPU tests can load ComfyUI without manual environment setup.

[Changes since v0.6.0](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/compare/v0.6.0...v0.7.0).

## [0.6.0] - 2026-11-04

### Added

- **Replacement bridges (unavailable).** A Timeline can describe a bridge that *replaces around the cut*: H3 regenerates a reviewed region of the two clips with exactly as many frames, so the full video keeps its length and recordings stay in sync. In tests with real generations every candidate still jumped at its joins, so this version ships them switched off: nothing renders or plays a replacement, the original cut plays, and the Studio only offers to remove one. See [Joins and bridges](guide/continuity/joins-and-bridges.md#replacement-bridges).
- **Dialogue cues.** A recording's exact words at its own times, with speaker, on-screen or voiceover portrayal and a check against the recording. Import them from a timed transcript, take them from the Story or type them. Clips speak the cues in their window as `<d>` lines, and replacements keep on-screen speech and footage you mark. See [Dialogue cues](guide/sound/dialogue.md).
- **Locked recordings.** An uploaded audio clip can be locked to the sequence clock: no bridge may add time inside it, so its cuts stay cuts, and the Timeline names any inserted bridge or setting that would move the picture off it.

### Fixed

- **A dialogue cue span with a non-numeric start** is now refused with an *H3 Timeline: dialogue …* message instead of an internal `TypeError`.
- **Visual memory is judged with the audio lanes and cues already read.** `parse` checked each box's memory before the Timeline's audio lanes and dialogue were loaded, so every cue looked missing.
- **Checking a dialogue cue works on plain http.** The check key needed `crypto.subtle`, which only exists on HTTPS or localhost; ComfyUI opened on a LAN address could not tick **Checked**.

### Changed

- **Visual memory at a cut with speech.** When someone speaks on either side of a cut, the clip after it remembers the five frames before the cut instead of the full preceding video. H3 copied that video's lip movement onto the new shot, so the new clip's lines went out of sync. Such clips need a render. See [Visual memory](guide/continuity/visual-memory.md#how-it-works).
- Timelines that use replacements, cues or locks list them in `requires`. From this version on, a reader that doesn't know a listed feature stops with *this Timeline needs a newer H3 Continuity* instead of misreading the file. Existing bridges keep their meaning: a bridge without `mode` still inserts time.

### Known limits

- Replacement bridges are shipped switched off: every real candidate still jumped at its joins, so the original cut plays.
- An inserted bridge does not move dialogue cues. A recording that plays in the full video and is not locked drifts from the picture after the bridge by the bridge's length; a locked recording only gets a warning. Lock the recording and keep the cut.

## [0.5.0] - 2026-11-04

### Added

- **Agent skill pack.** `skills/` now holds seven skills that work together. `h3-continuity-video` is the entry, and six scoped skills cover joins and visual memory, timing, references and guides, sound and text, Story and Cast, and the API. Together they describe every feature, including visual memory, plates, RefMods, takes, the continuity check, long clips and voice clips, which the earlier single skill did not mention. `GET /h3c/timeline/instructions` serves the whole pack as `skills` (`instructions_revision` `external-instructions-v8`), and `python skills/install.py` links it into the agent skill folders on this computer.
- **22-frame context.** `context_frames` now offers 22 (0.9 s) next to 39, 90 and 141, in the node combos, the Timeline API schema and limits, and external Timeline preparation (`instructions_revision` `external-instructions-v9`). A continuing box adds the same new frames at 22 as at 39 and generates 17 fewer, so sampling is slightly cheaper; 39 stays the default because 0.9 s carries less motion into fast action.
- **Comparison tools.** `tools/side_by_side.py` lays clips out in a row on one clock with labels and one audio track per clip, and `tools/render_scene.py` renders a scene file box by box on a ComfyUI server with a time cap. `examples/prefixstream_scenes/` holds the memory and continuation test scenes they were used with.

## [0.4.0] - 2026-11-03

### Added

- **Resizable Studio panes.** Drag the handles between References, the center and the Inspector, and above the Timeline (arrow keys work on a focused handle; double-click resets a pane). The original fixed sizes are the minimums. A taller Timeline pane shows more lanes without scrolling; rows keep their height.
- **Timeline zoom.** `−`, `+` and `Fit` in the Timeline toolbar, or Ctrl+scroll over the lane to zoom around the pointer, from 100% (fit) to 1600%.
- **Layout memory.** Pane sizes and zoom are saved in the browser and restored on refresh.

## [0.3.0] - 2026-11-03

### Added

- **Split at guide.** A Shot marker with an accepted guide can split its clip there. The guide becomes the first clip's Last and the second clip's First, joined by Continue, so one clip ends exactly on the image and the next starts from it. Both halves round up to the frame grid. Later timestamps, guides, plate changes, pinned cast moments and chosen memories move to the second clip. A half that still mentions references gets FLF2VA + cached RefMods.
- **Tests.** `node tests/run.mjs` runs the browser-module tests and the package tests. A server-agreement test checks that the render code reads a browser split the way the browser intends.

### Fixed

- **Split before Shot N keeps Shot guides.** A guide accepted on a Shot marker now moves to its shot's new number in the second half. Before, it pointed at a shot that no longer existed and was dropped from the render.

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

[0.3.0]: https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/releases/tag/v0.3.0
[0.2.1]: https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/releases/tag/v0.2.1
[0.2.0]: https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/releases/tag/v0.2.0
[0.1.0]: https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/releases/tag/v0.1.0
