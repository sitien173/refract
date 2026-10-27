<!-- refract-shared-version: 2.0.0 -->

# Phase 1 Decision Notes

Append one Task block per task. Include Decisions made, Spec deviations, Tradeoffs accepted, Assumptions, Follow-ups for human, and Test evidence. Empty subsections use `- none`. Record actual RED then GREEN commands and output.


## Task 1

### Decisions made
- Defined `record_error_report` on `Database` and `report_error` on `Runtime` with stubs raising `NotImplementedError` to establish credible test-first RED states without import failures.
- Exposed `redact_text` in `refract.logging_setup` as a public helper reusing existing secret regex patterns.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  RED command: `cd server && uv run --extra dev pytest -q tests/test_database.py -k "test_record_error_report"`
  RED output:
  `FFFFFFF                                                                  [100%]`
  `7 failed, 52 deselected in 1.19s`
  Failures:
  `FAILED tests/test_database.py::test_record_error_report_validation_and_unknown_job - NotImplementedError: Database.record_error_report not implemented`
  `FAILED tests/test_database.py::test_record_error_report_redaction - NotImplementedError: Database.record_error_report not implemented`
  `FAILED tests/test_database.py::test_record_error_report_duplicate_delivery - NotImplementedError: Database.record_error_report not implemented`
  `FAILED tests/test_database.py::test_record_error_report_conflict_same_key_different_content - NotImplementedError: Database.record_error_report not implemented`
  `FAILED tests/test_database.py::test_record_error_report_concurrent_insertions - NotImplementedError: Database.record_error_report not implemented`
  `FAILED tests/test_database.py::test_record_error_report_failed_write_truthful - NotImplementedError: Database.record_error_report not implemented`
  `FAILED tests/test_database.py::test_record_error_report_restart_persistence - NotImplementedError: Database.record_error_report not implemented`

  RED command: `cd server && uv run --extra dev pytest -q tests/test_server.py -k "test_job_report_error_mcp_validation_and_acknowledgement"`
  RED output:
  `FAILED tests/test_server.py::test_job_report_error_mcp_validation_and_acknowledgement - AssertionError: assert 'internal_error' == 'invalid_request'`
- Root cause (bugfix only): - none


## Task 2

### Decisions made
- Implemented `DiagnosticReport` and `DiagnosticReportResult` models in `refract.models`.
- Reused `run_sync` in `Runtime.report_error` to execute `Database.record_error_report` on worker threads.
- In `server.py`, `job_report_error` logs `job.error_reported` only when `duplicate` is `False`, strictly omitting report keys and summaries from logs and compact MCP responses.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  GREEN command: `cd server && uv run --extra dev pytest -q tests/test_database.py -k "test_record_error_report"`
  GREEN output:
  `.......                                                                  [100%]`
  `7 passed, 52 deselected in 0.75s`

  GREEN command: `cd server && uv run --extra dev pytest -q tests/test_server.py -k "test_job_report_error"`
  GREEN output:
  `..                                                                       [100%]`
  `2 passed, 62 deselected in 2.15s`
- Root cause (bugfix only): - none


## Task 3

### Decisions made
- Verified across all job states (queued, running, succeeded, failed, cancelled, interrupted) that `job_report_error` leaves state, attempts, timestamps (`created_at`, `updated_at`), result text, error, routing, queue ordering, and target health untouched.
- Verified retention policy removes diagnostic report events for expired terminal jobs and resets deduplication scope, while preserving events and deduplication for active/recent jobs.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Characterization (behavior preservation):
  Task 3 tests characterize unchanged pre-existing execution and retention behavior. As characterization coverage verifying existing behavior preservation, no artificial RED state was fabricated.
  Passing characterization command: `cd server && uv run --extra dev pytest -q tests/test_retention.py -k "test_diagnostic_report"`
  Output:
  `.                                                                        [100%]`
  `1 passed, 4 deselected in 0.27s`

  Passing characterization command: `cd server && uv run --extra dev pytest -q tests/test_database.py -k "test_record_error_report_preserves"`
  Output:
  `.                                                                        [100%]`
  `1 passed, 59 deselected in 0.40s`
- RED -> GREEN: - none (characterization of unchanged behavior)
- Root cause (bugfix only): - none


## Task 4

### Decisions made
- Registered `job_report_error` on the MCP server with annotations `(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)`.
- Updated canonical tool reference `tool-contract.md` heading to `## Nine tools` and registered exact tool schema assertions while strictly keeping file size within the 90-line limit (85 lines).
- Updated SDK unknown tool error message to reference nine tools returned by `tools/list`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  GREEN command: `cd server && uv run --extra dev pytest -q tests/test_server.py -k "test_v2_tool"`
  GREEN output:
  `..                                                                       [100%]`
  `2 passed, 62 deselected in 1.62s`

  GREEN command: `cd server && uv run --extra dev pytest -q tests/test_mcp_schema_contract.py`
  GREEN output:
  `.....                                                                    [100%]`
  `5 passed in 1.49s`

  GREEN command: `bash plugin/tests/run.sh`
  GREEN output:
  `session-start tests passed`
  `contract tests passed`
  `✔ Validation passed with 3 warnings`
- Root cause (bugfix only): - none
