<!-- refract-shared-version: 1.2.0 -->

# Phase 3 — Journal: Remove job dependencies and migrate the schema

## META

- Plan: docs/plans/remove-parallel-readers-dependencies/PLAN.md
- Implementation Profile: implement
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: bc4591f3-70a2-4315-9edf-f1e2adfaae89
- Review Job: 4b289e58-ad17-4988-a343-fdf7f5a7f0e4 FAIL; 485f8252-8b29-43db-a798-4aa42e73a8d2 PASS
- Started: 2026-10-22T18:28:00+07:00
- Finished: 2026-10-22T18:47:00+07:00

## Implementation Response

<!-- Coordinator appends the external response here. -->

# EXTERNAL RESPONSE
## META
- Phase 3 / Started 2026-10-22T18:28:00+07:00 / Finished 2026-10-22T18:37:25+07:00 / Plan dir docs/plans/remove-parallel-readers-dependencies
## SUMMARY
Removed job dependencies from the daemon and MCP/dashboard surfaces, and migrated existing databases to schema version 14.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/src/refract/database.py | Added transactional v13-to-v14 migration; fresh schema removes dependency table/access column; replaced dependency insert APIs with plain job creation |
| Modified | server/src/refract/scheduler.py | Removed dependency readiness, reevaluation, and waiting-reason logic |
| Modified | server/src/refract/runtime.py | Removed dependency readiness/cascade/startup repair and dependency submit/cancel/retry behavior |
| Modified | server/src/refract/models.py | Removed dependency/waiting summary and dashboard fields and cancelled-dependent result field |
| Modified | server/src/refract/server.py | Removed dependency parameters, codes, descriptions, instructions, progress metadata, and cancelled-dependent response field; generic unknown arguments return `invalid_request` |
| Modified | server/src/refract/dashboard.py | Removed dependency/waiting job output fields |
| Modified | server/README.md | Set version 2.0.0 and documented one-job-per-project FIFO admission and reduced tool signatures |
| Modified | server/tests/test_database.py | Added v13 migration, cancellation event, preservation, idempotence, and fresh v14 schema coverage; removed dependency persistence tests |
| Modified | server/tests/test_scheduler.py | Removed dependency readiness test and waiting reason assertions |
| Modified | server/tests/test_execution.py | Removed dependency/cascade tests while retaining startup recovery and terminal notifier/retry coverage |
| Modified | server/tests/test_server.py | Added unknown `depends_on` argument and exact summary/cancel envelope coverage; removed dependency-specific tests |
| Modified | server/tests/test_dashboard.py | Removed dependency waiting-metadata test |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-03/notes.md | Recorded decisions and RED→GREEN evidence for Tasks 1–4 |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-03/journal.md | Appended implementation response |
## NOTES
- phase-03/notes.md (## Task 1, ## Task 2, ## Task 3, ## Task 4)
## SPEC COMPLIANCE
- Meets Spec? YES — full server suite: 541 passed, 3 deselected; residue search matches only retained database migration references; `git diff --check` passes.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

# EXTERNAL RESPONSE
## META
- Phase 3 / Review fix cycle 1 / Started 2026-10-22T18:37:25+07:00 / Finished 2026-10-22T18:43:21+07:00 / Plan dir docs/plans/remove-parallel-readers-dependencies
## SUMMARY
Restored characterization for cancelling a reserved unstarted dispatch before retry and for exposing the safe execution-cancellation error.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/tests/test_execution.py | Added `test_cancel_reserved_unstarted_dispatch_then_retry_uses_fresh_event_once` without dependency/cascade setup |
| Modified | server/tests/test_server.py | Added `test_public_terminal_error_preserves_execution_task_cancellation` |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-03/notes.md | Appended review-fix rationale and test evidence |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-03/journal.md | Appended review-fix response |
## NOTES
- phase-03/notes.md (## Task 4 (fix 1))
## SPEC COMPLIANCE
- Meets Spec? YES — full server suite: 543 passed, 3 deselected; `git diff --check` passes. No production files changed; cancellation cause remains exposed by the existing safe whitelist.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Review Response

<!-- Coordinator appends the independent review response here. -->

## Coordinator Evidence

- Jobs: bc4591f3 TASK_COMPLETE; fc0a26a4 fix cycle 1 TASK_COMPLETE.
- Review 4b289e58 FAIL: two Medium findings on deleted mixed-purpose tests. Fixed in b1b689e with two restored tests.
- Fresh checks: pytest 543 passed, 3 deselected; git diff --check clean; residue only database.py migration steps v11-to-v12 and v13-to-v14.
- Noted behavior: server.py now rejects unknown tool arguments with invalid_request for every tool; reviewer accepted it.
- Review 485f8252 PASS, no findings.
