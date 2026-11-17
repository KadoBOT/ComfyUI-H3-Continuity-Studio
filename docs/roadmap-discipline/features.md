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
  "revision": 41,
  "phase": "Phase 23: Continuity degradation protection",
  "active_features": [
    "DP2"
  ],
  "focus_feature": "DP2",
  "goal": "Find wall-darkening onset and test native protection only across last-bright to first-dark range",
  "done_when": "Onset range located and documented; matched range renders preserve source/settings/memory; wall and motion compared honestly, draftPR94 updated",
  "last_completed": "Requested clip2 onset range rendered in3matched arms; output/carry/memory checks pass; registered wall result negative; GPUticket9cdd0f62 released and ownedPID40500 stopped",
  "in_progress": "No GPU work. Onset report/README/guide now explicitly record failed wall acceptance; draftPR94 publication pending. DP2 remains active; neutral attention default retained",
  "next": {
    "action": "Verify docs and publish exact negative onset evidence to draftPR94; retain frozen clip2 fixture as gate for any later recipe changes",
    "reason": "User requested this narrow range; tests completed but wall protection is not a demonstrated fix and must not be marked passing"
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
    "head": "572c45f2563c",
    "dirty": [
      "CHANGELOG.md",
      "README.md",
      "docs/research/2026-11-17-protection-integration.md",
      "docs/research/2026-11-17-wall-darkening-onset.md",
      "docs/roadmap-discipline/readiness-checklist.md",
      "guide/continuity/long-chains.md"
    ],
    "dirty_hash": "d2b2e736a10e5926054fbc4c650682a11a2c111131103346bfa39339e4f71d8b"
  },
  "verification": {
    "required": "matched baseline/protected render and reviewed source frames across a continuing chain",
    "last_run": "3GPU onset saves; CPU source/carry/memory and common-frame wall/flow checks; prior402JS+587Python/79adapter technical checks",
    "status": "failed",
    "detail": "Technical execution passes; visual acceptance fails. Common-frame DeltaE baseline2.37 neutral2.39 balance20 3.20. No accepted color-preservation recipe for this story"
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
