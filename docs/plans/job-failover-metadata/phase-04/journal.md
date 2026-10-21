<!-- refract-shared-version: 1.2.0 -->

# Phase 4 — Journal: MCP surface for next_target, metadata, and targets_unavailable


## META

- Plan: docs/plans/job-failover-metadata/PLAN.md
- Implementation Profile: implement
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: 11654b44-a570-42f2-a422-9a92c60bebef, 20096caa-6e5a-42ef-a80f-f457a16d1e27 (clarification 1), 3aa45407-e63b-43af-b3dd-1a16147468be (spec fix 1), aad1494d-2230-4c04-a248-a9be18ab3d77 (quality fix 2)
- Review Job: 517824f9-a9bf-40f2-99af-4bf210ff72f8, 90331bbd-6724-4804-bd7a-bd9c7735ace1 (fix 2 re-review)
- Started: 2026-10-21T17:18:01Z
- Finished: 2026-10-21T17:44:58Z

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase 4 / Started 2026-10-22T00:19:12+07:00 / Finished 2026-10-22T00:24:35+07:00 / Plan dir docs/plans/job-failover-metadata
## SUMMARY
Implemented opaque routing tokens, pinned submissions, breaker pre-check errors, and live terminal metadata over MCP.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/src/refract/planning.py | Added candidate-bound opaque token generation and resolution |
| Modified | server/src/refract/runtime.py | Added token pinning, breaker pre-checks, retry delay, and live result metadata |
| Modified | server/src/refract/server.py | Exposed next_target and metadata; added targets_unavailable payload support and MCP descriptions |
| Modified | server/tests/test_runtime.py | Added token and submission pre-check regressions |
| Modified | server/tests/test_server.py | Updated terminal metadata/schema tests and added error validation regression |
| Modified | docs/plans/job-failover-metadata/phase-04/notes.md | Recorded task decisions and verification evidence |
| Modified | docs/plans/job-failover-metadata/phase-04/journal.md | Appended this ERP block and finished timestamp |
## NOTES
- docs/plans/job-failover-metadata/phase-04/notes.md (## Task 1–4)
## SPEC COMPLIANCE
- Meets Spec? WITH_DEBT — targeted suite passed (65 passed); full suite has 565 passed, 3 deselected, and 3 failures in out-of-scope tests asserting pre-check behavior that contradicts the new required fail-fast semantics.
## CLARIFICATIONS NEEDED
Please authorize updates to the three legacy assertions in server/tests/test_execution.py (excluded by Phase 4 file scope), or specify another acceptable handling. The required full-suite command cannot pass while those assertions remain unchanged.
## NEXT
BLOCKED

# EXTERNAL RESPONSE
## META
- Phase 4 Coordinator clarification 1 / Started 2026-10-22T00:27:40+07:00 / Finished 2026-10-22T00:29:16+07:00 / Plan dir docs/plans/job-failover-metadata
## SUMMARY
Updated three execution regressions per Coordinator guidance while keeping the required pre-insert all-open-target pre-check unchanged.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/tests/test_execution.py | Reworked dispatch circuit-open test to invoke TargetExecutor directly; changed two dependency-parent drivers to REQUEST_FATAL/request_error |
| Modified | docs/plans/job-failover-metadata/phase-04/notes.md | Recorded the three rewrites and passing verification |
| Modified | docs/plans/job-failover-metadata/phase-04/journal.md | Appended this updated ERP response |
## NOTES
- docs/plans/job-failover-metadata/phase-04/notes.md (Task 2 test evidence)
## SPEC COMPLIANCE
- Meets Spec? YES — targeted runtime/server suite 65 passed; execution suite 121 passed; full suite 568 passed, 3 deselected.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

# EXTERNAL RESPONSE
## META
- Phase 4 spec review fix cycle 1 / Started 2026-10-22T00:29:16+07:00 / Finished 2026-10-22T00:34:14+07:00 / Plan dir docs/plans/job-failover-metadata
## SUMMARY
Added evidence for all blocking Phase 4 routing, retry pre-check, MCP error, and paged-result criteria; no production defect was found.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/tests/test_runtime.py | Added live routing/non-persistence, actual second-target execution, stale/foreign token, and retry state-preservation regressions |
| Modified | server/tests/test_server.py | Added MCP all-open error and bounded/private multipage metadata regressions |
| Modified | docs/plans/job-failover-metadata/phase-04/notes.md | Added Task 5 decisions and evidence |
| Modified | docs/plans/job-failover-metadata/phase-04/journal.md | Appended this fix-cycle ERP |
## NOTES
- docs/plans/job-failover-metadata/phase-04/notes.md (## Task 5 — Fix cycle 1)
## SPEC COMPLIANCE
- Meets Spec? YES — required targeted suite 71 passed; full suite 574 passed, 3 deselected.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

# EXTERNAL RESPONSE
## META
- Phase 4 quality review fix cycle 2 / Started 2026-10-22T00:34:14+07:00 / Finished 2026-10-22T00:41:56+07:00 / Plan dir docs/plans/job-failover-metadata
## SUMMARY
Fixed stale retry delay after configuration reload, canonicalized routing-token hashing, removed unused runtime API details, and tightened wait/test fixture contracts.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/src/refract/runtime.py | Use current catalog cooldown; annotate plan; remove unused imports and parameter |
| Modified | server/src/refract/planning.py | Hash compact JSON array token material |
| Modified | server/src/refract/server.py | Call `live_result_metadata` directly |
| Modified | server/tests/test_runtime.py | Added RED-first reload cooldown test and exact canonical token hash assertion |
| Modified | server/tests/test_server.py | Added `live_result_metadata` to wait test doubles |
| Modified | server/tests/test_execution.py | Corrected two REQUEST_FATAL fixtures using named DriverResult fields |
| Modified | docs/plans/job-failover-metadata/phase-04/notes.md | Appended Task 6 findings and test evidence |
| Modified | docs/plans/job-failover-metadata/phase-04/journal.md | Appended this ERP response and updated finish timestamp |
## NOTES
- docs/plans/job-failover-metadata/phase-04/notes.md (## Task 6 — Fix cycle 2)
## SPEC COMPLIANCE
- Meets Spec? YES — targeted suite 72 passed; full suite 575 passed, 3 deselected.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Quality Review

<!-- Coordinator appends the independent review response here. -->

Coordinator spec review at 42395d3: FAIL. No test evidence for live next_target from job_wait, execution on the pinned second target, foreign-profile and stale-revision token rejection at submit, job_retry targets_unavailable, the MCP retry_after_s error path, or multi-page metadata within byte and privacy limits. Fix 1 job 3aa45407 added six tests; spec re-check PASS at d08bfc3.

Review 517824f9, range refs/plans/job-failover-metadata/phase-04/base..d08bfc3:

# CODE QUALITY REVIEW
- Status: FAIL
- Findings: medium, blocking, server/src/refract/runtime.py, 568, probe estimate used startup self.config, so retry_after_s was stale after reload; low, non-blocking: duplicate method-local datetime imports; unused project_id parameter and TargetSelection import; hasattr fallback in job_wait; "\\0" token separator; REQUEST_FATAL fixture argument order in test_execution.py.
- Scope checked: server/src/refract/planning.py, server/src/refract/runtime.py, server/src/refract/server.py, server/tests/test_runtime.py, server/tests/test_server.py, server/tests/test_execution.py

Fix 2 job aad1494d addressed all six findings. Re-review 90331bbd, range d08bfc3..f63fbe4:

# CODE QUALITY REVIEW
- Status: PASS
- Findings: none
- Scope checked: server/src/refract/planning.py, server/src/refract/runtime.py, server/src/refract/server.py, server/tests/test_runtime.py, server/tests/test_server.py, server/tests/test_execution.py

## Review Result

- Spec Status: PASS
- Quality Status: PASS
- Checks at f63fbe4: targeted runtime and server suite 72 passed; full suite 575 passed, 3 deselected
- Scope addition: server/tests/test_execution.py, three tests, authorized in clarification 1
- Debt: none

## Final Checkpoint

- Phase base ref: refs/plans/job-failover-metadata/phase-04/base
- Phase implementation ref: refs/plans/job-failover-metadata/phase-04/impl
- Plan commit ref: refs/plans/job-failover-metadata/impl or `pending`
- State checkpoint: temporary commit, or `n/a (untracked)` when plan artifacts
  are excluded

Phase refs retain review evidence after checkpoint consolidation. The plan ref
names the sole commit retained on the branch.
