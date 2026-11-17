# Geiru update review — 2026-11-16

User requested checking the recent upstream commits for applicable improvements and adding explicit deserved credits to README/docs. This review updates draft PR #94; it makes no sampling-behavior change, installs nothing and runs no GPU work.

## Revisions inspected

- Previous snapshot: [e03cda9](https://github.com/roycho87/geiru_context_suite/commit/e03cda9f643afe55430ee4ccdff228888d1cdae1), 2026-11-12.
- [b5865c1](https://github.com/roycho87/geiru_context_suite/commit/b5865c109c6f095c19843ef359c7ff969c1cc655), 2026-11-15 23:11 UTC: Hybrid Windows memory/cropping, Keystone Attention and Director settings changes; version 1.1.0.
- [c1f57df](https://github.com/roycho87/geiru_context_suite/commit/c1f57df661bbeec464220db2a54179a30cceef17), 23:13 UTC: attention balance defaults to 20; version 1.1.1.
- [918327f](https://github.com/roycho87/geiru_context_suite/commit/918327fcd965371488e3df4eafebd7c1ac8eee12), 23:17 UTC: attention/context-noise example; version 1.1.2.
- [099da1b](https://github.com/roycho87/geiru_context_suite/commit/099da1be92f2da22a775076a0d533d29b4d97268), 23:20 UTC: README update and consolidation.

The complete [comparison](https://github.com/roycho87/geiru_context_suite/compare/e03cda9f643afe55430ee4ccdff228888d1cdae1...099da1be92f2da22a775076a0d533d29b4d97268) leaves `nodes.py`, `clown_context_noise.py` and `clown_keyframe.py` unchanged. There is no new correction to the original context-noise/keystone/late-lock mechanisms to port into our existing protection path.

## Applicability

| Upstream change | Native relevance | Decision |
| --- | --- | --- |
| Keystone Attention | Directly relevant candidate for residual brightness drift beyond our current clean anchors | Document as a separate opt-in experiment; not silently enabled in the current unvalidated draft |
| Hybrid Windows system-RAM state and cropped per-window sampling | Applies to an entire-video hybrid sampler holding several full-length arrays | No equivalent full-length state exists in our one-clip continuation path; no memory-result claim or generic rewrite |
| Window Director mutable protection controls and named-widget migration | Geiru's own interactive per-window controller and saved graph widgets | No matching controller in this feature; not imported |
| Balance default, example graphs and README | Documents upstream's selected attention recipe and wiring | Record exact source/version and credit; do not copy workflows or adopt new defaults without testing |

### Attention mechanism and compatibility

Read both new files completely: [keystone_attention.py](https://github.com/roycho87/geiru_context_suite/blob/099da1be92f2da22a775076a0d533d29b4d97268/keystone_attention.py) and [hybrid_keystone_attention.py](https://github.com/roycho87/geiru_context_suite/blob/099da1be92f2da22a775076a0d533d29b4d97268/hybrid_keystone_attention.py), plus the changed window sampler/Director and upstream README.

The new mechanism identifies clean anchor and held-context rows within native H3's packed video segment. On selected attention blocks it changes the division of their combined attention mass while retaining the other modalities' shares. It computes full attention plus anchor-only and context-only contributions and corrects the output. Upstream selects lighting blocks 31–33, 36–44, 47 with balance 20, and uses head chunks to limit attention memory. Upstream reports improved brightness retention with some reduced motion; those are its observations, not our measurements.

The chain node explicitly looks for Geiru's `clown_keyframe_slots`/`clown_keyframe_back` latent markers and `geiru_protection` switch. Our receipt-bearing latent has none of those markers, and our capstone exists only during late model calls. A drop-in Geiru Attention node therefore cannot be described as compatible with our native protection. Native adaptation would need explicit row ownership, correct late-capstone presence, composition with native/low-VRAM/Sage attention and disabled-path neutrality, with CPU mass/identity checks followed by matched brightness/motion renders. Merely adding legacy marker names would not establish those contracts.

This is a new attention-level feature, not a small fix to unchanged upstream noise/anchor code. Keep the current protection baseline stable for its first GPU comparison. The useful follow-up is a separately scoped optional attention experiment after that baseline; no unused helper, new tuning framework or untested replacement attention is added by this review.

### Window memory mechanism

The updated [clown_hybrid_windows.py](https://github.com/roycho87/geiru_context_suite/blob/099da1be92f2da22a775076a0d533d29b4d97268/clown_hybrid_windows.py) retains full-length clean/state/pinned arrays in system RAM and crops video/audio/noise/masks for each window's independent sampling pass. It preserves window-local shapes and source noise, with a full-length fallback for the per-step-ratio noise mode. Director mutable-field signatures and widget migration support that workflow. Our native Timeline instead loads original anchor slices and samples one continuing clip; `h3_continuity/windows.py` delegates ordinary context windows to core and the protection node deliberately rejects them. The Hybrid Windows rewrite has no direct target here.

## Credits applied now

- README prominently credits **roycho87 / Geiru Context Suite** for keystone/capstone anchors and late locking, and **ethanfel / Lumifel / H3 Context Loop** for sampler-synchronized context noise.
- The long-chain guide and `THIRD_PARTY_NOTICES.md` contain the same explicit attribution and independent-implementation statement.
- This review preserves upstream's credit to **ckinpdx's Carry Attention** for the new attention idea, and **kijai/JalenBrunson** for the window foundations, without implying those new components are implemented in this repository.
- Geiru's inspected license is GPL-3.0. No upstream source, workflow or other licensed implementation was copied into this MIT project. This is attribution of ideas plus a source-backed applicability review.

## Verification boundaries

No product Python/JS or sampling settings changed. Check the README/research/notice links and build MkDocs strictly; there is no reason to rerun unchanged model mechanics or start GPU inference for these documentation edits. Original DP1 CPU evidence remains separate from DP2's still-unverified visual improvement and the already diagnosed clip29→30 camera reset. Keep draft PR94 unmerged for later testing.

## Follow-up — 2026-11-17

roycho87 asked on [PR #94](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/pull/94) that **ckinpdx** be credited if Keystone Attention is used or tested: Carry Attention in [ComfyUI-MMH3Tools](https://github.com/ckinpdx/ComfyUI-MMH3Tools), the idea of biasing H3's attention by part of its sequence, is what Keystone Attention is based on. README, guide and notices now name ckinpdx and link MMH3Tools.

Carry Attention (`mmh3tools/nodes_carry_attention.py`, MIT, read at 5bf2f5b) adds a bias to the attention scores of chosen row spans through core's `optimized_attention_override`. Geiru's Keystone Attention instead leaves every share exact except the one shared by anchors and held context.

The "separate optional experiment" above is now implemented natively as `attention_balance` / `attention_blocks` on H3 Continuity Protection, default 1 (unchanged). It uses the same override hook Carry Attention uses rather than replacing the attention forward, takes row ownership from our own prepared mask and core's `minimax_h3_layout`, includes the late capstone when present, and fails sampling if another patch keeps it from running. Geiru's lighting blocks are the default. CPU checks compare it with explicit softmax attention and with a small real `MiniMaxH3Model`.

Upstream commits after 099da1b (0c81e3e, a2c094a, 6171b3f; versions 1.1.3-1.1.5) change README credits and Hybrid Windows preview and noise cropping only. Nothing further applies here.

The subsequent independent review reproduced a false successful receipt when another patch balanced only some requested blocks. The guard now checks every selected block on every model evaluation, including later evaluations, and rejects invalid block indices before sampling. Regressions failed before the fix and pass after it. Installed Veda reinstalls its sparse override above the native balance hook; the GPU comparison therefore uses the same native dense backend in all arms. A bounded GPU probe confirmed PyTorch memory-efficient SDPA accepts the extra value channels; Flash/cuDNN-only probes did not. See the [integration and motion report](2026-11-17-protection-integration.md) for actual render evidence and limits.
