<!-- ccg-shared-version: 7.7.0 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Used fake runtime waits to avoid real sleeps.
- Tested schema default, normalization, validation, and terminal jobs.

### Spec deviations
- none

### Tradeoffs accepted
- Test doubles return a stale wait result intentionally.

### Assumptions
- A durable database reread is required after every nonterminal wait.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added bounded-wait tests; server suite first failed six tests.
- Root cause (bugfix only): Public zero waits passed through as unlimited waits.

## Task 2

### Decisions made
- Kept the 30-second limit inside `server.job_wait` only.
- Reread the database after the runtime wait returns.

### Spec deviations
- none

### Tradeoffs accepted
- The server performs one extra durable lookup after waiting.

### Assumptions
- Runtime and scheduler zero timeout semantics must remain unchanged.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest tests/test_server.py -q` passed with 15 tests.
- Root cause (bugfix only): Positive waits above 30 seconds could exceed MCP call budgets.

## Task 3

### Decisions made
- Documented repeated calls as the public polling strategy.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Clients inspect structured terminal results after polling.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest tests/test_server.py -q` passed with 15 tests after documentation update.
- Root cause (bugfix only): none
