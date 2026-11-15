# Continuity degradation protection

Status: approved by the user on 2026-11-15 ("Approved"). DP0 is passing; DP1 implementation planning is active. No product implementation or GPU comparison has run.

## Intent and observed evidence

Reduce accumulated color/detail degradation in long H3 continuation chains, using the useful mechanisms from Geiru Context Suite within this repository's native Timeline and saved-latent workflow. Keep the smallest complete integration; do not import Geiru's chain controller, counter, latent storage, hybrid windows or experimental LoRAs.

Read-only inspection on 2026-11-15 identified the running observatory story in `generation_2701108ee2f34004be88fe6fbf18f6e9`, graph `c1158f18-3e33-40e9-92ca-c44d66713d2b`, Timeline node 1672: 34 clips (`orbit_01`–`orbit_34`), no cuts, 39-frame carry, audio carry off. The graph selects `10Eros_Max_h3_8stepTURBO_beta7_int8HQ.safetensors`, 8 steps and beta57 scheduling. Its Timeline omits `context_noise`, so the existing paired pixel-noise feature is off. No live values were changed.

The frozen analysis snapshot contains 24 matching orbit renders; unrelated imported legacy entries also exist in the manifest and were excluded by box identity. All 24 source clips are 1152×640, 24 fps, sRGB HEVC. Their sampled frames visibly become darker/more contrasty. Mean CIELAB lightness across three source frames per clip is 39.39 in clip 1 and 31.29 in clip 24. This is an observation, not an isolated color-error estimate: framing, visible windows and objects change. Saturation is higher in the latest sample, so do not describe this as proven desaturation. Source-clip evidence rules out an issue confined to the assembled preview, but does not by itself isolate model sampling, decode or grading as the sole cause.

Ignored research artifacts: `.tmp/degradation/{active-api.json,manifest-snapshot.json,measurements.json,source-frames.png,inspect_render.py}`. Research is read-only against the live host. The active render continues unchanged.

User follow-up: objects near the right window disappear. The first clip alone has memory off; all remaining 33 clips use `scene`. Saved metadata confirms actual references, not just authored settings: orbit_12 and orbit_24 both record orbit_01/frame 0 plus the preceding clip/frame 68. Thus memory is already being delivered. Do not attribute the disappearing props to disabled memory. Inspect the exact selected five-frame windows and whether they show those objects; explicit selected moments with labels may be a useful existing control, but no memory change is authorized or assumed here. Sampling color/detail protection is not an object-permanence guarantee. Keep object persistence as a separate visual acceptance criterion, with a separate defect investigation only if delivered memory is demonstrably wrong.

User clarification: the automatically selected recent views passed through clips where the right-window items were out of view; an explicitly selected memory from a clip that clearly shows them is the existing remedy. Treat this as reference coverage/authoring, not evidence that Same scene is off or a request for a new memory subsystem. Leave the live story unchanged. For any color-protection comparison keep memory settings identical between both arms, so a better prop reference does not confound the protection result.

## Approaches

1. **Native sampling protection — recommended builder choice.** Add one optional H3 Continuity graph node using native Timeline provenance and saved latents. Apply sampler-level context noise, a clean front anchor and a late back anchor. No external custom-node dependency, model download or global patch.
2. **Depend directly on Geiru.** Reuse its nodes, requiring another installation and an adapter from our native segment storage. More installation/wiring and compatibility surface; its source snapshot carries GPL-3.0 while this repository carries MIT. Do not vendor its implementation into the current MIT codebase.
3. **Correct color after decode.** Smaller visually, but does not address accumulated latent texture/detail changes, can fight deliberate lighting changes and feeds uncorrected latents forward. Does not fulfill the requested generation-level continuity protection.

The user approved this native approach and the complete written design on 2026-11-15. Public mechanisms will be implemented independently against ComfyUI APIs, with attribution and links to Geiru and its cited context-noise author; no upstream source is copied. If implementation requires reused licensed code, revisit that decision explicitly rather than silently vendoring it.

## Product shape and wiring

Add **H3 Continuity Protection** with required `model`, `latent` and native `segment` inputs; `enabled` defaults on. Return patched `model`, prepared `latent`, a cloned `segment` and a concise `info` string. Wire that returned segment to Save Segment. The explicit node is opt-in: existing graphs and Timeline JSON retain their exact behavior.

```text
chosen sampling MODEL ───────────┐
H3 Timeline latent ──────────────┼─ H3 Continuity Protection ─ model → guider
H3 Timeline segment ─────────────┘                          └ latent → sampler
                                  protected segment ────────→ Save Segment
```

