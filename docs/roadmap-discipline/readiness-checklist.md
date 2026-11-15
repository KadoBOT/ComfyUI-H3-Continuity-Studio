# Continuity protection readiness

## Can Start

Approved design and five-task plan; Native execution in this isolated worktree at local base 1dd03ed. No repeat permission needed. Existing package dependencies are present in the portable ComfyUI Python; installation is the usual custom_nodes clone and requirements.txt. No live deployment, restart, workflow mutation, extra generation or GPU inference. Original dirty parent checkout and Phase20 watch-through blockers remain untouched.

## Can Test

Set H3_PYTHON=D:/Projects/ComfyUI_windows_portable/python_embeded/python.exe and COMFY_ROOT=D:/Projects/ComfyUI_windows_portable/ComfyUI. Run node tests/run.mjs and focused unittest discover -t .; CPU bootstrap before ComfyUI imports. Adapter: uv run --project mcp_adapter python -m unittest discover -s mcp_adapter/tests -t mcp_adapter. Docs: uv run --with-requirements requirements-docs.txt python -m mkdocs build --strict --site-dir .tmp/degradation-docs. Baseline402JS+541Python; post-review402JS+577Python,79 adapter, strict docs and diff/roadmap pass. One independent review completed; three Important findings fixed RED→GREEN and verified by the parent. No second independent re-check claimed.

## Can See Progress

features.md links this task ledger; five task checkpoints belong to DP1. SDD ledger stores task bases, rulings and test receipts.

## Can Pick Up Next Steps

Recover features.md and its canonical reload paths. All five Native tasks and the independent review/fix/verification gate are complete (DP1 passing). User requested pushing this branch and creating a draft PR for later testing. DP2 requires separate GPU authorization; CPU checks do not demonstrate visual improvement or a fix for the clip30 camera reset. No merge/release/deployment or live test is requested.
