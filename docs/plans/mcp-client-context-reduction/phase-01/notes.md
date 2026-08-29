<!-- ccg-shared-version: 10.1.0 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Removed only the five MCP resource registrations and handlers named by the phase; database and runtime APIs remain unchanged.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: updated template test failed with the five obsolete templates present; after removing the handlers, `uv run pytest tests/test_server.py::test_runtime_resources_use_v2_templates_and_context` passed (1 passed).
- Fresh checks: `uv sync --all-extras --frozen` passed; `uv build` passed. The full pytest run exposed four pre-existing `job_wait` timeout mismatches (`_MCP_WAIT_TIMEOUT_S` is 300 while those tests expect 30).

## Task 2

### Decisions made
- `JobSummary` contains exactly the requested list-view fields and leaves full `JobView` unchanged.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: the new slim-model test first failed at collection because `JobSummary` was not exported; after adding the model and export, `uv run pytest tests/test_server.py::test_job_summary_is_slim` passed (1 passed).
- Fresh checks: `uv sync --all-extras --frozen` passed; `uv build` passed. The full pytest run retained the four pre-existing `job_wait` timeout mismatches documented in Task 1.

## Task 3

### Decisions made
- Partitioned the existing full database result in memory: all non-terminal jobs stay active, while terminal jobs are sorted by `updated_at` and capped at ten.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- `updated_at` values use the daemon's comparable UTC timestamp format.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: the payload test first failed because the handler returned a list; after adding the three-key bounded payload, it passed with 12 active jobs, ten ordered recent jobs, two truncated jobs, and no `result` fields.
- Fresh phase checks: `uv sync --all-extras --frozen` passed and `uv build` passed; the final full pytest run retained only the four pre-existing `job_wait` timeout mismatches.

## Task 4

### Decisions made
- Added focused coverage for zero truncation, compact JSON, and preservation of full single-job result text while updating the resource-template characterization.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: compact JSON coverage first failed on indented output; after switching `_json` to compact separators, the three new behavior tests passed (3 passed).
- Final fresh checks: `uv sync --all-extras --frozen` passed; `uv build` passed; `uv run pytest` reported 279 passed and four pre-existing `job_wait` timeout mismatches.

## Validation Reconciliation

### Decisions made
- Reconciled the four stale 30-second expectations in `tests/test_server.py` with commit `7a59db2`, which deliberately set the public `job_wait` timeout cap and default to 300 seconds; the 45-second case now correctly remains 45 because it is below the cap.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: the focused public timeout tests initially failed on the four stale expectations; after updating them, `uv run pytest tests/test_server.py::test_mcp_exposes_direct_job_contract tests/test_server.py::test_job_wait_bounds_public_timeout` passed (6 passed).
- Declared checks: `uv sync --all-extras --frozen`, `uv run pytest` (283 passed, 3 deselected), and `uv build` all passed.

## Security Reconciliation

### Decisions made
- Removed `target_id` from `JobSummary` and jobs-list serialization because configured target IDs expose provider identity; the full database `JobView` and single-job resource remain unchanged.

### Spec deviations
- The explicit Phase 1 plan/design listed `target_id` in `JobSummary` and its example payload; this fix intentionally deviates from that field to satisfy the provider-identity boundary.

### Tradeoffs accepted
- Jobs-list consumers lose target assignment detail and must use the bounded, provider-neutral summary; full job rows remain available to internal database/runtime paths.

### Assumptions
- Target IDs are provider identity and must not cross the jobs-list resource boundary.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: the security-focused tests first failed because `JobSummary` and serialized list items still exposed `target_id`; after removing the field and serialization argument, the focused model/resource tests passed (2 passed).
- 370-job measurement: busiest project returned 2,136 UTF-8 bytes (`under_4kb=True`).
- Declared checks: `uv sync --all-extras --frozen`, `uv run pytest` (283 passed, 3 deselected), and `uv build` all passed.
