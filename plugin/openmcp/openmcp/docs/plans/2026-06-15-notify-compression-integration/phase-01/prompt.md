# Phase 1 — Worker lifecycle notifications

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
`run()` emits best-effort notifications via `py-notify-system` on worker start, each retryable attempt, success, and final error — gated by `OPENMCP_NOTIFY_*` env, no-op when disabled or when the optional dependency is absent.

## Files to Create/Modify
- Create: `src/openmcp/notify.py`
- Create: `tests/test_notify.py`
- Modify: `src/openmcp/server.py` (call `emit_start` / `emit_finish` / `emit_error` in `run()`)
- Modify: `src/openmcp/retry.py` (call `emit_attempt_failed` per retryable attempt)
- Modify: `pyproject.toml` (add `notify` optional extra)

## Tasks
1. Write `tests/test_notify.py` first (RED): mocked `notify_system.notify`, assert each `emit_*` sends expected `status`/`title`/`context`; disabled → never called; `notify()` raising → swallowed; import-missing → no-op; dispatch via `asyncio.to_thread`.
2. Implement `src/openmcp/notify.py`: lazy import + `_AVAILABLE` guard, `_effective_env` reads, `emit_start/emit_attempt_failed/emit_finish/emit_error`, each wrapped in try/except (log-only, re-raise `CancelledError`), blocking `notify()` via `asyncio.to_thread`.
3. Hook `server.py::run()` (start before dispatch; finish/error after result, on the pre-compression result state) and `retry.py::run_with_retry()` (attempt-failed per retryable attempt before backoff). Add `notify` extra to `pyproject.toml`.
4. Add `run()`-level integration assertions (monkeypatched backend `execute`): success → start+finish; retryable-then-OK → attempt_failed per retry + finish; final failure → error; defaults (disabled) → behaviour byte-identical to today.

## Acceptance Criteria
- Notifications fire on all four events when `OPENMCP_NOTIFY_ENABLED` truthy.
- `context` carries `{backend, session_id, model, attempts}`.
- Disabled / import-missing / `notify()` raising never affects the `run()` payload or raises.
- `notify()` invoked off the event loop (`asyncio.to_thread`).

## Done When
- `uv run pytest tests/test_notify.py -v` green
- `uv run pytest` (full offline suite — no regressions)

## Output
- One commit per task: `phase-1.task-<M>: <summary>`
- Append `## Task <M>` blocks to `C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp/docs/plans/2026-06-15-notify-compression-integration/phase-01/notes.md` after each task
- Append full `# EXTERNAL RESPONSE` to `C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp/docs/plans/2026-06-15-notify-compression-integration/phase-01/journal.md`
- End with completion line: `Phase 1 completed. Journal: docs/plans/2026-06-15-notify-compression-integration/phase-01/journal.md.`
