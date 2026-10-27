<!-- refract-shared-version: 2.0.0 -->

# Phase 2 Decision Notes

## Task 1

### Decisions made
- Fresh databases initialize at schema 16; schema-15 conversion adds `telemetry_state_json` and precomputes canonical row payloads before the transaction.

### Spec deviations
- Structural preflight checks jobs columns and required table names, but not every expected column/index/constraint in every table. Rollback-on-DDL/update failure is not covered. The synthetic v15 fixture has core operational tables but does not fully reproduce every real v15 table definition.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Complete structural schema validation, full genuine-v15 fixture fidelity, transaction rollback coverage and preservation assertions.

### Test evidence
- RED: fresh schema test reported 15 instead of required 16 (2 parameterized failures).
- GREEN: focused fresh schema tests -> 2 passed.
- RED: synthetic v15 conversion expected grouped `execution`, observed `KeyError: 'execution'`.
- RED: after discarding initial untested migration behavior, malformed-row preflight expected a ValueError but did not raise.
- GREEN: focused migration/preflight/reopen/fresh tests -> 5 passed; database module -> 55 passed before later typed metadata changes.
- Current database module regressed after transition: 6 failed, 49 passed (legacy-shaped assertions/fixtures require canonical updates).

## Task 2

### Decisions made
- Typed `JobResult.metadata` uses Phase 1 `JobResultMetadata`. Internal accumulator data is read/written via the separate state column for live merges and retry reset.

### Spec deviations
- Producer and persistence changes are incomplete: terminal telemetry merge behavior, restart accounting and all legacy fixtures are not yet validated.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Complete terminal merge semantics, recovery and retry accounting; update synthetic tests to assert canonical objects rather than dictionary aliases.

### Test evidence
- RED: focused JobResult test failed because `metadata` was `{}` instead of a `JobResultMetadata`.
- GREEN: focused typed JobResult test passed after model typing.
- Regression: full database suite after typed switch reported 6 failures, 49 passed; full server suite timed out with multiple failures visible in dashboard/database/execution.

## Task 3

### Decisions made
- Updated execution metadata production to emit grouped fields and preserve model identity from the old usage bridge; runtime routing projection now writes `retry.next_target` and `retry.retryable`.

### Spec deviations
- These behavior changes were not preceded by a task-specific behavioral RED. The grouped producer/runtime changes and context-overflow/routing behavior are not complete or adequately covered.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Rework test-first, retain routing/failure precedence, and add grouped execution tests including context overflow, replay blocking and changed target health.

### Test evidence
- No valid task-level RED→GREEN evidence established. Full server test run timed out with execution test failures visible; see final verification record.

## Task 4

### Decisions made
- Updated server tool descriptions and embedded coordinator guidance to reference `metadata.retry.next_target` and `metadata.retry.retryable`; terminal response now serializes typed metadata explicitly.

### Spec deviations
- MCP/dashboard shared canonical serializer, exact key/null parity tests, and full response/pending-question/pagination regression verification are incomplete.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Complete shared projection and server/dashboard contract tests, then rerun full server suite.

### Test evidence
- No task-specific behavioral RED→GREEN evidence established.

## Phase verification

- `(cd server && uv run --extra dev python -m pytest -m 'not live')`: timed out after 1200 seconds, at 34% progress; output showed failures in dashboard, database, and execution. 955 collected, 15 live deselected, 940 selected; no final count.
- `bash plugin/tests/test-session-start.sh`: passed.
- `bash plugin/tests/test-contracts.sh`: passed.
- Phase is not complete and no checkpoint was made.

## ERP Recovery Evidence (2026-10-27)

This entry records inspection only; no product/test implementation or test execution was performed in the ERP recovery job.

