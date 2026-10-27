<!-- refract-shared-version: 2.0.0 -->

# Phase 2 Decision Notes

Append per-task blocks with Decisions made, Spec deviations, Tradeoffs accepted, Assumptions, Follow-ups for human, and actual RED then GREEN Test evidence. Use `- none` where inapplicable.

## Task 1

### Decisions made
- Tested diagnostics endpoint behavior through the registered Starlette dashboard routes, including bounded exclusive cursors and the existing loopback-client guard.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The existing event table's `job.error_reported` kind is the authoritative report discriminator; other event kinds are excluded in SQL.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added endpoint contract test; initial run failed with HTTP 404 because the diagnostics route did not exist. After implementation, the test passed (1 passed). Expanded endpoint cursor/filter/access-control tests passed with the dashboard and database/retention/consolidation suite (129 passed).

## Task 2

### Decisions made
- Report queries use a parameterized join with allowlisted selected fields, event-ID descending order, exclusive cursor, and a `limit + 1` fetch. Query parameters reject unknown/duplicate keys, non-decimal/invalid ranges, unsupported categories, and unknown explicit project/job IDs.
- Public report state is named `current_state` to make its temporal meaning explicit. No raw event payload or report key is returned.

### Spec deviations
- none

### Tradeoffs accepted
- Category filtering uses SQLite `json_extract` against the existing event payload, without adding a schema/index change as prohibited.

### Assumptions
- Phase 1 stored sanitized expected/observed text and valid JSON report events; reads tolerate malformed JSON by omitting such records.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: The test-first endpoint test observed 404 before implementation, then returned expected filtered sanitized reports after route/query implementation. Cursor test verified an event arriving after page one does not enter the older page; explicit unknown filters return 404, invalid query values 400, and non-loopback access 403.

## Task 3

### Decisions made
- Job-detail counts use one grouped count query. Project job lists batch counts for the bounded active/recent records, avoiding a report scan/query per listed job. Suspect is derived from retained event count only.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing history pruning is authoritative; deleted events therefore naturally clear both count and suspect without changing execution state.

### Follow-ups for human
- Dashboard UI, navigation, and display remain Phase 3 scope.

### Test evidence
- RED -> GREEN: Endpoint test confirmed a report yields `suspect: true` and matching `diagnostic_count`; retention test confirms pruning clears the derived count while job execution state remains `succeeded`. Final full suite: `836 passed, 15 deselected`; plugin session-start and contract tests passed, both validators passed with three existing compatibility warnings; `git diff --check` passed.

## Task 4 — Query validation correction

### Decisions made
- Bound decimal conversion before calling `int`: normalize leading zeroes, reject limit values with more than three significant digits, and validate cursors against the 19-digit SQLite signed-integer maximum lexically. This preserves practical leading-zero forms without changing Python's global integer safeguard.
- Reject explicitly supplied empty `category`, `project_id`, and `job_id` filters as malformed, while omitted filters remain optional.

### Spec deviations
- none

### Tradeoffs accepted
- Very long strings consisting only of leading zeroes normalize before integer conversion; resulting values are still checked against the contract's valid range.

### Assumptions
- SQLite event IDs fit its signed 64-bit integer range.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: New registered-route tests using 4,500 ASCII `9` digits reproduced `ValueError: Exceeds the limit (4300 digits) for integer string conversion` for both `limit` and `before` (2 failed). After bounded normalization/range checks, both return HTTP 400. Explicit empty filters return HTTP 400; leading-zero valid values (`limit=0001`, `before=0001`) return HTTP 200. Correction-focused tests: 8 passed. Final full server/plugin/diff-check results recorded in the appended correction ERP.
