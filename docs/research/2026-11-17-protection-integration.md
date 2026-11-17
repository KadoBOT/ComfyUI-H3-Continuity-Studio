# Native protection integration and motion testing — 2026-11-17

## Scope and recovery

User requested the additional credits identified in PR #94, remaining attention integration and motion testing, and necessary follow-through. The previous provider pushed `fcf29cf` with native opt-in attention balance and explicit **ckinpdx / Carry Attention / ComfyUI-MMH3Tools** credits, then stopped before launching a test server. Its recorded CPU result was 402 JavaScript + 585 Python tests and 79 adapter tests. No GPU comparison existed at recovery.

## Independent review and fixes

One fresh read-only reviewer inspected `b39a05e..fcf29cf` and the connected native ComfyUI/Veda implementations. A partial override could balance block 31 while bypassing requested block 32, and the completed receipt would still list both. The parent reproduced that bug, added regressions covering both a missing block and a later missing evaluation, then changed validation to require every selected block on every model evaluation. Failure occurs on the first incomplete evaluation, before Save. Invalid block numbers now fail before sampling, and the schema assertion checks `enabled` and the neutral attention default by name. Fresh full suite: **402 JavaScript + 587 Python tests pass**. No second independent review is claimed.

The reviewer also identified the unequal SDPA dimensions: native query/key head width 128, value width 136 for two attention-share markers plus padding. On the installed Torch 2.14.1+cu130 and RTX 5090 Laptop, a bounded CUDA probe with 1,024 rows succeeded under memory-efficient SDPA. Flash-only and cuDNN-only probes failed to find a compatible kernel. This is a backend constraint, not a measured model speed/memory gain; no padding rewrite was needed for this host.

## Matched fixture

- Separate ComfyUI on port 8189, loading only this branch and a test-only scheduler alias. Original host on 8188 is not restarted and its workflow/story is not edited. Its idle resident models were unloaded using its supported `/free` API before testing.
- Three independent output folders copy the original story's saved clips 1–29. Later clips are omitted from each copied manifest, so an existing following take does not pin the ending. The original output folder remains read-only.
- Target is the original box 30, with its original length, prompt, seed 220129 and identical Same scene memories. The initial source is clip 29 and the clean historical anchor is the original first clip. This tests a late-chain continuation and the previously observed clip 29→30 camera-reset case.
- Same 10Eros beta7 INT8HQ checkpoint, 1152×640, 39 carried frames, free audio, native Euler, eight steps, beta57 (the native beta scheduler with alpha .5 / beta .7), sigma shifts 12 video / 3 audio. No enhancement, upscale or finishing stage.
- All arms use native dense attention. The original story uses Veda sparse attention, whose override bypasses balance; retaining Veda only in the baseline would confound the comparison. Results therefore do not directly compare speed or quality with the original Veda render.
- Arms: disabled protection; protection with neutral balance 1; identical protection with experimental balance 20 on the credited Geiru lighting blocks. Any effect of balance is compared against the protected arm, not attributed to the entire protection package.

Scripts, graphs, immutable submission receipts and logs are under ignored `.tmp/dp2/`; fixture JSON records source manifest and shared timeline hashes. GPU ticket `433397e7-e45a-451d-8364-93ee7afb900a`, owner `fec5d642-7e40-4228-9dbf-43bc9479fcd8`, coordinates this workload.

## Render evidence

All three prompts completed successfully and Save Segment wrote **85 played frames** per arm (124 native frames, including the 39-frame overlap). The same delivered memories were recorded in every arm. Normal sampler outputs were used in all GPU arms; callback-derived denoised output remains covered by the CPU regressions, not a separate GPU arm.

| Arm | Prompt receipt | Maximum carried-latent error | Applied descriptor |
| --- | --- | --- | --- |
| Baseline | `e642a05d-9c97-4f73-914f-ba27d734a221` | 1.1920928955078125e-7 | None |
| Protection, balance 1 | `ffcf2d5d-6dac-4113-81f3-a8cd617f3391` | 0 | Original clip 1 anchor, late start step 6/8, no attention adjustment |
| Protection, balance 20 | `aa53beb9-5f8c-4906-9910-31991f2834a3` | 0 | Same anchor and late schedule; balance 20 on all 13 requested lighting blocks |

Saved metadata contains only the completed applied descriptor. The original source manifest SHA-256 remains `2e955386a7e27c7121634bc36c92fe5a7b95f7be686aa9d3e91defffad9af43b`. Graphs normalized only for output-folder name and experimental controls have the same SHA-256, `a571222094180e957a206ddf1a47aea993750db62ba3ebdd11ac0f786f45f039`.

CPU analysis decoded the saved source MP4s with PyAV. Mean SDR luma uses coefficients .2126/.7152/.0722 on 144×80 RGB frames. Frame change is mean absolute RGB change at that size. Motion is mean DIS optical-flow magnitude; the motion summary excludes both transitions into played frames 1 and 2 to separate the reset from later movement. These are whole-frame proxies, affected by composition, exposure, subject movement and encoding; they do not isolate color fidelity or camera velocity.

| Arm | Mean luma (0–255) | Largest RGB change | Transition into frame | Later mean flow (pixels/frame) |
| --- | --- | --- | --- | --- |
| Baseline | 82.97 | 81.19 | 2 | 0.593 |
| Protection, balance 1 | 81.61 | 78.58 | 2 | 0.383 |
| Protection, balance 20 | 86.06 | 81.62 | 2 | 0.428 |

Inspected played frames 0–7 densely and frames 12, 48 and 84, plus brightness/motion curves and the generated comparison artifact. Every arm retains the dark outgoing camera view for its first two played frames, then resets abruptly toward the frontal establishing composition at frame 2. The original Veda reference resets one frame earlier. **The camera reset remains; neither protection nor attention balance passes the requested seamless-shot acceptance case.** The carried latents are intact, so these runs reinforce the prior distinction between generated camera re-establishment and lost overlap.

The balance-20 arm is somewhat brighter than protection alone in this sample. It still darkens as the camera pulls back and includes more of the shadowed foreground, so this cannot establish less progressive color degradation. The framing and pose also differ. All arms retain visible subject/camera movement; the protected arms have lower later flow than the baseline here, while balance 20 does not reduce that proxy further than balance 1. This is one seed and one late-chain continuation, not evidence about an entire protected chain or other models. Keep attention optional and neutral by default; no new production preset is justified.

Local artifacts: `.tmp/dp2/comparison.html` (video, charts and source-frame sheet), `comparison.mp4`, `comparison.png`, `curves.png`, `metrics.json`, `validation.json` and per-arm graphs/history receipts. Generated story media stays local rather than being added to the public PR. Integration succeeded; creative acceptance and general long-chain quality remain separate.

## Cleanup and final verification

The isolated queue was empty after all three successful receipts. Owned host PID 43360 was stopped and confirmed absent; its GPU memory was released (device usage returned to about 1.9 GiB for desktop/shared-host resources). The GPU ticket was finished and released with that factual cleanup note. Original ComfyUI PID 14784 remains alive on port 8188 and its queue is idle. No shared workflow/story, installation source or original output manifest was edited; there was no shared-host restart, merge or release.

Fresh verification after the review fixes: 402 JavaScript + 587 Python tests, 79 adapter tests, strict MkDocs, output/carry/memory validation and diff/roadmap checks. DP2 completion means this bounded integration and comparison was performed and its negative/uncertain visual results recorded. It does not mean the original story now meets seamless-shot or long-chain color acceptance.