- The terminal prior job `a2102bf3-b8d5-4f01-bf6f-2a5f3b107acf` returned only `Running execution tests. Waiting for completion.` Its actual test command, process ID, and log path are not recorded in the repository or available from the inspected artifacts.
- Process inspection found no active `pytest`, `python -m pytest`, plugin test script, or `uv run ... pytest` process. Therefore no test left by that job is currently running; there is no current test PID to report. This does not establish whether the prior job's test process terminated normally.
- Prior available database evidence: `/tmp/refract-metadata-phase02-partial.log` reports 22 failed, 30 passed; `/tmp/refract-metadata-phase02-continuation1.log` reports 55 passed (before later typed metadata changes). `/tmp/pi-bash-8bb381f7581c50ef.log` also records the earlier 22 failed, 30 passed database run.
- The earlier full command `(cd server && uv run --extra dev python -m pytest -m 'not live')` was observed timing out at 1200 seconds around 34% progress with dashboard/database/execution failures visible; it has no final count. No complete-tree full-suite result exists. Current-tree test results are unavailable/not verified.
- Earlier exact plugin checks `bash plugin/tests/test-session-start.sh` and `bash plugin/tests/test-contracts.sh` were reported passed. They were not rerun during recovery, and do not verify later test changes.
- Recovery inspection ran `git diff --check`, which passed; HEAD remains `bc2250be5fd3b8ab7eae9aa65524b51c423d7de3`. No tests were launched during recovery.
- Remaining gaps remain all Phase 2 acceptance items: complete schema-15 structural preflight and faithful fixture, rollback/atomicity/preservation/no-write/cleanup proof; canonical typed persistence and terminal/live/retry/restart accumulator accounting; grouped failure/retry/context-overflow/routing proof; identical MCP/dashboard serializer and exact parity/null/pagination/response-bound coverage; valid task-level RED/GREEN evidence; and current-tree completion of all three required checks.

## Authorized Correction Batch (2026-10-27)

### Task 1

### Decisions made
- Expanded read-only structure checks to compare required columns for each core/support table and require named indexes and foreign-key relationships. Updated the synthetic schema-15 fixture's support-table foreign keys to match the historical DDL.

### Spec deviations
- Integrity checks do not yet validate index definitions or full table constraints; the fixture is improved but not proven to reproduce every historical definition. Structural correction was implemented before its new support-column regression was run, so that regression is not credited as test-first RED evidence.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Complete constraint/index-definition validation and rollback/preservation coverage.

### Test evidence
- RED: `cd server && uv run --extra dev python -m pytest tests/test_database.py::test_finish_job_never_persists_retry_routing_token -q` -> `AssertionError: assert 'nt_synthetic' is None`.
- GREEN: after token clearing, `cd server && uv run --extra dev python -m pytest tests/test_database.py -q` -> 61 passed.

### Task 2

### Decisions made
- Removed model mapping-like methods from `StrictModel` and `Measurement`; malformed persisted canonical metadata/internal telemetry now propagates validation errors instead of being defaulted. External invalid collector observations still return without changing execution.

### Spec deviations
- Finishing code also uses telemetry timestamp-aware merge, but incoming terminal telemetry accounting/provenance and end-to-end retry/restart behavior are not fully verified. Some updated callers/tests still assume model subscription and fail after removing compatibility methods.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Convert all typed callers/tests to attributes or explicit serialization; add malformed internal-state and exact terminal timestamp/provenance regressions and verify retry/restart deduplication.

### Test evidence
- RED: `cd server && uv run --extra dev python -m pytest tests/test_database.py::test_finish_job_rejects_malformed_persisted_canonical_metadata -q` -> expected ValueError did not raise.
- GREEN: focused token/corruption/migration tests -> 3 passed; complete database module -> 61 passed.
- Refactor regression: execution module showed subscription TypeErrors after deliberately removing the mapping-like compatibility methods.

### Task 3

### Decisions made
- none

### Spec deviations
- Existing task-3 production changes were not reconstructed under test-first discipline; grouped failure/context-overflow/routing behavior remains unverified. No further production redesign was performed.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Reconstruct the behavior from focused failing tests before accepting it; cover context overflow, replay blocking, changed target health, and retry/restart accounting.

### Test evidence
- No new valid task-specific behavioral RED→GREEN evidence established.

