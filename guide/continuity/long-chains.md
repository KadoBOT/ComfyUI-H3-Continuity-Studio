# Long continuing chains

Each continuing clip copies the end of the clip before it and adds its own small errors on top. Over many clips this compounds: skin, fabric and backgrounds get crisper and more etched ("burn"), the way a photocopy of a photocopy gains contrast. The [continuity check](check.md) measures it as texture drift, for example *Drift: 104% grainier than box 1.*

These settings are experimental and off by default. They were compared on one six-clip chain (a woman talking to camera in a kitchen, FastH3 omniref 8-step int8 at 960 × 544); results on other models and scenes may differ, so compare a few clips before relying on them. On this chain, the model changed the burn more than any setting did: see [The model matters most](#the-model-matters-most).

## H3 Continuity Protection

Add this optional graph node to target accumulated color and detail drift during sampling. It uses the original latent from the beginning of the current continuing chain, with sampler-level noise on the overlap and a second anchor introduced late. It does not require Geiru or another model. Existing graphs keep their current behavior.

Wire it once:

```text
Chosen sampling model ──> H3 Continuity Protection model ──> guider model
H3 Timeline latent ────> H3 Continuity Protection latent ──> sampler latent
H3 Timeline segment ───> H3 Continuity Protection segment ─> Save Segment segment
Sampler output (normal or denoised) ──────────────────────> Save Segment latent
```

Use the node's **returned segment** for Save Segment. Both sampler outputs restore the real carried frames before decode/save; the historical front anchor and temporary late capstone never become visible extra frames. Save rejects an output that did not complete the matching protected sampling pass, before moving takes or writing files. Audio generation, held audio and clip lengths remain on their existing clocks.

Turn off the Studio's old **Context noise** control first: it is a separate pixel-noise treatment and cannot be combined with this node. Besides **enabled**, the node has an optional [attention balance](#attention-balance), off at 1. It leaves fresh clips, cuts, bridges and non-continuing layers unchanged; anchors reset at the next continuing chain on the same track. An authored appearance change suppresses protection through the next fresh clip, so an old look is not forced back. An authored Last/frame guide or a protected following neighbor suppresses only the late capstone; the node's info explains this.

Protection needs a current native MiniMax H3 AV model with partial masks and an ordinary finite descending sigma schedule ending at zero. It rejects **Context Windows**, including windows added downstream. Missing or changed source takes and resolution mismatches require preparing/rendering the chain again; no source is silently substituted or resized.

**Protected continuations bypass H3 Disk Cache** because Save needs a live sampling receipt. Disabled/fresh paths retain existing cache behavior with the usual Timeline positive/latent/seed keys. Adding or toggling this graph node does not automatically mark old rendered clips outdated: use **Regenerate** on affected clips or start an independent generation. Old takes stay until replacements save successfully. See [the node reference](../reference/nodes.md#h3-continuity-protection) and [cache limits](../output/first-pass-cache.md#continuity-protection).

This feature has CPU checks for masks, native sampler outputs, joins' carried data and safe saves. A [matched GPU test of the first wall-darkening onset](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/blob/feat/continuity-protection/docs/research/2026-11-17-wall-darkening-onset.md) rendered only clip 2 of the user's 10Eros beta7 story, from the same bright clip 1. **Balance 20 worsened the tracked wall's darkening and color deviation; neutral protection showed no clear color-fidelity gain.** Motion remained visible. Keep attention neutral by default; this recipe has not passed wall-preservation acceptance. A separate [clip-30 integration/jump test](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/blob/feat/continuity-protection/docs/research/2026-11-17-protection-integration.md) also retained the camera reset. Compare matched prompts, seeds, model/schedule and memory, and watch motion and joins as well as color. This node is not a demonstrated fix for either issue on this story.

Visual memory serves a different purpose. If a prop leaves the camera view, choose **Selected** memory from a moment that clearly shows it and label the details to retain. Automatic Same scene memory already includes an establishing view and recent view; those views may not clearly cover every object. Protection is not an object-permanence guarantee.

### Attention balance

Experimental. Clean anchors alone can still leave a chain slowly darkening, because each new clip reads its held carried frames far more than the single clean anchor. `attention_balance` changes that split and nothing else: of the attention a token gives to the anchors and the held carried frames together, the anchors take `balance` times their normal weight and the carried frames give up exactly that much. Attention to the prompt, references, audio and new frames is unchanged. **1 leaves attention unchanged** while the node's other protection remains active; Geiru's own default for the equivalent control is 20.

`attention_blocks` chooses existing transformer blocks as numbers and ranges. Invalid indices fail before sampling. The default, `31-33, 36-44, 47`, is the set Geiru reports as carrying brightness on H3. That is Geiru's finding, not our measurement.

Use native attention for this experiment. Veda's sparse attention can bypass the balance hook, regardless of node order. Every selected block must run the balance on every model evaluation; a bypass fails that evaluation instead of saving a partly balanced result. This path uses PyTorch SDPA with extra value channels; it needs a backend that supports unequal query/key and value dimensions. Memory-efficient attention works on the tested Windows host; CUDA Flash attention is not available for this shape.

Geiru reports less motion as the cost, and a strong pull toward an old frame can also pull pose and framing. Raise it in steps and compare motion and joins, not only color. Each balanced block runs three attention passes instead of one, so those blocks are slower. If another node replaces H3's attention on those blocks, so the balance cannot run, sampling stops with an error instead of saving a clip that only claims to be balanced; set the balance to 1 or remove that patch.

### Credits and upstream developments

The clean keystone/capstone and late-locking ideas are credited to **roycho87's [Geiru Context Suite](https://github.com/roycho87/geiru_context_suite)**. Sampler-synchronized context noise is credited to **ethanfel / Lumifel** and [H3 Context Loop](https://github.com/ethanfel/ComfyUI-MiniMaxH3-Context-Loop), whom Geiru also credits. This is an independent native implementation using ComfyUI APIs; Geiru's GPL-3.0 code is not vendored here.

The attention balance follows Geiru's **Keystone Attention** (reviewed at commit [099da1b](https://github.com/roycho87/geiru_context_suite/commit/099da1be92f2da22a775076a0d533d29b4d97268)), including its lighting blocks. Keystone Attention is based on an idea by **ckinpdx**: biasing H3's attention by part of its sequence, published as **[ckinpdx's Carry Attention](https://github.com/ckinpdx/ComfyUI-MMH3Tools)** in ComfyUI-MMH3Tools. Our version is written independently on ComfyUI's attention override; Geiru's own node expects Geiru-specific latent metadata and is not a drop-in after ours.

The same update moves whole-video Hybrid Windows state to system RAM and samples cropped windows. Our continuing-clip path already renders one clip at a time and does not own that whole-video state, so it has no corresponding Hybrid Windows memory fix to import. Context Windows remain unsupported by our protection node. Neither Geiru's visual-quality nor its memory results are measurements of this implementation.

## What was measured

The historical measurements below concern the older settings named in each row, not H3 Continuity Protection.

Texture is the finest-detail energy of each clip against clip 1 (1.00 = no change). A "jump" is the largest frame-to-frame change at a join; the unchanged chain's joins measured 2.5 to 4.2.

| Setting | Clip 6 texture | Joins | Result |
| --- | --- | --- | --- |
| None (default) | 2.04 | 2.5–4.2 | Burn builds steadily. |
| `context_noise` | **1.75** | 2.6–3.2 | Much less burn; same framing; about 10% slower per continuing clip. |
| H3 Sigmas Tail, 3 steps, 0.5 | 1.93 | 2.4–3.2 | A little less burn. |
| `context_noise` and Sigmas Tail together | **1.67** | 2.7–3.3 | The least burn of all; same framing. |
| `continuation_guide: false` | 2.19 | 4.1–5.8 | See below: removes a hitch in moving shots. |
| Anti-burn LoRA 0.5 via H3 Continuation Model | (1.77) | **59 at clip 2** | Cut to a close-up at the first join; rejected. |
| Anti-burn LoRA 0.3 | 1.99 | 2.5–3.2 | No measurable effect on FastH3 int8. |

## The model matters most

The table above is `fasth3_omniref_8step_pruned_int8_convrot`. The same chain on MiniMax's REF2VA model (`minimax_h3_ref2va_pruned_int8_convrot` and `minimax_h3_ref2va_pruned_bf16`) with the ref2v turbo LoRA (`minimax_h3_ref2v_turbo_8step_v1.1`) burned far less in both files, so the difference comes from the model, not from int8.

FastH3 v2 (`fastvideo_fasth3_8step_v2_pruned_int8_convrot` with turbo LoRA `minimax_h3_ref2v_turbo_8step_v1.0` at 1), which the Story Studio examples render video with, did not burn (clip 6 texture 0.97), but in every render clip 2 cut to a closer framing one frame after the join. That held with the examples' own sampler (res_multistep) and with a second seed. Each time, clip 1 had come out wider than the "medium close-up" every prompt names, and clip 2 moved to the prompt's framing instead of keeping clip 1's; the later joins were smooth. The anti-burn LoRA did not change the cut. On this model, check the first join of a long chain. Whether a clip 1 that already matches the prompt's framing avoids the cut was not measured, and other models were not measured.

| Model and anti-burn LoRA | Clip 6 texture | Joins | Result |
| --- | --- | --- | --- |
| REF2VA int8 | 1.19 | 1.1–1.8 | Little burn with no setting. |
| REF2VA int8, anti-burn LoRA 0.3 | 1.16 | 1.0–1.7 | No clear effect. |
| REF2VA int8, anti-burn LoRA 0.5 | **1.04** | 1.1–1.3 | No cut. Clip 2 rises to 1.17, then later clips settle instead of climbing. |
| REF2VA bf16 | 1.25 | 1.0–1.8 | Like int8. |
| REF2VA bf16, anti-burn LoRA 0.3 | 1.16 | 1.0–1.7 | Slightly lower, within what the seed can move. |
| REF2VA bf16, anti-burn LoRA 0.5 | 1.23 | 1.1–1.5 | No cut; clip 2 rises to 1.36. |
| FastH3 v2 int8 | 0.97 | **36 at clip 2**, then 1.4–1.6 | No burn, but clip 2 cut to a closer framing. |
| FastH3 v2 int8, anti-burn LoRA 0.3 | 0.92 | **36 at clip 2**, then 1.3–1.5 | The same cut. |
| FastH3 v2 int8, anti-burn LoRA 0.5 | 0.86 | **37 at clip 2**, then 1.3–2.1 | The same cut. |
| FastH3 v2 int8, res_multistep | 0.95 | **39 at clip 2**, then 1.5–1.8 | The same cut with the examples' sampler. |
| FastH3 v2 int8, res_multistep, another seed | 0.90 | **45 at clip 2**, then 1.4–2.8 | The same cut; the 2.8 is a hand gesture. |

Each row is one render of this chain; differences of about 0.1 can come from the seed alone. The first three FastH3 v2 renders share clip 1 and the seed (the LoRA only reaches continuing clips), so their cuts count as one; the two res_multistep renders each made their own clip 1, so the cut was seen after three different clip 1s. Every row used euler at 8 steps except the two res_multistep rows, the sampler the Story Studio examples use for FastH3 v2 (same 8 steps and scheduler). On a 24 GB GPU a continuing clip took about 1 min 40 s on the int8 files and 2 min 40 s on the 40 GB bf16 file, which does not fit and streams from system memory.

## Context noise

Tick **Context noise** in the Studio ([below](#in-the-studio)), or add `"context_noise": true` to the Timeline JSON (or send it through the [API](../automation/api.md)). For each continuing clip, the carried frames are decoded, given seeded noise that fades from strong at the start of the overlap to none at its last frame, and encoded again; only the difference the noise makes is added to the original carried latent, so the VAE's own round-trip error is not carried forward. The carried frames stay frozen while H3 samples; audio is unchanged. It costs one decode and two encodes of the overlap per continuing clip.

## Guide at the first new frame

A continuing clip normally uses the previous clip's last frame as a guide at its first new frame, so the pose does not reset. In moving shots this produces a short hitch: about three nearly identical frames at the join, which the check reports as *Holds still: 3 frames at the join.* Unticking **Guide from the last frame** in the Studio (`"continuation_guide": false`) removes the guide and the hitch; in calm shots the join then moves a little more. It is a per-Timeline setting; the default keeps the guide.

## H3 Sigmas Tail

A node for your graph (`BasicScheduler → H3 Sigmas Tail → the sampler's sigmas`, with the Timeline's `segment` connected so clip 1 is unchanged). It raises the last noise levels before zero, so the final step of a distilled model settles less fine detail. See [Nodes](../reference/nodes.md#h3-sigmas-tail).

## H3 Continuation Model

Routes continuing clips (and bridges) to a different model, for a LoRA trained for continuations. The public H3 Anti-Burn LoRA did not help on FastH3 int8 and cut to a close-up at 0.5 ([first table](#what-was-measured)). On MiniMax's REF2VA model with the turbo LoRA, the base its authors tested it on, 0.5 caused no cut and kept later clips from climbing ([The model matters most](#the-model-matters-most)), though that model burns little without it. On FastH3 v2 it did not change that model's cut at the first join.

## In the Studio

**Project settings → Long continuing chains** holds these Timeline settings.

| Control | Timeline key | Default |
| --- | --- | --- |
| **Context noise** | `context_noise` | off |
| **Guide from the last frame** | `continuation_guide` | on |
| **Audio feather**, in ticks of 25 ms | `audio_feather` | 0 |
| **Split @video1 across clips**, one per reference video | `video_slices` | off; see [References](../build/references.md) |

They apply to every continuing clip; a split video applies to every clip that mentions it. Changing **Context noise**, **Guide from the last frame** or **Audio feather** marks those clips as changed until they render again. A split changes only the video frames and sound those clips receive, which the Studio cannot see before a run: clips already rendered still show as rendered, and **Run** in the graph renders them again, one clip per run.

**Audio feather** lets the end of the carried audio regenerate: over that many ticks (up to 16, which is 0.4 s), the carried sound fades from frozen to free, which can soften an audible seam at the join. At 0 the carried audio stays frozen.

H3 Sigmas Tail is a node in your graph, so it has no control here.
