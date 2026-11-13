# Timeline and clips

The Timeline is a list of **clips**. Each clip is one H3 generation with its own prompt, seed, length and join. The strip along the bottom of the Studio is where you arrange them.

[![The Timeline strip, with six rendered clips and a bridge](../assets/screens/timeline-strip.png)](../assets/screens/timeline-strip.png)

## Add, resize and arrange

| To | Do this |
| --- | --- |
| Add a clip | **+ Clip** in the Timeline toolbar, or drag after the last clip on the track to draw one. |
| Resize a clip | Drag its right edge. Lengths snap to H3's frame grid (see below), unless the clip uses [Exact length](exact-lengths.md). With [beats detected](../sound/audio.md#add-audio) and **Snap to beats** ticked, the edge also lands on the nearest beat. |
| Find a moment | Click or drag the ruler: the playhead moves there and the [video so far or the full video](../output/full-video-and-projects.md#the-full-video) plays from that moment. |
| Select a clip | Click it. The right-hand panel and the Viewer follow. |
| Add another video of a clip's time | **+ Video** in the clip's **Settings**: a second angle that the clip swaps to. See [Videos in one clip](video-layers.md). |
| Move, copy or delete | **Clip N actions** in the panel: move earlier or later, **Duplicate** (the copy gets a new seed) or **Delete**. |
| Split a clip | A clip whose prompt has more than one `[Shot N]` offers **Split before Shot N** in its **Shots** tab. Later shots need increasing `At MM:SS.mmm,` timestamps. The split separates the shots into two clips, with the second starting as a **Cut**; each half keeps the references it uses and accepted guides move with their shots. A bridge before the clip stays with the first half. Frame guides do not offer a separate split action. |

!!! info "H3's frame grid"
    H3 generates at 24 fps, in lengths of `17k + 5` frames for a clip that starts fresh (at least 22) and `17k` new frames for a clip that continues the one before (at least 17). Without Exact length, every clip snaps to that grid. The default maximum is 362 frames; see [Long clips](long-clips.md) to raise it.

## Join with the previous clip

Open a clip's **Settings** tab.

[![Settings tab](../assets/screens/clip-settings.png){ align=right width=280 }](../assets/screens/clip-settings.png)

- **Continue** (both **Cut** and **New scene** off): the clip carries the previous clip's last frames, `context_frames` of them, as native H3 context, so motion and sound continue.
- **Cut**: a new camera angle in the same place. No frames are carried, but with [visual memory](../continuity/visual-memory.md) the clip can still remember the scene.
- **New scene**: a cut to a different place, time or look. It starts a new scene for visual memory.
- On a Timeline with a [Story bible](../story/cast.md), a **Join** selector (Continue, Transition, Cut, New scene) replaces the two switches.

A **bridge** is a generated move between two rendered clips; see [Joins and bridges](../continuity/joins-and-bridges.md).

## The Settings tab, section by section

**First & last frame**
:   Pick a picture as the clip's first or last frame, or **Upload…** one. See [First and last frames](frame-guides.md).

**Join with previous clip**
:   The **Cut** and **New scene** switches described above.

**Length**
:   The clip's length, with the **Exact length** switch for [frame-exact edits](exact-lengths.md).

**Seed**
:   The clip's seed, a button for a new random seed, and a **Seed mode**. The seed belongs to the clip, so changing it renders only that clip again.

**Bridge**
:   **Insert bridge** (extra frames outside Timeline time) or **Replace around the cut** (a reviewed region regenerated within it, unavailable for now), shown on a join that cuts. See [Joins and bridges](../continuity/joins-and-bridges.md#bridges).

**FLF2VA + cached RefMods**
:   An experimental per-clip switch that converts first, last and reference images into reusable RefMods. It is off by default. Use it only with the matching example workflow.

    A clip that runs as REF2VA shows **Convert to FLF2VA** under its mode line. The button turns this switch on: the clip's First and Last frames, and accepted guides at those frames, become its start and end frames, and the images it mentions become cached image RefMods. Audio it mentions (`@audio1`, or an audio clip in the audio lane under this clip) stays an audio reference, encoded by the H3 audio VAE exactly as REF2VA encodes it and numbered before any audio RefMods. The button is disabled, with the reason beside it, when the clip cannot convert:

    - **Raw video** (`@video1`, `@video_audio1`): the Studio cannot convert a video to a RefMod. Create a video RefMod with RefForge's **Create H3 RefMod** node, assign it on the **RefMods** page, and mention that slot instead.
    - **No First frame** on a fresh clip: choose one under **First & last frame** or accept a First guide.

**Visual memory**
:   Which earlier moments this clip is shown. See [Visual memory](../continuity/visual-memory.md).

## Rendering

| Button | Renders |
| --- | --- |
| **Render next** | The next clip that is not current, or once every clip is current, the next [bridge](../continuity/joins-and-bridges.md#bridges). |
| **▶ Render N remaining** | Every clip that has no saved take, in Timeline order, then every bridge that needs a render. [Outdated](#outdated-clips) clips keep their take; regenerate them one by one. |
| **Generate clip N** | Only that clip. The number beside it sets how many [takes](../continuity/takes.md) to render (1 to 10), each with a new seed. |

ComfyUI's **Run** button also works: each queued run renders the next clip that needs it.

A long Render keeps only three runs in ComfyUI's queue. It adds one as each finishes, and stops at the first run that fails, so a clip that cannot render is not retried down the whole queue. The progress line shows how many runs are still to be queued. Keep the page open while it works; if the page closes, the runs already in ComfyUI's queue finish and the rest wait for the next **Render**. After a failure, fix the cause and press **Render** again: it carries on with the clips that are not rendered yet. **Settings → H3 Continuity → Timeline** sets the number of runs kept queued; 0 queues every run at once.

A clip is **current** when its saved render still matches its prompt, seed, length, join, pictures, memory and the node's settings. Change any of those and the clip needs a render again; the Timeline says why when you point at it. A clip that **continues** another also needs a render when the clip before it renders again.

!!! tip "Re-rendering one clip"
    **Generate clip N** renders only that clip, with its saved neighbours as anchors. Re-rendering can put later clips that continue it, or remember frames from it, out of date; the Timeline marks them and says why, and nothing renders again until you ask.

If the next clip's saved starting frames cannot be reused (for example, it was rendered as a Cut or at another resolution), **Generate clip N** asks before queueing. The confirmation lists the dependent clips that will need rebuilding. Their existing videos and affected bridges move to **Takes** only after the new clip saves successfully; independent clips keep their renders. Cancelling or a failed save leaves the existing renders in place. Use **Render remaining** afterward to rebuild continuity and the complete video. Start this recovery with **1** take; once continuity is rebuilt, you can generate multiple takes again.

## Where files go

### Start another generation

Open **Project settings → Start a new generation** to generate a new version using the same Timeline and prompts. After confirmation, every clip and bridge starts unrendered in a separate render folder. Prompts, clip lengths, seeds, guides, references and render settings stay as they are; nothing is queued automatically.

The old generation's videos, latents and Takes stay in their original folder. **Previous generations**, in Project settings, links to their joined videos and individual clips, even when a generation was only partly rendered. Wait for Story writing, uploads and rendering to finish before switching. Attached API projects remain intact; the new generation uses the current workflow as a fresh native render workspace.

### Outdated clips

A clip whose prompt, length, settings or references changed after it rendered, or whose remembered clip was rendered again, is **outdated**: it keeps its picture and video, is drawn with a dashed border and ⟳, and plays in the full video until you regenerate it. Its tooltip says what changed. **Render N remaining** does not re-render outdated clips; select one and press **Regenerate clip N** to update it.

Saved takes stay with their clip, not its position: inserting, removing or moving a clip never hides the clips after it, and rendering a clip normally moves only that clip's earlier take to `takes/`. Confirmed continuity recovery also archives the dependent clips named in the warning. Takes of a clip you removed stay in the folder and come back with the clip (for example through Undo).

If a status check fails or times out, the Studio keeps showing the clips it last knew about, with a note, instead of showing them as unrendered.

Renders are written to `output/h3_sequences/<name>/`: one MP4, one latent file (`.safetensors`) and a last-frame PNG per clip, a manifest, the full video, and a `takes/` folder for earlier renders. Keep the folder together; the latents are what let a later clip continue exactly.

## Status you can read

The head of the Studio reads like **6 clips · 30.8 s · 1 bridge, +1.9 s · All 6 boxes are rendered.** The *+1.9 s* is the time inserted bridges add to the *full video only*; the Timeline's own time, audio lanes and timed text do not include it. [Replacements](../continuity/joins-and-bridges.md#replacement-bridges) are counted after it, for example *· 2 replacements*, and add no time.