### Task 4

### Decisions made
- none

### Spec deviations
- Exact MCP/dashboard serialization and pagination behavior remain incompletely verified; prior task-4 behavior lacks recovered RED evidence.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Add test-first shared serializer/key/null parity and required pending-question, response-bound, and Unicode pagination coverage.

### Test evidence
- No new valid task-specific behavioral RED→GREEN evidence established.

### Correction batch verification

- Exact Python check `(cd server && uv run --extra dev python -m pytest -m 'not live')`: timed out at 1200 seconds; 964 collected, 15 live deselected, 949 selected. Output showed execution failures after 35% progress. No final count.
- Exact plugin checks: `bash plugin/tests/test-session-start.sh` passed; `bash plugin/tests/test-contracts.sh` passed.
- `git diff --check`: passed.
- Correction batch is BLOCKED. Full Python verification and required test-first evidence are outstanding; do not claim acceptance.

## Authorized Correction Batch 2 (2026-10-27)

### Task 1 — Schema preflight and migration
- Added exact index-column/uniqueness checks; table primary-key, project uniqueness, foreign-key target/action, and required NOT NULL checks. The synthetic schema-15 fixture has the full support-table DDL. Existing migration-preservation coverage asserts events, context sessions/turns, target health, stream rows, and job/project data. Added index-definition, nullable-column, and unique-constraint malformed-structure tests plus failure-after-DDL/update rollback coverage.
- RED: wrong index regression -> `Failed: DID NOT RAISE <class 'ValueError'>`; nullable required column regression -> same intended missing NOT NULL rejection. GREEN: database-focused module (with atomicity, metadata, retention) -> 288 passed.
- Rollback regression uses an aborting trigger and proves `user_version=15`, no telemetry column, and unchanged legacy row values after failure.

### Task 2 — Strict metadata, telemetry retention, retry/restart
- Kept mapping emulation removed. Converted typed metadata assertions/callers in execution and retention tests to attributes or explicit `model_dump`.
- RED: `test_terminal_merge_keeps_newer_measurement_and_original_provenance` against terminal overwrite behavior asserted newer terminal value 18 but observed live value 10 with stale provenance. GREEN after timestamp-aware merge: focused test passed.
- RED: corrupt accumulator regression against default-repair behavior failed because ValueError did not raise. GREEN after strict boundaries: focused test passed; invalid external observation remains ignored without modifying stored metadata.
- RED: schema-15 normalized telemetry retry regression expected cumulative 41, observed 10 after rollover. GREEN after accumulator fix: migrated normalized values, original provenance/timestamp, completed accounting, reopen, and retry all survive (rollover aggregate 41, not duplicated).
- RED: typed caller run initially failed at `set(second.result.metadata)` with `TypeError: unhashable type: 'ExecutionMetadata'`. GREEN: all 125 execution tests pass after typed assertions/callers were corrected.

### Task 3 — Grouped producer and routing
- Added a producer regression for grouped failure metadata and absence of flat counters.
- RED: deliberately restored flat producer shape; regression failed with flat keys (`failure_kind`, `input_tokens`, etc.) instead of the required grouped root. GREEN after canonical grouped producer restored: focused producer/context-overflow tests -> 2 passed.
- RED: context-overflow read-time routing expected next-target token but got null. GREEN after projecting context-overflow eligible targets at read time, while preserving `retryable=True` when no target is available; focused test passed. Runtime/server/dashboard routing regressions including changed health passed within focused suites.

### Task 4 — Shared dashboard/MCP projection
- Dashboard details now use `runtime.live_result_metadata`, the same canonical projection as MCP, including read-time route tokens.
- RED: dashboard/MCP route parity differed (`dashboard next_target=None`, MCP `nt_...`). GREEN after shared projection: exact route parity test passed. Existing dashboard/server coverage for nulls, pending questions, response limits, and Unicode pagination was included in focused/full checks.

