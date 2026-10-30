<!-- refract-shared-version: 2.1.0 -->

# Phase 1 Decision Notes

## Task 1

### Decisions made
- Used a deterministic temporary database and two-target fixture with a succeeded job; no historical job or live backend was contacted.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Initial RED: the first assertion incorrectly expected an internal runtime return shape that omitted its existing `project_id`. This was a test-shape mistake, not valid RED evidence; corrected and superseded by the precise RED below.
- Correct original-behavior RED: temporarily removed only the two production hunks (`Runtime.report_error` post-record routing and MCP top-level serialization) using exact edits. `cd server && uv run pytest -q tests/test_runtime.py -k report_acknowledgement_state_category` failed at the intended missing-behavior assertion with `KeyError: 'retry'` at `assert result["retry"]["retryable"] is eligible`. Reapplied the identical production hunks with exact edits (no restore/reset). This is the reproduced acknowledgement defect, not a fixture/key-shape failure.
- GREEN: same focused coverage passes after reapplying production changes; new report-specific suite passed (7 passed).
- Existing characterization: succeeded `live_result_metadata` keeps retry fields null and `job_retry` rejects succeeded jobs; integrated report test asserts both after reporting.

## Task 2

### Decisions made
- Record/deduplicate first, then load current job state and conditionally reuse `_next_target_token`; routing remains response-only.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- GREEN: serialized MCP acknowledgements retain report/duplicate and add only retry; protocol/nonterminal reports serialize false/null, output-success serializes a token, duplicate retains report ID, and summaries/project_id/private strings are absent.

## Task 3

### Decisions made
- Duplicate routing is recalculated against live health and configuration; tokens remain bound to existing project/profile/workflow/revision/candidate scope.

### Spec deviations
- none; all originally deferred coverage added in Specification Batch 1.

### Tradeoffs accepted
- Reused existing target selection and token-validation paths without changes.

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- A report-specific matrix covers queued/running/failed/cancelled/interrupted/succeeded crossed with protocol/output; only succeeded+output is eligible.
- Unavailable/exhausted fallback returns false/null. Identical retained duplicates keep one event and the report ID; changing fallback health refreshes from target b to c, and exhausting the sole fallback refreshes to false/null.
- Configuration revision change rejects the old token; identical duplicate refreshes a distinct valid token. Tests reject mismatched project, profile, and workflow using `resolve_next_target`.

## Task 4

### Decisions made
- Reporting never submits; explicit `Runtime.submit` consumes the acknowledgement token with `fresh_session=True`.

### Spec deviations
- none; all originally deferred coverage added in Specification Batch 1.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Integrated fake-executor report → explicit submit produces a distinct job ID targeting b, stores `fresh_session=1`, and passes an empty session ID to the executor. Before submission, reporting leaves execution list and job count unchanged.
- Entire original job record/result metadata, context sessions, and target-health rows match snapshots around reporting. After report, `job_wait`/live result retry remains null and `job_retry` returns `invalid_state`.
- Actual MCP serialization covers eligible output token, ineligible false/null, duplicate ID/freshness, and privacy; existing validation, conflict, redaction, and logging tests remain.

## Preserved initial implementation notes (before Specification Batch 1)

The initial notes recorded the following evidence and deferred items; their deferred status is resolved by the Batch 1 tests above.

- Initial Task 1 RED claim: `uv run pytest -q tests/test_runtime.py -k report_error_acknowledges_succeeded_output_with_live_fallback` failed because the assertion saw `project_id` rather than the expected set; this was an incorrect test-shape assertion, not correct missing-behavior RED. The later exact KeyError RED above supersedes it.
- Initial Task 1 GREEN: same test passed after implementation (1 passed). Initial characterization referenced existing succeeded `live_result_metadata` and retry behavior.
- Initial Task 2: report was recorded/deduplicated before reading current job, and MCP acknowledgement was expanded; initial focused result was 189 passed, 4 skipped.
- Initial Task 3: report-ID preservation and duplicate recomputation were covered, but health/config freshness, exhausted target and stale-token report-specific checks were deferred. These are now tested above.
- Initial Task 4: execution change was avoided, but integrated report-to-submit and fresh-session behavior were deferred. These are now tested above.
- Initial verification: focused 189 passed, 4 skipped; full 1251 passed, 23 skipped, 15 deselected; plugin contracts and diff check passed. Superseded by fresh Batch 1 checks below.

## Specification Batch 1 — completion evidence

- Focused exact command: `(cd server && uv run pytest -q tests/test_runtime.py tests/test_server.py tests/test_database.py)` — 193 passed, 4 skipped.
- Full exact command: `(cd server && uv run pytest -q)` — 1255 passed, 23 skipped, 15 deselected.
- `bash plugin/tests/test-contracts.sh` — passed.
- `git diff --check` — passed.
- Production changes remain the same minimal two hunks; no planning, database, execution, `job_wait`, `job_retry`, or token-format changes.
