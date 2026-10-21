<!-- refract-shared-version: 1.2.0 -->

# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Added daemon breaker settings with the specified defaults and positive-integer validation. Retained parsing and storage of workflow `max_attempts`; emitted `config.deprecated_key` for explicit declarations.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Deprecated warning is emitted at profile declaration parsing (one per profile/workflow occurrence).

### Follow-ups for human
- none

### Test evidence
- Added `test_breaker_config_defaults_and_deprecated_max_attempts_warning` and `test_breaker_max_cooldown_must_not_be_below_base`; config suite passes as part of the 206-test targeted run.

## Task 2

### Decisions made
- Added v13 schema and guarded the v12 migration against columns already created by support-table initialization on older databases. Added one-statement probe claim and reset/release/failure/success operations.

### Spec deviations
- Migration uses column-presence guards for legacy versions where `target_health` is first created with the current DDL.

### Tradeoffs accepted
- none

### Assumptions
- Cooldown value zero is normalized to the configured base when recording a failure.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_v12_to_v13_migration_preserves_rows` initially failed because the test inserted its pre-migration health row outside a transaction; committing the row made preservation evidence meaningful. Updated schema assertions now include v13 metadata columns.
- Targeted suite passed: 206 passed.

## Task 3

### Decisions made
- Selection derives half-open status from timestamps and atomically claims a probe for the current job. Failure accounting uses configured threshold/cooldowns; retryable failures count, target-fatal opens immediately, success resets, and excluded outcomes release a held probe.

### Spec deviations
- none

### Tradeoffs accepted
- Existing attempt loop was not changed.

### Assumptions
- Driver outcomes are `RETRYABLE`, `TARGET_FATAL`, `SUCCESS`, `CANCELLED`, and `REQUEST_FATAL` as used by the current executor.

### Follow-ups for human
- none

### Test evidence
- Rewrote `test_retrying_parent_does_not_revive_cancelled_descendant`, `test_retry_is_not_lost_while_terminal_notifier_is_paused`, and `test_fresh_job_retry_survives_and_runs_fresh` to fail first with `REQUEST_FATAL`, because these tests cover retry/dependency lifecycle rather than target-breaker opening.
- Added threshold/immediate-open, success reset, cooldown cap, atomic 20-way claim, and non-counted-probe outcome coverage. Targeted suite: 206 passed.

## Task 4

### Decisions made
- Startup clears orphaned probe ownership and makes those targets immediately half-open before scheduler startup.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing startup recovery order remains otherwise unchanged.

### Follow-ups for human
- none

### Test evidence
- `test_restart_releases_orphaned_probe_to_half_open` verifies daemon restart clears orphan ownership and leaves the target half-open.
- Full verification: targeted suite 206 passed; full `uv run pytest -q`: 557 passed, 3 deselected.

## Fix 1

### Decisions made
- Keep atomic claims during candidate scanning, but release every claimed half-open probe that is not the target returned by `_select_target`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- If all healthy candidates are at capacity, the existing fallback selection behavior remains; only the returned target may retain its probe claim.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_half_open_probe_claim_is_not_leaked_when_target_at_capacity` first failed with `probe_job_id == 'probe-job'` despite selecting the closed target; after cleanup of claims not matching the selected target, it passed.
- Targeted suite: 207 passed. Full suite: 558 passed, 3 deselected.

## Fix 2

### Decisions made
- Release probe ownership on exceptions from capacity acquisition, driver invocation, and recorder finalization. Keep release ownership-checked through the database API's `(target_key, job_id)` predicate.
- TARGET_FATAL on a claimed probe opens immediately without requesting cooldown doubling; the failure recorder clears the held probe while retaining its existing cooldown.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Release is safe when invoked more than once because the database update is conditional on the owning job ID.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: four regression tests initially failed: driver exception retained probe ID, capacity-acquire cancellation retained it, recorder close failure retained it, and TARGET_FATAL changed cooldown 77 to 154. All passed after the fix.
- Targeted suite: 211 passed. Full suite: 562 passed, 3 deselected.