One node covers the complete protection; do not ask people to reproduce Geiru's multi-node setup. Keep it separate from Timeline's conditioning node: a sampling model can already depend on Timeline's segment through H3 Continuation Model, so a new MODEL input on Timeline could create a graph cycle. This first integration is a graph setting, like H3 Sigmas Tail; no duplicate Studio checkbox or Timeline JSON option is introduced.

The Timeline attaches lightweight runtime anchor provenance to SegmentPlan from its already parsed track and manifest. The node reads only the required original video-latent slices with `store.load_video_window`, clones them and never rewrites the source. No full VAE decode/re-encode is needed for this protection.

## Sampling behavior

- Disabled, fresh/cut clips, bridges and non-continuing layers pass model and latent through without anchor reads. Scope is a native continuing chain. Resolve the anchor using `rules.continuation_chain` and `previous_index`, respecting tracks, gaps and cuts; never assume manifest segment 1 or array adjacency is the source. Reset at every fresh chain. `plate_changes` alone does not reset `continuation_chain`; suppress protection from any authored appearance change through the next fresh/cut boundary, because even the changed box's slot 0 can still show the old look. Explain suppression in `info`; never reuse that old appearance or invent a post-change source. Malformed `new_scene` on a continuation is also a suppression boundary, not an instruction to reuse the previous scene.
- Use the source chain's first original video latent as the front anchor. During sampling it replaces slot 0 only; preserve the real carried slot for restoration. Apply a linear fractional denoise-mask ramp to the remaining carried video slots, from full context noise toward zero at the join. Leave the final carried slot clean, every free slot fully free, and audio masks untouched.
- For the last quarter of the actual sampling schedule, append one clean video latent from the source's last single-frame block as a capstone inside model calls. Remove it immediately from the prediction. For eight steps this means six early steps without it and the final two with it; derive progress from the actual sigma schedule, not model-call counts or an assumed eight steps. Do not append it when the Timeline protects a following neighbor's ending or an authored last/interior guide would conflict. Report that suppression.
- Restore every original carried video latent in both normal sampler output and `SamplerCustomAdvanced.denoised_output` before decode, caching and save. The installed core builds the latter from callback-captured x0: restoring OUTER_SAMPLE's return alone does not restore that path. Compose callback handling as well, preserving preview callbacks and correct internal/output latent coordinate conversion. Preserve original audio and protected ending regions. Input tensors, masks, base model and source files remain unmodified. Patch a clone and compose with existing model wrappers; no shared mutable state across renders or re-rolls.
- Missing/stale anchor provenance, incompatible latent resolution, unavailable partial-mask support or ambiguous schedule: fail with a specific setup error before sampling. Do not silently resize anchors, ignore restoration failures, substitute another box, retime clips or claim protection when the requested path did not execute. A feature can improve drift without guaranteeing identical color or motion.
- The new mode supersedes the old paired pixel-noise treatment for that run. Reject combining it with an already pixel-noised carry (or an unrelated incompatible mask), explaining which existing control to turn off. Preserve old `context_noise` semantics for existing graphs.

## Provenance, cache and persistence

The returned segment is a shallow dataclass clone with an owned copy of `segment.timeline`, plus a runtime-only receipt shared with that patched model. Do not mutate Timeline's original segment. Reset the receipt on each sampling invocation; preparation alone never marks it applied. After successful restoration, complete the receipt with the actual schedule activation and content digests of both admissible sampler outputs (normal and denoised, in the coordinates Save receives). Save Segment validates its input latent against this receipt before any file/take mutation. A missing/incomplete receipt, another pass's output or an unpatched-model bypass is an explicit error. A failure cannot reuse the previous successful receipt. Require CPU coverage for both output branches, rerolls, failures, reused model objects and stale/mismatched receipts.

Only after successful validation, Save records a versioned applied-protection descriptor in its existing `segment.timeline` metadata: method, anchor box/take identity and latent content identity, context count, actual schedule activation and any suppressed capstone reason. Permit this minimal Save integration; do not persist runtime receipts, output digests, tensors or model state. Disabled/fresh/suppressed pass-throughs require no receipt and are not recorded as applied protection.

For this first integration, protected sampling deliberately uses H3 Disk Cache's existing safe bypass: the upstream runtime segment/receipt cannot be represented as a cache key. Make that outcome explicit in node guidance and verify the real graph traversal. Do not add a cache receipt format or cross-run cache restoration in this change. Even if an old/plain cache result is miswired around the node, Save's receipt/output validation must reject it before writes. Disabled/fresh paths retain existing cache behavior. Source-take identity is checked again before sampling; never reuse a prepared anchor after the underlying take changed.

Existing Timeline status tracks authored inputs rather than every model/sampler graph setting. Adding/toggling this graph node therefore follows the current model/sampler workflow: explicitly Regenerate affected clips or start an independent generation; merely queueing a completed story will not replace its takes. Document that limit in the node and guide. Keep old clips/takes until their replacements save successfully. Source take changes must participate in runtime/cache identity even if the authoring UI is unchanged.

