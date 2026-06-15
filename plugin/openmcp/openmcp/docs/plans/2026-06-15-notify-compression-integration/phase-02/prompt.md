# Phase 2 — ERP-aware response compression

## Contract
Read these files first:
- C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp/.agents/shared/worker-contract.md
- C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp/.agents/shared/erp.md
- C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp/.agents/BACKEND.md

## Plan
- C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp/docs/plans/2026-06-15-notify-compression-integration/PLAN.md
- C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp/docs/plans/2026-06-15-notify-compression-integration-design.md

## Phase Rules
This phase is **test-first** per `test-driven-development`: write a failing test before any production code. Record RED→GREEN evidence in `notes.md`.

## Goal
`run()` compresses the worker's `agent_messages` via `the-token-company-python` before returning, ERP-aware (only `## SUMMARY` and `## NOTES` prose compressed; all other ERP structure verbatim), gated by `OPENMCP_COMPRESS_RESPONSE` + `OPENMCP_TTC_API_KEY`, strictly best-effort.

## Files to Create/Modify
- Create: `src/openmcp/compression.py`
- Create: `tests/test_compression.py`
- Modify: `src/openmcp/server.py` (await `compress_response(agent_messages, env)` before return dict)
- Modify: `pyproject.toml` (add `compress` optional extra)

## Tasks
1. Write `tests/test_compression.py` first (RED): mocked `AsyncTheTokenCompany`; ERP block → SUMMARY/NOTES prose replaced, META/table/COMMITS/SPEC/NEXT/completion line byte-identical; no ERP → whole string compressed once; disabled / no key / import-missing → input unchanged & `compress()` never called; TTC raises → verbatim; timeout exceeded → verbatim; malformed/truncated ERP → no corruption; empty text → skipped.
2. Implement `src/openmcp/compression.py`: `async compress_response(text, env)`, gate order (enabled → key → import → non-empty), ERP parser splicing only SUMMARY/NOTES prose, `asyncio.wait_for(..., OPENMCP_TTC_TIMEOUT_S)`, all exceptions → original text, `CancelledError` re-raised, env-driven `model`/`aggressiveness`.
3. Hook `server.py::run()`: `agent_messages = await compress_response(agent_messages, effective_env)` immediately before the return dict (after notify finish/error). Add `compress` extra to `pyproject.toml`.
4. Add `run()`-level integration assertion: successful run passes `agent_messages` through `compress_response`; defaults (disabled) → behaviour byte-identical to today.

## Acceptance Criteria
- With an ERP block, only SUMMARY/NOTES prose is compressed; every coordinator-scanned element (headers, FILES MODIFIED table, COMMITS hashes, completion line) is unchanged.
- Disabled / no key / import-missing / TTC error / timeout → original text returned, never a failure.
- Prompt is never compressed; only the returned `agent_messages` is touched.

## Done When
- `uv run pytest tests/test_compression.py -v` green
- `uv run pytest` (full offline suite — no regressions)

## Output
- One commit per task: `phase-2.task-<M>: <summary>`
- Append `## Task <M>` blocks to `C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp/docs/plans/2026-06-15-notify-compression-integration/phase-02/notes.md` after each task
- Append full `# EXTERNAL RESPONSE` to `C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp/docs/plans/2026-06-15-notify-compression-integration/phase-02/journal.md`
- End with completion line: `Phase 2 completed. Journal: docs/plans/2026-06-15-notify-compression-integration/phase-02/journal.md.`