### Verification, batch 2
- Focused `(cd server && uv run --extra dev python -m pytest tests/test_database.py tests/test_database_atomicity.py tests/test_result_metadata.py tests/test_retention.py -xq)`: 288 passed.
- Focused `(cd server && uv run --extra dev python -m pytest tests/test_telemetry.py -xq)`: 23 passed.
- Focused `(cd server && uv run --extra dev python -m pytest tests/test_runtime.py tests/test_server.py tests/test_dashboard.py -xq)`: 154 passed.
- Focused `(cd server && uv run --extra dev python -m pytest tests/test_execution.py -xq)`: 125 passed.
- Exact full check `(cd server && uv run --extra dev python -m pytest -m 'not live')`: 959 passed, 15 deselected in 154.84s. Log: `/tmp/refract-metadata-phase02-correction2-python.log`.
- Exact `bash plugin/tests/test-session-start.sh`: passed. Log: `/tmp/refract-metadata-phase02-correction2-session.log`.
- Exact `bash plugin/tests/test-contracts.sh`: passed. Log: `/tmp/refract-metadata-phase02-correction2-contracts.log`.
- `git diff --check`: passed. HEAD remains `bc2250be5fd3b8ab7eae9aa65524b51c423d7de3`; no Git mutations.
- These checks pass, but coordinator specification validation and independent review remain required; worker does not claim final plan acceptance.

## Authorized Correction Batch 3 (2026-10-27)

### Task 1 — Terminal telemetry accounting retention

#### Decisions made
- Persist the timestamp-aware merged internal `TelemetryData` snapshot alongside terminal canonical metadata in the same existing jobs UPDATE/transaction. When terminal metadata provides telemetry but no earlier internal snapshot exists, initialize the separated internal state from that validated canonical snapshot.

#### Spec deviations
- none

#### Tradeoffs accepted
- none

#### Assumptions
- The existing bounded `TelemetryData` representation remains the sole internal accumulator snapshot; no second accounting algorithm or representation was introduced.

#### Follow-ups for human
- none

#### Test evidence
- RED: `(cd server && uv run --extra dev python -m pytest tests/test_database.py::test_terminal_telemetry_accounting_survives_retry_and_reopen -q)` -> after `reset_retry`, expected `(18, response, reported, 2026-10-27T00:00:01Z)`, observed `(10, response, reported, 2026-10-27T00:00:00Z)`.
- GREEN: same focused command -> 1 passed. Verifies retry rollover, persisted completed total 18, close/reopen retention, second rollover without double-counting, and original terminal observation time/provenance.

### Task 2 — Recursive output filtering

#### Decisions made
- `_public_data` validates the exact `metadata` value as strict `JobResultMetadata` before allowing public `execution.model`; invalid/arbitrary metadata falls back to recursive forbidden-key filtering. No arbitrary metadata dictionary bypass remains.

#### Spec deviations
- none

#### Tradeoffs accepted
- none

#### Assumptions
- The strict canonical model is the authorized exception boundary for the intentionally public execution model field.

#### Follow-ups for human
- none

#### Test evidence
- RED: `(cd server && uv run --extra dev python -m pytest tests/test_server.py::test_public_data_filters_unvalidated_metadata_and_preserves_canonical_execution_model -q)` -> assertion showed `synthetic-private-backend` and `unvalidated-private-model` leaked unchanged.
- GREEN: same focused command -> 1 passed. Also asserts canonical exact root keys, required `failure: null`, and explicit unavailable telemetry.

### Task 3 — Strict terminal result boundary

#### Decisions made
- Terminal paging now validates supplied/stored metadata directly as canonical metadata and propagates validation failure instead of substituting defaults.

#### Spec deviations
- none

#### Tradeoffs accepted
- none

#### Assumptions
- Invalid terminal canonical state is a boundary error; valid default unavailable metadata continues to serialize explicitly.

#### Follow-ups for human
- none

#### Test evidence
- RED: `(cd server && uv run --extra dev python -m pytest tests/test_server.py::test_terminal_page_rejects_malformed_canonical_metadata_and_keeps_unavailable_shape -q)` -> expected ValueError did not raise.
- GREEN: same focused command -> 1 passed; malformed aliases/extras fail, valid unavailable snapshot preserves exact null fields.

