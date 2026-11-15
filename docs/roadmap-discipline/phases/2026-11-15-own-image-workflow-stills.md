# Stills from the user's own image workflow

### Phase 23: own image workflow stills

- [ ] **OW1** (State: `active` | Verification: `node tests/run.mjs; strict guide build; git diff --check; browser check of a real subgraph connected to still_image`)
  - *Behavior:* The Timeline's `still_image` input takes the IMAGE output of any image workflow wrapped in a native subgraph; the Studio binds it by input names (`prompt`, `seed`, optional `width`, `height`, `negative`, IMAGE inputs as references) and never changes other settings.
  - *User intent (2026-11-15):* Replace the still custom nodes with the user's own workflows and settings. User agreed to the subgraph-contract design, to deprecating the old nodes for one release before deleting them, and to leaving H3 video-model stills alone.
  - *Design:* [Written design](../../superpowers/specs/2026-11-15-own-image-workflow-stills-design.md).
  - *State:* Implemented in worktree `h3c-subgraph-stills` on `feat/subgraph-still-workflows` (from eb75744). Uncommitted; no PR, no install, no ComfyUI restart, no generation.
  - *Evidence (2026-11-15):* `node tests/run.mjs`: 394 JavaScript + 540 Python pass (9 new JavaScript in `tests/js/still_workflow.test.mjs`, 6 new Python in `tests/python/test_still_workflow.py`). Strict guide build passes through `uvx --with mkdocs-material --with mkdocs-glightbox mkdocs build --strict`. `git diff --check` clean. Spike: live ComfyUI 0.45.0 rejects an empty required IMAGE input without queueing.
  - *Outstanding:* Browser check against a live `graphToPrompt` result. `features.md` and `readiness-checklist.md` were not updated: the main checkout holds uncommitted edits to both from other work.

- [ ] **OW2** (State: `pending` | Verification: `templates load and generate; deprecated nodes still load saved workflows`)
  - *Behavior:* Native subgraph templates for P-H3-Image and MiniMax H3 Image; mark `H3C_StillRecipe`, `H3C_PH3ImageStill` and `H3C_MiniMaxH3ImageStill` deprecated for one release.
  - *Open point:* Native replacement for `H3C_MiniMaxPromptCaption` is unconfirmed.

- [ ] **OW3** (State: `pending`) Native `LoadImage` instead of the injected `H3C_StillImageSource`.
- [ ] **OW4** (State: `pending`) Server-side recipe derivation so MCP agents send no recipe.
- [ ] **OW5** (State: `pending`) Delete the deprecated nodes one release after OW2.

## Resume

Open the worktree, run `node tests/run.mjs`, then do the OW1 browser check before a PR.
