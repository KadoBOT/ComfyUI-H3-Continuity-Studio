# Continuity Degradation Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one opt-in native H3 Continuity Protection node that reduces accumulated continuation drift with sampler-level context noise, clean front anchors and late capstones while preserving original carried frames in both sampler outputs.

**Architecture:** Timeline supplies lightweight runtime source provenance using its existing track/manifest information. A new protection module prepares the carried-video mask, clones/patches the sampling model and returns an owned segment with an executed receipt; Save validates that receipt before writing. Protected runs safely bypass disk sampling cache; existing graphs remain unchanged.

**Tech Stack:** Existing Python, PyTorch, ComfyUI packed AV latents/model wrappers, unittest and node:test. No new packages, models or LoRAs.

**Spec:** `docs/superpowers/specs/2026-11-15-degradation-protection-design.md`, explicitly approved by the user on 2026-11-15.

## Global Constraints

- "The explicit node is opt-in: existing graphs and Timeline JSON retain their exact behavior."
- "No full VAE decode/re-encode is needed for this protection."
- "Public mechanisms will be implemented independently against ComfyUI APIs"; attribute the Geiru/ethanfel work, copy no upstream implementation.
- "Restore every original carried video latent in both normal sampler output and `SamplerCustomAdvanced.denoised_output` before decode, caching and save."
- "Keep old clips/takes until their replacements save successfully."
- "No live deployment/restart during the current queue."
- "No new package/model/LoRA dependency."
- Preserve frames/exact durations, seeds, guide placement, audio clocks, joins, takes, source files and all pre-existing dirty files. Free audio still generates normally; do not replace the entire audio stream with source audio.
- No Studio checkbox/Timeline creative key, memory subsystem, automatic grading, hybrid windows, cache-receipt persistence or workflow migration. Missing/unsupported setup raises before sampling; receipt failures raise before writes.
- DP2 visual comparison needs separate explicit GPU authorization and the shared GPU skill. CPU verification does not establish visual improvement.
- Execute in an isolated workspace using `using-git-worktrees`/available native isolation at execution time. Start from the local commit containing this approved spec and plan; do not lose these unpublished documents by starting from origin/main alone. This planning turn creates no worktree or workers.

## Review Focus

- A legacy/unused source entry is missing: old graphs must still work; defer new anchor validation until the optional node is enabled (Task 1).
- Callback x0 is in internal coordinates while normal samples are in output coordinates: both must restore identically without altering audio or breaking previews (Task 3).
- One sigma triggers several predictor/corrector or CFG calls: activate by schedule position, never call count, and do not append a second capstone (Task 3).
- A failed reroll or stale/plain cache output reaches Save: reject before directory creation, take movement or manifest changes (Task 4).
- A plate change occurs inside a continuing box, or track array order differs from playback: suppress through the next fresh boundary and never borrow an unrelated anchor (Task 1).

## Files and shared contracts

| File | Responsibility |
| --- | --- |
| `h3_continuity/protection.py` (new) | Source selection/validation, latent preparation, scoped model wrappers, runtime receipt, node schema |
| `h3_continuity/nodes.py` | Append optional SegmentPlan runtime fields; minimal Save receipt validation/metadata bridge |
| `h3_continuity/timeline_node.py` | Attach deferred provenance after guide/ending decisions on the main continuation path |
| `h3_continuity/extension.py` | Register `H3C_ContinuityProtection` |
| `h3_continuity/agent_api/coverage.json`; `tests/test_agent_resources.py` | Advertise graph-only node and update actual inventory checks (currently 19 nodes) |
| `tests/python/test_protection_source.py` (new) | Track/cut/appearance/source identity and deferred failure checks |
| `tests/python/test_protection_latent.py` (new) | Native AV masks, front anchor and input preservation |
| `tests/python/test_protection_sampling.py` (new) | Installed-core wrappers, both sampler output paths, capstone scheduling, receipts |
| `tests/python/test_protection_save.py` (new) | Save boundary, metadata and no-write failures |
| `tests/python/test_disk_cache.py` | Actual executor proof of protected safe bypass and ordinary pass-through behavior |
| `README.md`; `guide/reference/nodes.md`; `guide/continuity/long-chains.md`; `guide/output/first-pass-cache.md`; `docs/MCP.md`; relevant pack skills; `CHANGELOG.md`; `tests/README.md` | Wiring, compatibility, verification commands and truthful scope |

