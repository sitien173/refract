<!-- refract-shared-version: 2.4.0 -->

# Phase 1 — Journal: Trustworthy baseline and secure job actions

## META

- Plan: docs/plans/dashboard-spa-redesign/PLAN.md
- Implementation Profile: balanced
- Consultation Profile: n/a
- Review Profile: base
- Implementation Job: 405e95ea-c10f-4788-aa11-683df422405a, fix e1e51c41-a098-45c6-b358-8bae3a95dcc6
- Review Job: 1ea7372a-4a45-49e3-8b64-4272fc698e98, 633effcb-e497-4c6a-a7ed-fd2cfcdf4277
- Started: 2026-11-05T11:52:43+07:00
- Finished: 2026-11-05T12:40:32+07:00

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase 1 / Started 2026-11-05T11:52:43+07:00 / Finished 2026-11-05T12:21:00+07:00 / Plan dir docs/plans/dashboard-spa-redesign
## SUMMARY
Fixed the transport test timing race under load, added question-ID validation to answer delivery, and created three CSRF-guarded POST action endpoints for jobs.
## FILES MODIFIED
| Action | Path | Change |
| --- | --- | --- |
| Modify | server/tests/test_transport.py | Arm deadline deterministically on child readiness in `test_timeout_kills_the_whole_process_group` |
| Modify | server/src/refract/ask.py | Add optional `expected_question_id` check under lock in `deliver_answer` |
| Modify | server/src/refract/runtime.py | Add optional `expected_question_id` argument to `job_answer` |
| Modify | server/tests/test_ask.py | Add question ID match and mismatch tests for registry and runtime |
| Modify | server/src/refract/dashboard.py | Add CSRF guard, header constants, error mapping, and action endpoints for cancel, retry, answer |
| Create | server/tests/test_dashboard_api.py | Add CSRF rejection matrix and action endpoint tests |
| Modify | server/tests/test_dashboard.py | Update route set assertion in `test_routes_are_dashboard_routes_ask_and_actions` |
| Modify | docs/plans/dashboard-spa-redesign/phase-01/notes.md | Record per-task decisions, spec deviations, and RED/GREEN test evidence |
| Modify | docs/plans/dashboard-spa-redesign/phase-01/journal.md | Record completion timestamps and implementation response |
## NOTES
- docs/plans/dashboard-spa-redesign/phase-01/notes.md (## Task 1, ## Task 2, ## Task 3)
## SPEC COMPLIANCE
- Meets Spec? YES - All tasks implemented with behavioral RED->GREEN evidence, full test suite passes (789 passed, 15 deselected), and 20 consecutive runs of transport tests succeed.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

# EXTERNAL RESPONSE
## META
- Phase 1 (FIX 1) / Started 2026-11-05T12:26:04+07:00 / Finished 2026-11-05T12:37:00+07:00 / Plan dir docs/plans/dashboard-spa-redesign
## SUMMARY
Addressed Phase 1 review findings by requiring question_id on answer route, handling malformed origin ports, standardizing action route parameters to {job_id}, extracting shared POST preamble helper, and cleaning transport test deadline comparison.
## FILES MODIFIED
| Action | Path | Change |
| --- | --- | --- |
| Modify | server/src/refract/dashboard.py | Require question_id on answer route, handle malformed Origin port, standardize action routes to {job_id}, extract _api_post_preamble helper, and remove redundant invalid_request error mapping |
| Modify | server/tests/test_dashboard_api.py | Add tests for malformed Origin port and required question_id validation (missing, null, empty, non-string) without runtime call |
| Modify | server/tests/test_transport.py | Remove inverted __ge__ from ArmedDeadline, comment __le__ reflection, assert armed.deadline is not None, and remove redundant fallback |
| Modify | server/tests/test_dashboard.py | Update route-set assertion to expect {job_id} in action routes |
| Modify | docs/plans/dashboard-spa-redesign/phase-01/notes.md | Append ## FIX 1 decision notes, RED/GREEN test evidence, and root causes |
| Modify | docs/plans/dashboard-spa-redesign/phase-01/journal.md | Append FIX 1 external response under Implementation Response |
## NOTES
- docs/plans/dashboard-spa-redesign/phase-01/notes.md (## FIX 1)
## SPEC COMPLIANCE
- Meets Spec? YES - All review findings addressed with behavioral RED->GREEN evidence, full test suite passes (789 passed, 15 deselected), transport tests pass 20/20 runs, and focused API checks pass.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Quality Review

Review job 1ea7372a-4a45-49e3-8b64-4272fc698e98 (cc/claude-sonnet-medium-isolated): FAIL. Blocking: dashboard answer POST accepted a missing question_id, bypassing race protection. Non-blocking: malformed Origin port raised 500; ArmedDeadline had dead inverted `__ge__`; `{id}` vs `{job_id}` naming; duplicated POST preamble and redundant error branch.

FIX job e1e51c41-a098-45c6-b358-8bae3a95dcc6 resolved all five. Coordinator verification after fix: full suite 789 passed, 15 deselected; transport 20/20; targeted 53 passed.

Re-review job 633effcb-e497-4c6a-a7ed-fd2cfcdf4277: PASS_WITH_DEBT. All prior findings resolved, no new correctness or security issue. Remaining low item: `_api_json_response`/`_api_error` overlap `_json_response`/`_error`.

## Review Result

- Spec Status: PASS
- Quality Status: PASS_WITH_DEBT
- Debt: _api_json_response/_api_error overlap _json_response/_error in dashboard.py; fold or document when HTML helpers are removed (owner: Coordinator, Phase 5 cutover)

## Final Checkpoint

- Phase base ref: refs/plans/dashboard-spa-redesign/phase-01/base
- Phase implementation ref: refs/plans/dashboard-spa-redesign/phase-01/impl
- Plan commit ref: refs/plans/dashboard-spa-redesign/impl
- State checkpoint: temporary commit

Phase refs retain review evidence after checkpoint consolidation. The plan ref
names the sole commit retained on the branch.