## Integration scope

- `h3_continuity/protection.py` (new): preparation, wrapper composition/restoration, capstone schedule and new node.
- `h3_continuity/nodes.py`: minimal optional SegmentPlan provenance fields; preserve every existing caller.
- `h3_continuity/timeline_node.py`: populate provenance at the native continuation planning boundary, after ending protection is known; no creative prompt changes.
- `h3_continuity/extension.py`: register the node. Agent coverage, node/schema tests and guidance must list it.
- Save Segment receives the minimal receipt-validation/metadata bridge described above. Existing cache/media code changes only if a demonstrated invariant requires it. Preserve frames, exact durations, seeds, guide placement, audio clocks, joins, takes and disk-cache safety.
- README/guide, `docs/MCP.md`, relevant skills and CHANGELOG: show native wiring, opt-in behavior, compatibility/limits and upstream attribution. No new package/model/LoRA dependency.

## Verification and rollout

Before implementation: write an approved-design plan, isolate product changes from the dirty main checkout, run the existing baseline and record the actual Python/COMFY_ROOT. CPU regressions must cover fresh/disabled pass-through; mask taper/audio preservation; byte-exact restored carry in both sampler outputs and unchanged output shape; anchor selection across tracks/cuts/gaps and take changes; appearance-change suppression; existing wrappers and CFG batches; variable schedules/multiple calls per sigma; protected endings/guides; incompatible masks/shapes; no tensor mutation/state leak; executed receipt validation; and safe cache bypass. Test actual ComfyUI packed AV mask and wrapper interfaces, not only stubs. When Context Windows are present, either prove correct window-local anchor placement or reject the combination clearly before sampling; no speculative support claim.

Run `node tests/run.mjs`, adapter/node-coverage checks affected by registration, strict docs and `git diff --check`. No live deployment/restart during the current queue.

Real acceptance is separate DP2 work: after explicit GPU authorization and an idle/safe activation point, render matched baseline/protected continuations using this story's actual checkpoint/sampler/settings and fixed prompts/seeds in independent output sequences. Compare source frames at matched camera moments, joins, face/clothing/props, motion and CIELAB/texture trends; use repeated scene content/regions where possible. Do not treat CPU tests or lower frame means as visual acceptance. No protection result is claimed yet; Geiru itself documents residual darkening and turbo-dependent behavior.

## Builder discretion and exclusions

Choose internal helper boundaries and the smallest safe wrapper APIs from the installed ComfyUI. Fixed initial ramp and late-lock defaults avoid an unrequested preset/settings framework. If real comparison needs a strength control, add only the demonstrated control in a follow-up decision. No hybrid-window director, shot-counter replacement, anti-burn LoRA, exporter rewrite, automatic color grading or silent workflow migration.

## Sources

- [Geiru Context Suite](https://github.com/roycho87/geiru_context_suite), inspected at `e03cda9f643afe55430ee4ccdff228888d1cdae1` on 2026-11-15: README, LICENSE, nodes.py, clown_context_noise.py and clown_keyframe.py.
- [Context-noise source](https://github.com/roycho87/geiru_context_suite/blob/e03cda9f643afe55430ee4ccdff228888d1cdae1/clown_context_noise.py), credits ethanfel/Lumifel and ComfyUI-MiniMaxH3-Context-Loop.
- [Keystone and late-lock source](https://github.com/roycho87/geiru_context_suite/blob/e03cda9f643afe55430ee4ccdff228888d1cdae1/clown_keyframe.py).
- [Author's fade/strength experiments](https://github.com/roycho87/NerdNotes/blob/main/20261101/frame0_conclusions.md).
- Native anchors: timeline.py (`continuation_chain`, `scene_sources`, `layout_key`), timeline_node.py continuation path, nodes.py (`prepare_segment`, SegmentPlan), latents.py (`build_continuation`, old context noise), windows.py, store.py (`load_video_window`), disk_cache.py and check_frames.py.
- Installed core inspected read-only: `comfy/model_base.py` MiniMaxH3 partial masks and `scale_latent_inpaint`, `comfy/ldm/minimax/model.py` per-token timesteps and sigma schedule.

## Design verification

Fresh read-only builder check found three material gaps, now resolved: restore callback-derived denoised output as well as normal output; suppress across in-chain appearance changes until a fresh boundary; return an owned segment and validate an executed receipt before Save metadata/file writes. To keep scope small and safe, protected runs deliberately bypass disk sampling cache in this first integration. No second review, product tests or protected GPU render is claimed. Roadmap/diff validation is recorded in the phase ledger; user approved the full design on 2026-11-15.
