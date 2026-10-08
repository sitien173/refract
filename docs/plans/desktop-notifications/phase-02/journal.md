<!-- ccg-shared-version: 11.0.4 -->

# Phase 2: Journal: Terminal job desktop notifications

## META

- Plan: docs/plans/desktop-notifications/PLAN.md
- Implementation Profile: implement
- Consultation Profile: consult, completed during design
- Review Profile: review
- Implementation Job: fda6d40e-4ca4-4d01-8536-1ed9cfa53075
- Review Job: 488e5055-7748-4ad9-8d78-d9be201c01dd
- Final Fix Job: 478522a8-1e68-4434-ac89-662cfe403f90
- Started: 2026-10-05
- Finished: 2026-10-05

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase: Phase 2: Terminal job desktop notifications
- Started: 2026-10-05
- Finished: 2026-10-05
- Plan dir: docs/plans/desktop-notifications

## SUMMARY
Added terminal-job desktop notification delivery with independent failure guards and mocked test coverage.

## FILES MODIFIED
| Action | Path | Change |
| Create | src/openmcp/notifications.py | Add send_job_notification helper |
| Create | tests/test_notifications.py | Add tests for send_job_notification helper |
| Modify | src/openmcp/runtime.py | Add desktop notifications dispatch in Runtime._notify_job_resource |
| Modify | tests/test_execution.py | Add execution tests for terminal desktop notifications |
| Modify | docs/plans/desktop-notifications/phase-02/notes.md | Add Task 1-4 decision notes and RED to GREEN evidence |
| Modify | docs/plans/desktop-notifications/phase-02/journal.md | Update metadata and record implementation response |

