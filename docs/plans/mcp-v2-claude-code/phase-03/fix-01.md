# Phase 3 recovery fix: admitted queued cancellation

## Status

Authorized by the user's 2026-10-07 directive to complete mcp-v2-claude-code. Accept the saved ERP as documented transport-failure recovery and dispatch this scoped correction. The failed job remains failed. No source reset, daemon restart, or change to live configuration is authorized.

## Request

FIX B1 only. Preserve the saved Phase 3 implementation. Follow phase-03/prompt.md, the existing worker contract, and ERP. This is a bounded correction within the approved seven-file scope, not a redo of the phase.

## Confirmed failure

With max_jobs=1, pause the sole worker in a completed job's terminal notifier. Its admission reservation has already been released. Submit a new parent and a dependent child. The new parent is reserved but its persisted state is queued; its callback has not started.

Runtime.cancel currently reports running, leaves both records queued, returns no cancelled dependent IDs, and retains the reservation until the older notifier releases. scheduler.py:139 conflates reservation with execution. runtime.py:371 takes the running cancellation path for that reserved queued record.

Existing tests pass because their queued-parent cancellation fixture uses a pending parent behind an active project reservation. That does not cover this admitted-but-unstarted case.

## Required correction

- Distinguish admitted but unstarted dispatches from executing work using the minimum state needed.
- Cancel an actual unstarted queued parent immediately. Persist its cancelled outcome and the transitive causal cascade before notification awaits. Return only IDs actually cancelled in this call.
- Release the parent's global/project/session reservation and all cancelled completion waiters.
- A removed ready-queue entry must not execute, cancel, signal, or release a later retry of the same job ID. Retain generation-specific completion and reservation handling.
- Preserve active execution cancellation, durable shutdown queues, writer fairness, immutable dependencies, and the approved ActionResult field.

## Scope

Use only the existing Phase 3 production/test paths. Limit changes to scheduler/runtime and necessary regression tests unless another declared path genuinely needs correction. No models change beyond the already approved field. Update phase-03 notes/journal with exact RED/GREEN evidence and full ERP. All other paths are read-only.

## Regression evidence

Use existing fixture helpers, isolated home/project paths, notifications disabled, and deterministic events. Do not use live data or dependency polling.

1. While the prior terminal notifier remains paused, cancel the admitted but unstarted queued parent. Assert parent and descendants are cancelled, returned IDs match actual current-call cancellations, waiters release, and reservation capacity is released.
2. Retry the cancelled parent before releasing the prior notifier. Assert stale ready-queue entries cannot affect the retry's dispatch, cancellation event, reservation, or completion event. The retry executes once through its own generation. Its cancelled descendants do not revive.
3. Keep actual running cancellation behavior unchanged and preserve existing admission, fairness, capacity, cleanup, and retry tests.

## Checks

- Record exact regression RED failures before production edits.
- uv run --extra dev pytest tests/test_scheduler.py tests/test_runtime.py tests/test_execution.py -q
- uv run --extra dev pytest -q
- git diff --check

No Git writes, OpenMCP calls, configuration changes, service restart, or reads of live/global configuration, database, authentication, or session stores.
