<!-- ccg-shared-version: 7.7.0 -->

# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Tested one runtime across sequential session lifespans.
- Tested global resources between sessions.
- Tested dashboard access before and after a session.
- Tested cleanup after startup and shutdown failures.

### Spec deviations
- none

### Tradeoffs accepted
- Lifecycle unit tests use small runtime doubles.

### Assumptions
- Session closure must not change daemon runtime ownership.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: The focused run failed both CLI tests.
- Root cause (bugfix only): CLI still entered FastMCP directly.

## Task 2

### Decisions made
- Mounted the FastMCP application inside outer Starlette.
- Owned runtime and session-manager lifespans in that application.
- Reduced FastMCP session lifespan to runtime lookup only.

### Spec deviations
- none

### Tradeoffs accepted
- Runtime startup failure still invokes runtime cleanup.

### Assumptions
- Mounted child application lifespans are not entered automatically.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Focused server and dashboard tests passed, 46 tests.
- Root cause (bugfix only): Per-session runtime cleanup poisoned later calls.

## Task 3

### Decisions made
- Served the outer application directly through Uvicorn.
- Passed resolved host and port values explicitly.

### Spec deviations
- none

### Tradeoffs accepted
- Uvicorn is imported only on the serve path.

### Assumptions
- Existing MCP CLI dependency supplies Uvicorn.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Both configured and overridden CLI tests passed.
- Root cause (bugfix only): Direct `FastMCP.run` owned session lifecycle.

## Task 4

### Decisions made
- Constrained MCP to `>=1.21.2,<2`.
- Updated the lockfile only through `uv lock`.

### Spec deviations
- none

### Tradeoffs accepted
- MCP SDK v2 migration remains deferred.

### Assumptions
- Current lifecycle behavior targets MCP SDK v1.

### Follow-ups for human
- none

### Test evidence
- `uv lock --check` resolved 45 packages.
- `uv run pytest -q` passed 157 tests, with 2 deselected.
- `uv build` produced both distributions.
- Root cause (bugfix only): An unconstrained major upgrade could invalidate lifecycle assumptions.
