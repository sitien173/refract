<!-- refract-shared-version: 1.2.0 -->

# Phase 2 — Journal: 3-state circuit breaker, config keys, and schema v13

<!--
Phase Journal template. Copy to docs/plans/job-failover-metadata/phase-02/journal.md at phase
start, fill the META, then append the full `# EXTERNAL RESPONSE` block (see
erp.md) under `## Implementation Response` after all tasks. Never overwrite earlier
sections.
-->

## META

- Plan: docs/plans/job-failover-metadata/PLAN.md
- Implementation Profile: implement
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: 6e06574c-0349-4307-98a0-eb9d9989e806, 8de61cc3-fe0e-4acf-b227-33aa5b8d572e, 7754411a-40d0-4cc1-afe0-3b2a82cc86b3 (fix 1), 0f8d368e-c854-4f28-89a3-df8407445595 (fix 2)
- Review Job: 377bc896-59da-429a-b5a5-7fc8e60b72ba, 75978c02-b004-442d-91e2-c70c6d9d6460 (fix 2 re-review)
- Started: 2026-10-21T15:37:38Z
- Finished: 2026-10-21T22:34:00+07:00

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase 2 / Started 2026-10-21T15:37:38Z / Finished 2026-10-21T22:34:00+07:00 / Plan dir docs/plans/job-failover-metadata
## SUMMARY
Added breaker configuration, schema v13 probe metadata, derived half-open probe admission, failure accounting, and startup orphan recovery; phase is blocked on test updates and green verification.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/src/refract/config.py | Added breaker defaults/validation and max_attempts deprecation logging |
| Modified | server/src/refract/database.py | Added v13 schema/migration and breaker probe/cooldown operations |
| Modified | server/src/refract/execution.py | Added configured 3-state breaker selection and counting behavior |
| Modified | server/src/refract/runtime.py | Reset orphaned probes before scheduler start |
| Modified | docs/plans/job-failover-metadata/phase-02/notes.md | Recorded Task 1–4 decisions and evidence |
| Modified | docs/plans/job-failover-metadata/phase-02/journal.md | Appended implementation response |
## NOTES
- docs/plans/job-failover-metadata/phase-02/notes.md (## Task 1–4)
## SPEC COMPLIANCE
- Meets Spec? WITH_DEBT — targeted suite failed (13 failed, 184 passed); legacy schema and immediate-retry tests require updates, and concurrent probe/restart acceptance checks remain unverified.
## CLARIFICATIONS NEEDED
- None; remaining work is implementation/test reconciliation, not a specification ambiguity.
## NEXT
CONTINUE_CONTEXT

# EXTERNAL RESPONSE
## META
- Phase 2 / Continued 2026-10-21T22:34:00+07:00 / Finished 2026-10-21T22:54:10+07:00 / Plan dir docs/plans/job-failover-metadata
## SUMMARY
Completed the configured three-state target breaker, v13 migration, atomic probe lifecycle, and orphan-probe startup recovery with targeted and full test suites passing.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/src/refract/config.py | Breaker configuration defaults/validation and workflow max_attempts deprecation warning |
| Modified | server/src/refract/database.py | Schema v13 migration, atomic probe claim/release/reset, cooldown/failure/success recording |
| Modified | server/src/refract/execution.py | Derived breaker state, half-open claim, outcome accounting, and probe cleanup |
| Modified | server/src/refract/runtime.py | Clear orphaned probes before scheduler startup |
| Modified | server/tests/test_config.py | Config defaults, deprecation warning, and max/base validation tests |
| Modified | server/tests/test_database.py | v13 schema/migration, failure/success/cooldown, and concurrent probe claim tests |
| Modified | server/tests/test_execution.py | Non-counted outcome release and restart recovery tests; adjusted legacy retry fixtures |
| Modified | docs/plans/job-failover-metadata/phase-02/notes.md | Updated Task 1–4 evidence |
| Modified | docs/plans/job-failover-metadata/phase-02/journal.md | Appended completion ERP block |
## NOTES
- docs/plans/job-failover-metadata/phase-02/notes.md (## Task 1–4)
- Rewritten legacy tests: `test_retrying_parent_does_not_revive_cancelled_descendant`, `test_retry_is_not_lost_while_terminal_notifier_is_paused`, and `test_fresh_job_retry_survives_and_runs_fresh` now use `REQUEST_FATAL` for their initial failure. These tests cover retry/dependent lifecycle, and should not open the target breaker.
## SPEC COMPLIANCE
- Meets Spec? YES — acceptance scenarios are covered and both requested Python verification commands pass.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

# EXTERNAL RESPONSE
## META
- Phase 2 FIX 1 / Started 2026-10-21T22:54:10+07:00 / Finished 2026-10-21T23:04:21+07:00 / Plan dir docs/plans/job-failover-metadata
## SUMMARY
Fixed half-open probe leakage by releasing claims for candidates not returned by target selection.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/src/refract/execution.py | Release claimed probes on non-selected targets |
| Modified | server/tests/test_execution.py | Added RED→GREEN capacity/probe-leak regression test |
| Modified | docs/plans/job-failover-metadata/phase-02/notes.md | Appended Fix 1 decision and evidence |
| Modified | docs/plans/job-failover-metadata/phase-02/journal.md | Appended this ERP block |
## NOTES
- docs/plans/job-failover-metadata/phase-02/notes.md (## Fix 1)
## SPEC COMPLIANCE
- Meets Spec? YES — regression test and both requested verification suites pass.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

# EXTERNAL RESPONSE
## META
- Phase 2 FIX 2 / Started 2026-10-21T23:04:21+07:00 / Finished 2026-10-21T23:41:55+07:00 / Plan dir docs/plans/job-failover-metadata
## SUMMARY
Closed probe leaks on exceptional capacity, driver, and recorder exits, and prevented TARGET_FATAL probes from doubling cooldown.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/src/refract/execution.py | Added ownership-checked probe release on exceptional exits; kept TARGET_FATAL cooldown unchanged |
| Modified | server/tests/test_execution.py | Added four RED→GREEN exceptional-exit and cooldown regression tests |
| Modified | docs/plans/job-failover-metadata/phase-02/notes.md | Appended Fix 2 decisions and verification evidence |
| Modified | docs/plans/job-failover-metadata/phase-02/journal.md | Appended this ERP block |
## NOTES
- docs/plans/job-failover-metadata/phase-02/notes.md (## Fix 2)
## SPEC COMPLIANCE
- Meets Spec? YES — all four regression tests pass; targeted suite 211 passed and full suite 562 passed, 3 deselected.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Quality Review

<!-- Coordinator appends the independent review response here. -->

Six earlier review jobs on a resumed session returned no review: the target reported zero tool calls remaining. Job 377bc896 used `fresh_session: true` and completed.

Review 377bc896, range refs/plans/job-failover-metadata/phase-02/base..17ff629:

# CODE QUALITY REVIEW
- Status: FAIL
- Findings:
  - high, blocking, server/src/refract/execution.py, 110, Probe cleanup does not cover cancellation while acquiring capacity, driver exceptions, or recorder-close failures; these leave the target permanently open until restart.
  - medium, blocking, server/src/refract/execution.py, 336, TARGET_FATAL on a held probe doubles cooldown through failed_probe=True, contrary to the required immediate open at current cooldown.
- Scope checked: server/src/refract/{config.py,database.py,execution.py,runtime.py}, server/tests/{test_config.py,test_database.py,test_execution.py}

Fix 2 job 0f8d368e addressed both findings. Re-review 75978c02, range 17ff629..10ab45c:

# CODE QUALITY REVIEW
- Status: PASS
- Findings: none
- Scope checked: server/src/refract/execution.py, server/tests/test_execution.py

## Review Result

- Spec Status: PASS
- Quality Status: PASS
- Checks at 10ab45c: targeted suite 211 passed; full suite 562 passed, 3 deselected
- Debt: none

## Final Checkpoint

- Phase base ref: refs/plans/job-failover-metadata/phase-02/base
- Phase implementation ref: refs/plans/job-failover-metadata/phase-02/impl
- Plan commit ref: pending
- State checkpoint: temporary commit

Phase refs retain review evidence after checkpoint consolidation. The plan ref
names the sole commit retained on the branch.
