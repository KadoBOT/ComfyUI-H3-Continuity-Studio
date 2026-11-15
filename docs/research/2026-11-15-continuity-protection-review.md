# Native continuity protection: final branch review

One fresh independent reviewer inspected the complete implementation range `1dd03ed..c623519`, connected native callers, the approved spec/plan and the installed ComfyUI core. The reviewer used CPU reproductions without model weights, made no file changes and dispatched no agents. Native execution used no per-task agents.

Three findings were graded Important by the reviewer and accepted by the parent on user impact:

1. Bridges/replacements carry video without an ordinary chain anchor. The enabled node attempted to load an anchor instead of passing them through.
2. Same-geometry input from another SegmentPlan could be sampled and saved under the wrong carried context, because preparation did not bind native carried/ending data to the segment.
3. Sampling with altered prepared data or an all-zero video mask could still complete a receipt, because the expected prepared inputs were not checked at sampler entry.

The parent reproduced each with failing checks, then completed one cumulative fix pass:

- A shared pass-through classifier handles bridge/replacement/layer/fresh/suppressed paths consistently in the node and cache. Real CPU executor tests verify cache hits for those pass-through paths.
- Preparation validates full native AV geometry and carried/ending video/audio against SegmentPlan before making any changes.
- Sampler entry verifies prepared sample and expanded/normalized mask identities using native packing and dtype promotion. Alterations fail before model evaluation and cannot leave a successful receipt. Positive mixed-AV-dtype coverage protects legitimate native packing.

Post-fix verification: `node tests/run.mjs` **402 JS + 577 Python**, **79 adapter** tests, strict documentation build, diff and roadmap checks pass. The full suite includes the review regressions and actual core mask/packing/wrapper/callback dispatch with weight-free evaluation. Baseline was402JS+541Python;36 new CPU checks were added overall. Full logs/RED repros are retained in the ignored plan workspace while this local worktree is kept for review.

No second independent review of the corrected head is claimed; the parent verified the fixes with regressions and the complete suites. No Critical or Minor findings were reported.

## Declined-to-judge rulings and limits

- Actual color/detail improvement is unverified DP2 work. CPU checks prove mechanics and save/cache safety, not visual quality; a matched GPU comparison requires separate authorization.
- The clip29→30 camera reset is present in the original source video after its first guided frame. This protection node is not a demonstrated fix for it; keep that join in later visual acceptance.
- Uninspected core versions are not certified. The node requires native H3 AV partial masks; the inspected installed core is the CPU target. Context Windows are explicitly rejected rather than claimed compatible.

No live workflow, service, generation, deployment, release, push or merge occurred. The original parent checkout's dirty files and Phase20 watch-through blockers are preserved.
