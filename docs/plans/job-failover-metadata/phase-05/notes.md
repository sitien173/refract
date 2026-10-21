# Phase 5 — Decision Notes

## Task 1

### Decisions made
- Half-open targets count as attention only through existing `circuit_open_until` handling; `healthy` semantics remain unchanged. Probing is exposed independently and means `probe_job_id` is non-empty.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- `target_health` supplies `cooldown_s` and `probe_job_id` for every target, as provided by the database API.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: dashboard targets payload contract initially failed because its allowlist omitted the three new view properties; targeted test passed after adding the fields.
- Added database-backed `target_health` coverage in `server/tests/test_dashboard.py` asserting `breaker_state`, `probing`, and `cooldown_s` across closed, open, half-open, and probing states; focused test passed.

## Task 2

### Decisions made
- Existing `max_attempts` fields are left untouched; new policy writes omit the field. A shorthand policy with zero timeout remains shorthand.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Legacy `WorkflowPolicyData.max_attempts` remains readable but is not serialized by profile mutation.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: characterization tests failed under old writes (existing value overwritten; shorthand expanded), then passed after the mutation behavior changed. Following coordinator clarification, updated only the legacy `max_attempts` assertion in `tests/test_runtime.py::test_project_override_runtime_activation_and_plan_preservation`; its timeout and plan-preservation assertions were unchanged.
- Added coverage verifying `_apply_workflow_policy` writes a new timeout policy with `targets` and `timeout_s` and no `max_attempts` for both absent and shorthand workflows. Removed the unused `max_attempts` parameter and call arguments from `ConfigurationMutationService.set_workflow_policy`. Focused tests passed; final full suite passed: 577 passed, 3 deselected.

## Task 3

### Decisions made
- Documented the Phase 4 metadata keys and failure-kind values verbatim and included `targets_unavailable` retry timing.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Plugin readers should use failure_kind for recovery and treat routing tokens as opaque.

### Follow-ups for human
- none

### Test evidence
- Documentation checked against Phase 4 descriptions and `_ERROR_CODES` in `server.py`; no separate test exists.

## Task 1 (UI)

### Decisions made
- Half-open and probing targets count as needing attention in `Targets.jsx` filter counts and status filtering because they are recovering from tripped circuit breakers and are not fully operational.
- Exposed `Breaker state`, `Cooldown`, and `Probing` metadata in the target inspector panel alongside existing `Circuit open until` handling.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Targets with `breaker_state` undefined fall back gracefully to `isCircuitOpenUntil` and `healthy` checks.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `server/web/src/screens/Targets.test.jsx::renders half-open and probing targets distinctly from open and closed targets` failed before implementation (missing status labels and metadata), then passed after adding `getTargetStatus` helper, status column handling, inspector metadata rows, and attention/healthy filter updates. Full 14 tests in `Targets.test.jsx` passed.

## Task 2 (UI)

### Decisions made
- Removed the deprecated `max_attempts` number input and form group from `ProfileEditor.jsx`, leaving timeout in the workflow grid.
- Removed `max_attempts` from the saved workflow payload in `ProfileEditor.jsx`, and removed `max attempts` text from the inherited policy preview.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Server config mutation preserves existing file `max_attempts` values independently of profile editor saves.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `server/web/src/screens/Profiles.test.jsx::omits max_attempts from profile editor save payloads and does not render max_attempts input` failed before implementation with `max_attempts: 1` in payload, then passed after removing `max_attempts` from `ProfileEditor.jsx`. Updated `Profiles.test.jsx` create test to verify absence of `max_attempts` in payload. Full 12 tests in `Profiles.test.jsx` passed.
