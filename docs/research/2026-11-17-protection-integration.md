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

In progress. Do not infer visual improvement from the CPU tests or successful queue acceptance. Record successful saves, actual source frames, motion/joins and resource cleanup here before DP2 can pass.