## NOTES
- docs/plans/desktop-notifications/phase-02/notes.md (## Task 1, ## Task 2, ## Task 3, ## Task 4)

## SPEC COMPLIANCE
- Meets Spec? YES - All Phase 2 acceptance criteria met and verified with fresh test runs.

## CLARIFICATIONS NEEDED
None

## NEXT
TASK_COMPLETE

### Review Fix 1 Response

# EXTERNAL RESPONSE
## META
- Phase: Phase 2: Terminal job desktop notifications (Review Fix 1)
- Started: 2026-10-05
- Finished: 2026-10-05
- Plan dir: docs/plans/desktop-notifications

## SUMMARY
Fixed concurrent retry notification loss via pre-await job snapshot and resolved warning test coverage debt.

## FILES MODIFIED
| Action | Path | Change |
| Modify | src/openmcp/runtime.py | Snapshot JobView before first await in Runtime._notify_job_resource |
| Modify | tests/test_execution.py | Add concurrent retry regression and warning assertion tests |
| Modify | docs/plans/desktop-notifications/phase-02/notes.md | Add Task 5 decision notes and regression evidence |
| Modify | docs/plans/desktop-notifications/phase-02/journal.md | Record Review Fix 1 implementation response |

## NOTES
- docs/plans/desktop-notifications/phase-02/notes.md (## Task 5)

## SPEC COMPLIANCE
- Meets Spec? YES - All Phase 2 acceptance criteria and Review Fix 1 requirements met and verified with fresh test runs.

## CLARIFICATIONS NEEDED
None

## NEXT
TASK_COMPLETE

### Review Fix 2 Response

# EXTERNAL RESPONSE
## META
- Phase: Phase 2: Terminal job desktop notifications (Review Fix 2)
- Started: 2026-10-05
- Finished: 2026-10-05
- Plan dir: docs/plans/desktop-notifications

## SUMMARY
Passed explicit exc_info tuple on deferred lookup warnings, stopped scheduler race in concurrency test, and closed runtimes.

## FILES MODIFIED
| Action | Path | Change |
| Modify | src/openmcp/runtime.py | Pass explicit exc_info tuple for deferred lookup error warning |
| Modify | tests/test_execution.py | Leave scheduler unstarted in concurrency test and wrap runtimes in try/finally |
| Modify | docs/plans/desktop-notifications/phase-02/notes.md | Add Task 6 decision notes and test evidence |
| Modify | docs/plans/desktop-notifications/phase-02/journal.md | Record Review Fix 2 implementation response |

## NOTES
- docs/plans/desktop-notifications/phase-02/notes.md (## Task 6)

## SPEC COMPLIANCE
- Meets Spec? YES - All Phase 2 acceptance criteria and Review Fix 2 requirements met and verified with fresh test runs.

## CLARIFICATIONS NEEDED
None

## NEXT
TASK_COMPLETE

## Quality Review

### Initial review

- Job: b70af530-40cc-4bd2-acc2-d72afe917091
- Revision: 66238188ddcaa19ffe540f961f7a99bda8710a86
- Status: PASS_WITH_DEBT
- Finding: LOW, tests/test_execution.py:3170. False/exception isolation tests did not assert event job.desktop_notification_failed or job_id. Owner: Phase 2 implementation owner.
- Independent focused verification: 92 passed.
- Reviewer left source, tests, and Git unchanged.

### Coordinator blocking verification

- Hypothesis H1: a post-await job lookup sees queued after concurrent retry and loses the prior failed transition.
- Reproduction: persist a failed job, pause its MCP notifier on asyncio.Event, call Runtime.retry to reset it to queued, release the terminal publish, and assert one helper call with state failed.
- Result at the reviewed revision: AssertionError: Terminal notification lost during retry: expected 1, got 0.
- Root cause: src/openmcp/runtime.py reads database.job after await self.notifier.
- Fix cycle 1: pre-await JobView snapshot with isolated lookup errors, plus warning test assertions. DESIGN.md and PLAN.md record the correction.
- Additional checks passed at the same revision: helper executed off the event loop; false/exception paths logged the expected event/job_id; MCP failure did not suppress desktop invocation; persisted job state remained succeeded. Helpers were mocked throughout.

### Fix cycle 1 review

- Job: d0dd8556-762b-434d-87ea-01d48d95785b
- Revision: 4a874928782fe0fa7111bcaf7b50e002af6a1d1b
- Status: FAIL
- MEDIUM, src/openmcp/runtime.py:97-102: deferred exc_info=True lost the captured exception and traceback. Fix: pass the captured exception tuple and assert it in the test.
- MEDIUM, tests/test_execution.py:3286-3298: starting the scheduler let retry execution race with the regression assertion. Fix: leave the scheduler unstarted.
- LOW, tests/test_execution.py:3319 and 3348: two new tests did not close Runtime. Owner: Phase 2 implementation owner. Fix: try/finally with await runtime.close().
- Prior warning-event coverage debt was resolved. The original terminal snapshot regression passed with credible RED to GREEN evidence.
- Coordinator checks: 95 focused tests passed; 461 full-suite tests passed, 3 deselected; concurrency regression passed three separate runs. Those runs did not eliminate the scheduler race identified by review.
- Review was read-only. Fix cycle 2 addresses all findings.

### Final fix review

- Job: 488e5055-7748-4ad9-8d78-d9be201c01dd
- Revision: 68bc4ee52aeec076cc3cb6f4641a6b2b14bee092
- Status: PASS
- Findings: none
- All prior findings resolved: captured exception type/value/traceback preserved and asserted; scheduler unstarted in the real concurrent retry regression; Runtime closed in both control-flow tests; warning-event and job-ID coverage retained.
- Review remained read-only. Coordinator confirmed source, tests, and Git unchanged, apart from its own handover review reference.
- Coordinator fresh verification at the reviewed revision: 95 focused tests passed; 461 full-suite tests passed, 3 deselected; clean root and whitespace check passed.
- Scope: src/openmcp/runtime.py and tests/test_execution.py final fix delta; prior helper, terminal state, config toggle, and failure-isolation reviews retained.

## Review Result

- Spec Status: PASS
- Quality Status: PASS
- Debt: none
- Concurrent retry regression: recorded failed assertion before the snapshot fix, then passed with deterministic scheduler isolation.
- Deferred lookup traceback regression: recorded None-is-RuntimeError failure before correction, then passed with captured exception tuple.

## Final Checkpoint

- Phase base ref: refs/plans/desktop-notifications/phase-02/base
- Phase implementation ref: refs/plans/desktop-notifications/phase-02/impl
- Plan commit ref: refs/plans/desktop-notifications/impl
- State checkpoint: validated temporary phase checkpoint retained by phase implementation ref

Phase refs retain review evidence after checkpoint consolidation. The plan
implementation ref identifies the sole branch commit for the completed plan.
Final verification runs the notify-py import, config tests, focused notification
and execution tests, and full suite against that consolidated commit.
