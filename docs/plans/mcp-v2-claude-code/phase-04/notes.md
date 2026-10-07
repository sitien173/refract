# Phase 4 — Decision Notes

## Task 1

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Preserved test-first evidence in `/tmp/mcp-v2-phase4-recovery-evidence.tzGQYW/test-evidence.json`: initial compact JSON error/client regressions failed (2/2), then were made green in subsequent focused runs. Fresh actual-client checks on this tree passed under SDK 2.0.0 (3 passed) and SDK 2.3.0 (validation and expected-error checks passed).
- Root cause (bugfix only): The SDK validation and ToolError response shape differs from model-visible JSON tool errors; the implemented middleware normalizes only validated OpenMCP payloads and known schema failures, sanitizing unknown failures.
- Fresh full suite: `timeout --kill-after=5s 180s uv run --extra dev pytest -q` -> 529 passed, 3 deselected.

## Task 2

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Preserved evidence records initial tool-surface and four-call client regressions failing, followed by focused GREEN runs. Fresh focused verification: `timeout --kill-after=5s 180s uv run --extra dev pytest tests/test_server.py tests/test_runtime.py tests/test_execution.py tests/test_smoke.py tests/test_notifications.py -q` -> 225 passed.
- Root cause (bugfix only): Replaced the legacy seven-tool/resource API with the approved seven-tool API and exact response/error contracts, without adding production compatibility fallbacks.
- Fresh actual-client check: project interpreter (SDK 2.0.0), three client cases passed, including compact validation/expected errors and a four-call workflow.

## Task 3

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Preserved RED records for canonical project resolution and oversized response/paging cases; the recorded runtime resolution tests subsequently passed (2 passed). Fresh focused suite above passed, including exact Unicode paging reassembly, envelope bounds, overflow handling, canonical aliases/symlinks, and concurrent insertion coverage.
- Root cause (bugfix only): Project resolution now canonicalizes roots and rereads the winning row after a concurrent root-uniqueness conflict; bounded payload rendering adapts terminal text pages and explicitly errors for unpageable overflow.
- Fresh full suite: 529 passed, 3 deselected.

## Task 4

### Decisions made
- The condition for deleting `src/openmcp/backend_runner.py` was met: AST import inspection found no imports in `src` or `tests` after removing obsolete facade consumers.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Fresh focused run initially exposed six stale test assertions/doubles (notification URI expectations, old notifier helper, dependency message case, and the still-present facade module). After updating the permitted tests to the new job-ID contract and deleting the now-unimported runner, the six focused regressions passed.
- Root cause (bugfix only): Legacy test fixtures asserted removed URI/facade behavior, and one test expected lowercase text although the runtime correctly emits `Dependency`. Updated tests to assert the v2 behavior; no production metadata fallback was added.
- Fresh verification: `timeout --kill-after=5s 180s uv run --extra dev pytest tests/test_server.py tests/test_runtime.py tests/test_execution.py tests/test_smoke.py tests/test_notifications.py -q` -> exit 0, 225 passed; `timeout --kill-after=5s 180s uv run --extra dev pytest -q` -> exit 0, 529 passed, 3 deselected; `git diff --check` -> exit 0.
- SDK 2.0.0 actual-client command: `/home/ngosi/projects/openmcp/.venv/bin/python -m pytest tests/test_server.py::test_inprocess_client_receives_compact_json_errors tests/test_server.py::test_inprocess_client_sanitizes_unexpected_tool_exception tests/test_server.py::test_mcp_client_completes_v2_cycle_in_four_calls -q` -> exit 0, 3 passed. SDK 2.3.0 actual-client in-process memory transport script via `/home/ngosi/.local/share/pipx/venvs/openmcp/bin/python` -> exit 0; verified exact seven-tool listing, validation-error JSON and unknown-job JSON. Both commands were bounded by `timeout --kill-after=5s 180s`; no dependencies were installed.
- `git diff --check` reported no whitespace errors. README, pyproject, and editable OpenMCP uv.lock version metadata are updated to 2.0.0; lock dependencies were not re-resolved.

## Fix cycle 1 evidence (B1–B4)