Append `SegmentPlan.protection_source: dict | None = None` and `protection_receipt: object | None = None`; default values preserve positional callers. Source/receipt are runtime fields, never authored Timeline JSON. Avoid importing protection from nodes at module import time; use a local import in Save's protected branch to avoid the node/module cycle.

Public helpers in `protection.py`:

- `source_info(parsed, index, entries, is_done, guides, ending) -> dict`: pure/deferred provenance, status `ready|skip|error`; no latent reads or new failures in unprotected Timeline execution.
- `load_anchors(segment) -> tuple[Tensor, Tensor | None, dict]`: validates the ready source, reads/clones the two required slices and returns front/capstone plus an immutable JSON-safe descriptor.
- `prepare_latent(latent, segment, front) -> tuple[dict, Tensor]`: returns a new latent and original carried video, leaving caller data untouched.
- `patch_model(model, prepared, segment, originals, capstone, descriptor) -> tuple[ModelPatcher, ProtectionReceipt]`: cloned wrappers and runtime-only opaque receipt.
- `validate_save(segment, latent) -> dict | None`: validates full output identity, returns JSON-safe applied metadata, or raises before writes. Returns None for ordinary segments.
- `H3C_ContinuityProtection.execute(model, latent, segment, enabled=True) -> io.NodeOutput`: outputs MODEL, LATENT, H3C_SEGMENT, STRING in that order.

The descriptor identifies method `h3c-continuity-protection-v1`, source box/index/take identity and source latent content identity, context count and capstone suppression reason. The completed save record adds actual late-lock activation. `ProtectionReceipt` is an ordinary opaque runtime object, not a dataclass/dict that the disk-cache key encoder can accidentally serialize. Its state belongs only to the returned segment/model pair; every sampling invocation resets success/output digests before running and failure leaves it incomplete. Store only completed descriptor data, never the receipt object or output digests.

## Task 1: Source provenance on the native Timeline path

**Files:** Create `h3_continuity/protection.py`, `tests/python/test_protection_source.py`; modify `h3_continuity/nodes.py:SegmentPlan` and `h3_continuity/timeline_node.py:H3C_Timeline.execute` after ending protection is known.

**Interfaces:** Consume `timeline.continuation_chain/previous_index`, existing `by_index`/`is_done`, accepted guides and `SegmentPlan.ending_video`. Produce the two optional SegmentPlan fields, `source_info` and `load_anchors` above. Snapshot entry/provenance dictionaries by value; no live manifest references in an owned plan.

- [x] **1. Write CPU source tests:** `test_tracks_choose_the_playback_chain_not_array_or_manifest_one`, `test_cut_or_gap_resets_anchor`, `test_in_chain_plate_change_suppresses_until_next_fresh_box`, `test_legacy_graph_defers_missing_source_failure`, `test_take_change_rejects_prepared_source`. Assert source box IDs match playback order; fresh/bridge/replacement/non-continuing-layer status is skip; first-call provenance performs zero `store.load_video_window` calls; enabled loading rejects missing/currentness/identity/geometry changes. Include `new_scene` on a continuation and a plate change at a nonzero frame: skip to the next fresh boundary.
- [x] **2. Run RED:** `python -m unittest discover -s tests/python -t . -p test_protection_source.py -v`; expect missing protection API or failing source assertions, not an import/environment failure.
- [x] **3. Implement the shared contracts:** attach `source_info` only on the main Timeline path after guides/ending are finalized. Use `continuation_chain`, never numeric segment adjacency. Ready source records contain copied entry identity and expected geometry; error records postpone the error to `load_anchors`. Loading checks the current entry/take/file identity and original latent shape, using `store.load_video_window` for slot 0 and the last single-frame block inside delivered source frames (exclude generated padding beyond its played endpoint). Capstone is None with an explicit reason for protected endings or conflicting authored last/interior guides. Preserve old `context_noise` information for the later incompatibility check. No VAE calls or disk writes.
- [x] **4. Run GREEN:** the new suite and `python -m unittest discover -s tests -t . -p test_context_noise.py -v`; expect no failures and unchanged old noise semantics. Inspect all `SegmentPlan(` callers with `rg` and run the owning existing timeline/layer tests if integration touches them.
- [x] **5. Commit only this task's explicit paths:** `feat: identify native continuity protection anchors`. Checkpoint DP1 partial state, source rules and exact test result before Task 2.

## Task 2: Prepare sampler-level context noise without changing audio

**Files:** Modify `h3_continuity/protection.py`; create `tests/python/test_protection_latent.py`.

