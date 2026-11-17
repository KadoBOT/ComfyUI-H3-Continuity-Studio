# Continuity protection execution

**Status:** DP0, DP1, DP3 and DP4 passing technically. DP2 active: the requested clip-2 onset experiment completed, but wall-preservation acceptance failed (balance20 worse; neutral no clear color-fidelity gain). Clip30 remains integration/jump evidence only. Draft PR #94 remains open.
**Current Phase:** Phase 23: Continuity degradation protection

Historical Phase20 watch-through blockers remain in the original parent roadmap at D:/development/rambrogi/work/ComfyUI-H3-Continuity-Studio/docs/roadmap-discipline/. They are preserved and outside this execution.

## Phase Ledgers

- [Continuity degradation protection](phases/2026-11-15-degradation-protection.md)

## Recovery State

```json
{
  "version": 1,
  "revision": 42,
  "phase": "Phase 23: Continuity degradation protection",
  "active_features": [
    "DP2"
  ],
  "focus_feature": "DP2",
  "goal": "Find wall-darkening onset and test native protection only across last-bright to first-dark range",
  "done_when": "Onset range located and documented; matched range renders preserve source/settings/memory; wall and motion compared honestly, draftPR94 updated",
  "last_completed": "Pushed58aa972 to linked draftPR94; README/guide/report and PRbody explicitly record negative clip2 wall result; all requested onset arms/technical checks complete, resources released",
  "in_progress": "No GPU workload or implementation edits. DP2 remains active because wall-preservation acceptance failed; requested narrow-range test is delivered, neutral default retained",
  "next": {
    "action": "Use frozen clip2 fixture for anchor-only/noise-only ablations before proposing another recipe; do not claim a fix or recommend balance20 from these results",
    "reason": "Current model/recipe does not improve wall-color fidelity; the next useful diagnosis must isolate the mechanism within the same user-selected range"
  },
  "files": [
    {
      "path": "docs/research/2026-11-17-wall-darkening-onset.md",
      "state": "User-selected clip2-only onset experiment complete; three successful saves, negative wall-color result, similar motion, source/overlap/memory preserved; GPU host stopped/ticket released"
    },
    {
      "path": "docs/research/2026-11-17-protection-integration.md",
      "state": "Completed three-arm GPU fixture, per-output receipts/carry/memory checks, frame/flow findings and limits; owned GPU host stopped and ticket released"
    },
    {
      "path": "tests/python/test_protection_attention.py",
      "state": "10 CPU checks including partial-block/later-evaluation bypass and invalid block regressions, passing"
    }
  ],
  "repository": {
    "branch": "feat/continuity-protection",
    "head": "58aa972ffcc5",
    "dirty": [],
    "dirty_hash": "75a11da44c802486bc6f65640aa48a730f0f684c5c07a42ba3cd1735eb3fb070"
  },
  "verification": {
    "required": "matched baseline/protected render and reviewed source frames across a continuing chain",
    "last_run": "3GPU onset saves; source/carry/memory validation; registered common-frame wall/flow inspection; strict docs/diff/roadmap; draftPR94 metadata",
    "status": "failed",
    "detail": "Technical checks pass; wall acceptance fails: baselineDeltaE2.37 neutral2.39 balance20 3.20 on30 common frames. Six total GPU tests across distinct onset/jump cases; both GPU tickets released"
  },
  "blockers": [],
  "reload": [
    "docs/roadmap-discipline/features.md",
    "docs/roadmap-discipline/phases/2026-11-15-degradation-protection.md",
    "docs/superpowers/specs/2026-11-15-degradation-protection-design.md",
    "docs/superpowers/plans/2026-11-15-degradation-protection.md",
    "docs/research/2026-11-15-orbit29-30.md",
    "docs/research/2026-11-15-continuity-protection-review.md",
    "docs/research/2026-11-16-geiru-upstream-review.md",
    "docs/research/2026-11-17-protection-integration.md",
    "docs/research/2026-11-17-wall-darkening-onset.md"
  ]
}
```