### B1 — Strict raw argument types
- RED: `timeout --kill-after=5s 180s uv run --extra dev pytest tests/test_server.py::test_actual_client_rejects_sdk_coercions_before_dispatch tests/test_server.py::test_terminal_page_with_tight_metadata_advances_or_errors tests/test_runtime.py::test_resolve_project_preserves_alias_of_concurrent_canonical_winner -q` -> 3 failed; the Boolean timeout returned `unknown_job` instead of `invalid_request`, the terminal-page test exposed non-advancing/incorrect boundary behavior in its initial fixture, and the SQLite race stored alias `loser` instead of `winner`. The coordinator probe independently confirmed the exact non-advancing page defect under both SDKs. Boolean offset and numeric/string `fresh_session` cases were added to the strict-type regression.
- GREEN: actual-client strict-type regression passed in the fresh focused and SDK 2.0.0 runs. SDK 2.3.0 actual client verified all five malformed cases return `isError` invalid_request with non-retryable schema guidance and no job insertion.
- Root cause: SDK tool argument validation coerces primitive values before handler dispatch. Middleware now inspects the original call arguments and rejects wrong JSON primitive types before `call_next`.

### B2 — Paging progress at the response boundary
- RED: Coordinator's preserved actual-client diagnostic `/tmp/mcp-v2-phase4-spec-probes.py` reproduced empty result text with unchanged `next_offset=0` and remaining emoji under SDK 2.0.0 and 2.3.0. A focused regression now establishes metadata-only envelope fit while the next Unicode code point cannot fit.
- GREEN: the regression passes by returning bounded `response_too_large`; SDK 2.3.0 actual client confirms the same fixture returns an explicit error rather than a stalled page. Existing exact Unicode reassembly and full envelope bounds passed in both fresh full test commands.
- Root cause: page shrinking could halve a one-code-point candidate to zero and return an unchanged offset. It now errors if remaining text exists but one code point cannot fit; EOF remains an ordinary empty read.

### B3 — Alias-preserving concurrent resolution
- RED: `tests/test_runtime.py::test_resolve_project_preserves_alias_of_concurrent_canonical_winner` initially failed: the actual second SQLite connection's winner alias `winner` was returned/stored as `loser`.
- GREEN: the actual SQLite interleaving regression passed after the final canonical-root/alias check and insertion were serialized with `BEGIN IMMEDIATE`; both the returned row and stored alias remain `winner`. SDK 2.3.0 client-driven project resolution passed the same real-database race.
- Root cause: `Database.upsert_project` updates the alias for an existing canonical root and does not necessarily raise the assumed root uniqueness exception. The allowed runtime-only correction rechecks under a write transaction; database.py and scheduling remain unchanged.

### B4 — Contract evidence
- Added actual-client checks for all documented expected error families: unknown_project, invalid_path, alias_taken, unknown_job, unknown_profile, invalid_dependency, dependency_failed, invalid_state, config_invalid, daemon_stopping, invalid_request, response_too_large, and internal_error. Responses are pure compact JSON, bounded, privacy-scanned, and actionable; unexpected failures include a request ID and do not expose injected provider detail.
- Checked all seven tools' annotation hint tuples/titles and every parameter description. Successful outputs for all seven tools are recursively scanned for forbidden keys, contain exactly one text item, and have no structured duplicate. Error outputs from all tools receive the same recursive privacy and one-text checks.
- Actual submit, retry, and cancel overflow tests assert `response_too_large`, applied wording, retained root IDs, and persisted outcomes. Dependency listing checks `depends_on` and `waiting_on`; cancellation verifies the complete dependent ID list and persisted cancellation.
- Fresh focused original command: `timeout --kill-after=5s 180s uv run --extra dev pytest tests/test_server.py tests/test_runtime.py tests/test_execution.py tests/test_smoke.py tests/test_notifications.py -q` -> exit 0, 232 passed.
- Fresh full original command: `timeout --kill-after=5s 180s uv run --extra dev pytest -q` -> exit 0, 536 passed, 3 deselected.
- SDK 2.0.0 actual-client command: `timeout --kill-after=5s 180s /home/ngosi/projects/openmcp/.venv/bin/python -m pytest tests/test_server.py::test_actual_client_rejects_sdk_coercions_before_dispatch tests/test_server.py::test_terminal_page_with_tight_metadata_advances_or_errors tests/test_server.py::test_expected_runtime_error_families_are_compact_json tests/test_server.py::test_all_tool_success_payloads_are_private_and_single_text_content tests/test_server.py::test_submit_retry_cancel_overflow_reports_applied_root_ids tests/test_server.py::test_job_cancel_reports_complete_cancelled_dependents tests/test_server.py::test_inprocess_client_sanitizes_unexpected_tool_exception tests/test_runtime.py::test_resolve_project_preserves_alias_of_concurrent_canonical_winner -q` -> exit 0, 8 passed. SDK 2.3.0 bounded in-process actual-client command -> exit 0; verified exact tool set, strict invalid argument rejection/no mutation, actual SQLite alias-race resolution, advancing-or-explicit-error terminal paging, and request-ID sanitization.
- Final `git diff --check` -> exit 0. No dependency/environment changes, Git writes, daemon restart, or live service calls.