**Interfaces:** Consume Task 1's `load_anchors` output and SegmentPlan. Produce `prepare_latent(latent, segment, front) -> (prepared, originals)`. `originals` contains all real carried video slots in output latent coordinates, not the grafted front.

- [x] **1. Write native AV assertions:** in `test_front_anchor_and_linear_mask_preserve_free_video_and_audio`, build with `latents.build_continuation` for context 22/39/90/141. Assert slot 0 equals the clean front with mask 0; remaining carried masks equal `linspace(1, 0, tokens-1)`; final carried mask is 0; free masks stay 1; original samples/masks are unchanged; audio samples/masks including audio feather are bit-identical to the input; returned originals equal the real pre-graft carry. Add `test_rejects_old_pixel_noise_and_incompatible_masks` and shape/batch/dtype cases with full/expanded masks.
- [x] **2. Run RED:** `python -m unittest discover -s tests/python -t . -p test_protection_latent.py -v`; expect API/assertion failure.
- [x] **3. Implement `prepare_latent`:** use native nested AV layout and exact context-token count, cloning only edited tensors. Reject the old paired pixel-noise flag, mismatched anchors and unsupported mask patterns. Preserve legitimate audio feather and frozen neighbor ending masks. Validate native MiniMax partial-mask support from installed core without loading weights; no global model changes or conversion to pixel noise.
- [x] **4. Run GREEN:** the new suite, `test_wave1_overlap22.py`, `test_context_noise.py` and `test_audio_feather.py` via unittest discovery; expect zero failures, correct taper and untouched existing controls.
- [x] **5. Commit:** `feat: prepare sampler-level continuity context noise`; record exact CPU evidence and remaining wrapper work in DP1.

## Task 3: Scoped sampling, late capstone and both restored outputs

**Files:** Modify `h3_continuity/protection.py`; create `tests/python/test_protection_sampling.py`.

**Interfaces:** Consume Task 2's prepared latent/originals plus Task 1's capstone/descriptor. Produce `patch_model` and opaque `ProtectionReceipt`; receipt completion contains accepted normal/denoised output digests and the executed descriptor. Reuse existing `disk_cache.content_digest` for canonical tensor/dtype/shape identity, not a second hashing implementation.

- [x] **1. Write installed-core CPU regressions:** `test_normal_and_denoised_outputs_restore_every_carried_slot`, `test_callback_uses_internal_coordinates_and_preserves_previews`, `test_capstone_enters_last_quarter_once_per_model_call`, `test_existing_wrappers_cfg_batches_and_audio_survive`, `test_reroll_failure_clears_previous_receipt`, `test_anchor_take_change_before_sampling_fails`, `test_context_windows_are_rejected_before_sampling`. Use actual `comfy.utils.pack_latents/unpack_latents`, `WrapperExecutor`, native MiniMax mask conversion and `SamplerCustomAdvanced.execute` with fake weight-free model evaluation. Do not replace the code under test with a test-only copy. Assert both output branches retain shape and exact carried values, predict no capstone frames in output, and have different identities when their free predictions differ. Test callback exceptions as failed/incomplete runs.
- [x] **2. Run RED:** `python -m unittest discover -s tests/python -t . -p test_protection_sampling.py -v`; expect failing wrapper/API assertions. No GPU/model file loads are allowed in this test.
- [x] **3. Implement `patch_model` and receipt:** clone the model, compose existing UNet/OUTER_SAMPLE wrappers and preview callback, and reset receipt before invoking sampling. Restore normal output after the executor and restore callback x0 in the coordinates expected by core `process_latent_out`; leave free audio/free video predictions intact. For nonzero sampler schedules validate finite descending sigmas; use the current sigma's schedule interval, including intermediate predictor/corrector evaluations, to activate at `ceil(0.75 * step_count)` (8 steps → last 2). Do not use nearest-sigma rounding or a model-call counter for intermediate evaluations. Append one locked video capstone only inside each eligible model call, update native latent shapes/masks locally, compose the previous wrapper and strip that added slot from the prediction. Restore/identity-check before receipt completion; any failure invalidates it. Check source identity again at invocation start. Explicitly reject `model_options['context_handler']` and any runtime context window for v1; reject nested application of this node rather than double-wrapping shared state. Include schedules with 4/8/12 steps, repeated/intermediate sigmas, nonzero terminal sigma or ambiguous schedules as explicit setup errors, both predictor/corrector calls and CFG-expanded batches.
- [x] **4. Run GREEN:** source/latent/sampling suites and the existing `test_continuation_model.py`/`test_sigmas_tail.py` checks. Assert all input tensors and the original model's wrappers/options are byte/identity unchanged, no state leaks between different prepared segments, and unsupported settings fail before the first model call. Verify no audio timeline ticks or protected ending slots change.
- [x] **5. Commit:** `feat: sample continuity anchors with exact output restoration`; checkpoint CPU results, supported core interfaces and explicit Context Windows rejection.

