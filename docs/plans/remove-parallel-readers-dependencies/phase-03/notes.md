<!-- refract-shared-version: 1.2.0 -->

# Phase 3 — Decision Notes

## Task 1

### Decisions made
- Migration selects the first unfinished dependency per queued job in deterministic job/dependency order, commits each cancellation event in the same `BEGIN IMMEDIATE` transaction, then drops the dependency table and legacy column before stamping version 14.

### Spec deviations
- none

### Tradeoffs accepted
- For jobs with multiple unfinished parents, the migration error records the first unfinished parent in dependency row order; each affected queued job is cancelled once.

### Assumptions
- Version 13 databases have the `events` support table and schema shape produced by prior migrations.

### Follow-ups for human
- none

### Test evidence
- RED: new fresh-schema and v13 migration tests initially observed schema version 13 instead of 14.
- GREEN: migration tests verify removed schema, exact cancellation/error/event behavior, preservation of a queued job with succeeded dependency, and idempotent rerun.

## Task 2

### Decisions made
- Removed dependency readiness and cascade paths; terminal callbacks now only call `scheduler.complete(job_id, signal=False)`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing scheduler terminal-commit release and notifier ordering remain unchanged.

### Follow-ups for human
- none

### Test evidence
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest -q -x`: 541 passed, 3 deselected after scheduler/runtime dependency removal.

## Task 3

### Decisions made
- Removed dependency fields and codes from MCP/dashboard surfaces; unknown MCP arguments are rejected through generic argument validation. Updated the README version and submit/cancel documentation.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- An extra argument absent from a tool schema is an invalid request, with no special-case handling for `depends_on`.

### Follow-ups for human
- none

### Test evidence
- RED: MCP test showed `job_submit` accepted an extra `depends_on` argument.
- GREEN: generic unknown-argument validation returns `invalid_request`; tests verify the exact reduced summary fields and `{job:summary}` cancel envelope.

## Task 4

### Decisions made
- Removed dependency-specific tests and assertions while retaining mixed-purpose coverage for startup recovery, terminal notifier/retry ordering, and non-dependency result behavior.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- UI and plugin dependency surfaces are intentionally deferred to later phases.

### Follow-ups for human
- none

### Test evidence
- Full server suite: `uv run --extra dev pytest -q` — 541 passed, 3 deselected.
- Residue search matches only retained database migration references (`_migrate_v11_to_v12` and `_migrate_v13_to_v14`); `git diff --check` passes.

## Task 4 (fix 1)

### Decisions made
- Restored the reserved-but-unstarted dispatch/retry characterization without dependency or cascade setup. Restored the public cancellation error assertion as a standalone test.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- `execution task cancelled` remains a safe, intentionally public cancellation cause; dependency-specific causes remain removed.

### Follow-ups for human
- none

### Test evidence
- Restored tests: `test_cancel_reserved_unstarted_dispatch_then_retry_uses_fresh_event_once` and `test_public_terminal_error_preserves_execution_task_cancellation`.
- The second test passes without a production change: `_public_terminal_error` still whitelists the non-dependency cancellation cause `execution task cancelled`.
- Focused restored-test run: 2 passed. Full suite: 543 passed, 3 deselected. `git diff --check` passes.
- Audited other test deletions against Phase 3 base: dependency-only assertions were removed; mixed-purpose retained behavior, including startup interruption recovery, notifier/retry ordering, and unrelated result behavior, remains covered.
