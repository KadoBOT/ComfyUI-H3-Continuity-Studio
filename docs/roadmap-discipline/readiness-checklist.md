# Continuity protection readiness

## Can Start

Approved design and five-task plan; Native execution in this isolated worktree at local base 1dd03ed. No repeat permission needed. Existing package dependencies are present in the portable ComfyUI Python; installation is the usual custom_nodes clone and requirements.txt. User follow-up on 2026-11-17 authorizes remaining integration and motion testing, including coordinated matched GPU comparisons. Use an isolated test host/output; preserve the shared host's workflows, saved story, original dirty parent and Phase20 blockers. No merge/release authorized.

## Can Test

Set H3_PYTHON=D:/Projects/ComfyUI_windows_portable/python_embeded/python.exe and COMFY_ROOT=D:/Projects/ComfyUI_windows_portable/ComfyUI. Run node tests/run.mjs and focused unittest discover -t .; CPU bootstrap before ComfyUI imports. Adapter: uv run --project mcp_adapter python -m unittest discover -s mcp_adapter/tests -t mcp_adapter. Docs: uv run --with-requirements requirements-docs.txt python -m mkdocs build --strict --site-dir .tmp/degradation-docs. Fresh 2026-11-17 checks:402JS+587Python,79adapter and strict docs pass. Original DP1 independent review resolved three Important findings; one fresh DP4 increment review reproduced a partial-attention false receipt, now fixed RED→GREEN with per-evaluation coverage. No second independent re-check claimed. GPU fixture/scripts/receipts/logs live under .tmp/dp2; report in canonical reload list records actual visual limits.

## Can See Progress

features.md links this task ledger; five task checkpoints belong to DP1. SDD ledger stores task bases, rulings and test receipts.

## Can Pick Up Next Steps

Recover features.md and its canonical reload paths. Draft PR #94 includes native opt-in attention balance and ckinpdx/MMH3Tools credits. Review fixes626cadd enforce per-evaluation block coverage. DP2 completed three matched native-backend GPU arms on original box30;85 played frames each, source/memory preserved. Camera reset remains, and progressive color/detail retention is unproven by this single-clip test. Owned test host stopped and GPU ticket released; shared host remains alive/idle. Keep draft for review/testing; no merge/release requested. Full report and local comparison artifacts are identified in Recovery State.