## Task 4: Node, Save receipt boundary and safe cache bypass

**Files:** Modify `h3_continuity/protection.py`, `nodes.py:H3C_SaveSegment.execute`, `extension.py`, `agent_api/coverage.json`, `tests/test_agent_resources.py`, `tests/python/test_disk_cache.py`; create `tests/python/test_protection_save.py`.

**Interfaces:** Consume Tasks 1–3. Produce registered `H3C_ContinuityProtection` with inputs `model`, `latent`, `segment`, `enabled=True`; outputs `model`, `latent`, `segment`, `info` in slots 0–3. Produce `validate_save(segment, latent) -> descriptor|None`.

- [x] **1. Write integration assertions:** `test_disabled_and_fresh_node_pass_through_without_source_reads`, `test_save_accepts_normal_or_denoised_receipt_only`, `test_save_rejects_pending_failed_stale_or_plain_cached_output_before_writes`, `test_metadata_contains_only_applied_descriptor`, `test_node_schema_and_inventory_are_complete`. Return original model/latent/segment objects on disabled/fresh/suppressed paths; on protected paths return an owned segment and timeline dict. Before a failed Save, patch filesystem/take/manifest helpers to raise if called; assert none are reached. Validate the full input batch identity before existing Save takes batch item 0. A direct pass-to-Save of the prepared unsampled latent must fail. Add actual-executor cache cases for protected use/refresh and explicit segment/latent keys: sampling runs, disk load/save do not; ordinary unprotected cache tests retain their behavior.
- [x] **2. Run RED:** the new Save suite, affected `test_agent_resources.py` and focused disk-cache tests. Expect node/receipt/inventory assertion failures; do not loosen existing assertions to hide a bypass failure.
- [x] **3. Implement the node and Save bridge:** disabled/fresh/suppressed cases return before anchor/model validation; active cases call helpers, copy `SegmentPlan` and its timeline dictionary, then attach the opaque receipt. Save locally imports `validate_save` when needed, before any output/take mutation; validate receipt and normal/denoised digest and only then copy the completed descriptor under `segment.timeline['degradation_protection']`. Keep runtime fields/digests out of manifest entries. Register the node and update 19→20 inventory expectation by checking the actual list, not only its count. Keep disk-cache bypass explicit: active receipt paths are uncacheable, never persisted; if real-executor tests reveal an accidental graph-hash hit, add the smallest protection-specific uncacheable check to the existing cache boundary. Disabled/fresh branches must not acquire protection side effects or new caches. Do not add cache restoration support.
- [x] **4. Run GREEN:** source/latent/sampling/Save suites; `python -m unittest discover -s tests/python -t . -p test_disk_cache.py -v`; `python -m unittest discover -s tests -t . -p test_agent_resources.py -v`; `test_regeneration.py` and `test_layer_render.py`. Expect no failures, no mutation before receipt validation, applied metadata only after actual successful sampling, and old graphs functional. One real in-process node schema/registration check must confirm slots and defaults match documentation.
- [x] **5. Commit:** `feat: expose native continuity protection with verified saves`; checkpoint exact evidence, graph wiring and intentional cache/Context Windows limits.

## Task 5: Documentation, full verification and final branch review

**Files:** Modify the documentation/skills/CHANGELOG/`tests/README.md` paths mapped above; update the Phase 23 ledger and Recovery State. Change product paths only for demonstrated review/test failures.

**Interfaces:** Consume the final registered node and wiring; no additional product API. Documentation must use its actual output indices and require returned protected segment → Save. MCP exposes it through existing graph-node schemas and guidance; no new MCP tool or Timeline key.

