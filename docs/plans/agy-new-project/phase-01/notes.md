# Phase 1 — Decision Notes

## Task 1

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED: removing the conditional flag caused the new-session regression test to fail while the resume test passed: 1 failed, 1 passed.
- GREEN: restoring the conditional flag produced 2 passed.
- Root cause: new-session argv omitted `--new-project`.

## Task 2

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED: without the source change, the new-session assertion failed while the resumed-session assertion passed.
- GREEN: `uv run pytest tests/test_smoke.py -k agy -q` -> 8 passed, 43 deselected.

## Task 3

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: focused `uv run pytest tests/test_smoke.py -k agy -q` ->
  8 passed. Full `uv run pytest -q` -> 172 passed, 4 failed, 3 deselected;
  the 4 failures (`tests/test_server.py::test_mcp_exposes_direct_job_contract`,
  `test_job_wait_bounds_public_timeout[None/0/45-30]`) reproduce on the clean
  pre-change tree and are unrelated to this phase. The new and resumed argv
  assertions both pass.