### Timeout investigation and verification — batch 3

- Coordinator log `/tmp/refract-metadata-phase02-coordinator-final-python.log` shows 959 selected (15 deselected), progress stopped in `tests/test_execution.py` at 45%; coordinator reports exit 124 at the 300-second wall limit. It contains no test assertion failure or final count.
- Bounded isolated diagnostic `(cd server && timeout 220 uv run --extra dev python -m pytest tests/test_execution.py -xq)` completed 125 passed in 207.38s; log `/tmp/refract-metadata-phase02-correction3-execution-diagnostic.log`.
- Fresh complete exact Python verification then completed successfully in 244.42s, below 300s: 962 passed, 15 deselected. This establishes the prior result was a wall-time timeout, not a reproduced test failure; the evidence does not identify a definitive cause for the earlier slower run, so none is inferred.
- Exact `(cd server && uv run --extra dev python -m pytest -m 'not live')`: 962 passed, 15 deselected in 244.42s. Log: `/tmp/refract-metadata-phase02-correction3-python.log`.
- Exact `bash plugin/tests/test-session-start.sh`: passed. Log: `/tmp/refract-metadata-phase02-correction3-session.log`.
- Exact `bash plugin/tests/test-contracts.sh`: passed. Log: `/tmp/refract-metadata-phase02-correction3-contracts.log`.
- Focused checks: database plus both terminal response tests -> 71 passed; the isolated execution diagnostic above passed; individual RED/GREEN tests are recorded above.
- `git diff --check`: passed. HEAD remains `bc2250be5fd3b8ab7eae9aa65524b51c423d7de3`; no Git mutations. A separate active test process from another worktree was observed and left untouched; no test process from this batch remains.

## Authorized Independent-Review Accounting Correction (2026-10-27)

### Decisions made
- The public terminal telemetry snapshot omits accounting attribution, so never merge it using its default attempt 1. Copy the stored internal attribution and completed-attempt aggregate onto the validated terminal telemetry snapshot before passing both snapshots to the existing timestamp-aware `merge_telemetry`. Persist that merged internal state as before. This retains identity without inferring it from public metadata or adding an accounting algorithm.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Canonical terminal measurements update metric values/provenance while accounting identity and completed totals remain owned by the stored internal state.

### Follow-ups for human
- none

### Test evidence
- RED: `(cd server && uv run --extra dev python -m pytest tests/test_database.py::test_later_attempt_terminal_measurement_preserves_accounting_identity_retry_and_reopen -q)` -> after attempt-2 terminal input 28 at `2026-10-27T00:00:03Z` and retry, observed 20 at `2026-10-27T00:00:02Z`.
- GREEN: same focused test -> 1 passed. Regression now exercises terminal corrections on attempts 2 and 3, stored attribution/completed totals, retry rollover, close/reopen, original source/quality/timestamps, and no double-counting.
- Existing first-attempt terminal retention also passed: focused terminal trio -> 3 passed.

### Verification
- Focused `(cd server && uv run --extra dev python -m pytest tests/test_database.py -xq)`: 70 passed. Log: `/tmp/refract-metadata-phase02-review-correction-database.log`.
- Exact `(cd server && uv run --extra dev python -m pytest -m 'not live')`: 963 passed, 15 deselected in 154.69s. Log: `/tmp/refract-metadata-phase02-review-correction-python.log`.
- Exact `bash plugin/tests/test-session-start.sh`: passed. Log: `/tmp/refract-metadata-phase02-review-correction-session.log`.
- Exact `bash plugin/tests/test-contracts.sh`: passed. Log: `/tmp/refract-metadata-phase02-review-correction-contracts.log`.
- `git diff --check`: passed. HEAD remains review checkpoint `3526883ff1fcc4c474c92df1d1568f4071ffe31b`; no Git mutations, and no test process from this batch remains.