- [x] **1. Write documentation and coverage expectations:** extend existing resource/skill tests only where needed to assert the new node is discoverable and guidance reaches the host bundle. Document enabling the node; turning off old Context noise; why old graphs are unchanged; suppression on cuts/appearance changes and guide/ending conflicts; Context Windows rejection; sampling-cache bypass; explicit Regenerate/new-generation requirement; native/denoised restoration; and the separate role of Selected memory for the right-window objects. No claimed percentage improvement or visual acceptance. Preserve existing measured long-chain results as historical old-mode evidence.
- [x] **2. Run RED where coverage changed:** affected resource/skill tests should fail until documentation/coverage is complete; for prose-only changes run the strict docs build and repair actual broken links/warnings. No mirrored prose tests or new browser/UI suite is needed for a graph-only node.
- [x] **3. Complete the smallest docs/skill edits:** README feature mention/link; node and long-chain wiring; cache page limit; MCP graph-only inventory (remove stale hard-coded node count if appropriate); joins/video/API skills as needed; concise CHANGELOG entry; CPU test command/scope. Attribute public techniques and keep independent implementation explicit.
- [x] **4. Run final verification:** `node tests/run.mjs`; `uv run --project mcp_adapter python -m unittest discover -s mcp_adapter/tests -t mcp_adapter -v`; `uv run --with-requirements requirements-docs.txt python -m mkdocs build --strict --site-dir .tmp/degradation-docs`; `git diff --check`; `node C:/Users/ricar/.agents/skills/roadmap-discipline/scripts/roadmap.mjs check --root .`. Expect zero failures, no product tests skipped for missing dependencies, strict docs success and consistent roadmap. No live service/GPU operation. Re-run only affected checks after fixes; record final combined evidence before claiming DP1 passing.
- [ ] **5. Perform final branch review, resolve findings, commit and checkpoint:** use the user-selected execution method; Native execution uses one fresh independent final reviewer. Commit explicit task paths as `docs: document native continuity degradation protection`. DP1 becomes passing only after its exact verification succeeds; leave DP2 unstarted pending authorized matched GPU comparison. Report technical completion separately from color/detail quality. Do not push/merge/release/deploy or restart without the task authorization in force then.

## Execution environment and baseline

The live host uses `D:/Projects/ComfyUI_windows_portable/python_embeded/python.exe` and `D:/Projects/ComfyUI_windows_portable/ComfyUI`. In the implementation workspace set `$env:H3_PYTHON` and `$env:COMFY_ROOT` to those paths for CPU-only checks. `python` in the focused commands means `& $env:H3_PYTHON`; use `-m unittest discover -t .` because embedded Python otherwise omits the checkout from sys.path. Tests import `tests.continuity_support.enable_comfy_cpu()` before ComfyUI modules; never load a local GPU model in these checks.

Before Task 1 run `node tests/run.mjs` once, saving results under `.tmp/degradation-baseline.*`. Resolve feature-caused failures; record unrelated failures without widening scope or modifying the running installation. When importing installed core code for tests, use COMFY_ROOT read-only; all product edits live in the isolated development workspace. No worktree setup belongs in a child task prompt.

Track the five task checkpoints under DP1; do not create parallel feature locks. Parent owns the shared roadmap. Before starting/after a meaningful edit/verification/failure, record exact partial state and next action. DP0 is approved/passing; DP2 is deliberately separate because real visual quality needs a matched render with the same memory, camera prompts, checkpoint, sigmas and seeds in both arms. Never improve only one arm's memory inputs and attribute the result to protection.

## Self-review and execution handoff

Spec coverage: native source/track/appearance rules → Task 1; mask/audio/old-noise compatibility → Task 2; clean anchors/late schedule/both output paths/wrapper composition → Task 3; node/receipt/Save/cache/inventory → Task 4; documentation/full tests/review → Task 5; no-live/GPU/duration/take constraints → every task. Every Review Focus item has an owning regression. Shared helper names/returns are consistent across tasks.

Builder choices fixed by this plan: reject Context Windows in v1; suppress in-chain appearance changes to the next fresh boundary; use `ceil(0.75 * step_count)` with interval-based sigma progress; validate the full sampler output before Save's batch slicing; never count preparation as execution; deliberately bypass disk sampling cache while protected. Keep private helper boundaries flexible and avoid a settings framework.

User approved this complete plan and selected **Native** on 2026-11-15 ("Approved, native"). Execute all tasks continuously in an isolated native worktree, then one fresh independent final branch review; do not repeat design/plan/method approval. Design approval is already recorded. No product tests, product code, worktrees, deployment or GPU work were performed while writing this plan. The added read-only clips29–30 diagnosis is recorded at docs/research/2026-11-15-orbit29-30.md; preserve it and include that generated camera reset in later visual acceptance, without claiming the new protection fixes it.
