## User Request

Continue the approved remove-legacy-metadata plan. Execute Phase 2 only, then stop after fresh verification and independent review.

## Phase

Switch persistence and server responses atomically to canonical metadata and schema 16. Implement migration code and test only synthetic temporary databases. Live migration and deployment are excluded.

## Tasks

- task-1: Add schema-15 read-only preflight and transactional schema-16 migration. Add jobs.telemetry_state_json and initialize fresh databases at 16. Cover rollback, unsupported databases, repeated opens, connection cleanup, and preservation of historical data.
- task-2: Type JobResult.metadata and wire terminal writes, live merges, retry rollover, restart recovery, and accumulator loading through separated canonical snapshots and internal state. Remove legacy allowlists and generic metadata merges.
- task-3: Produce grouped execution/failure/retry facts and preserve dynamic routing behavior, including context overflow. Until Phase 3, read only model identity from the old driver usage bridge.
- task-4: Use the same canonical serializer for MCP and dashboard detail results. Update server tool descriptions and embedded guidance to grouped paths. Preserve required nulls, response limits, pending questions, and Unicode pagination.

## Context

Repository: /home/ngosi/.worktrees/refract/remove-legacy-metadata.
Branch: remove-legacy-metadata. Existing isolated worktree.
Read DESIGN.md and Phase 2 in PLAN.md under docs/plans/remove-legacy-metadata before edits.
Phase 1 is accepted at refs/plans/remove-legacy-metadata/phase-01/impl. Its pure converter and strict public types are in server/src/refract/result_metadata.py. It returns tuple[JobResultMetadata, TelemetryData | None]. Missing historical telemetry yields no internal state. Measurement quality defaults only when absent; explicit null is invalid. Retain these strict rules.

The grouped public root is execution, failure, retry, telemetry. Internal version, attribution, and completed_attempts never appear publicly. Persist bounded accumulator data separately. Preserve normalized values, source, quality, and original observed_at. Never infer normalized totals from raw counters, invent timestamps, or persist opaque routing tokens. Use current routing state for eligible next_target at read time. Canonical schema-16 reads/writes must not call the historical converter or accept aliases.

Schema policy: accept fresh initialization and upgrade schema 15 only. Unsupported versions, nonempty unversioned, malformed, or incomplete schemas remain no-write errors with cleaned-up connections. Read-only preflight validates structure and every historical metadata row before writable initialization. Malformed JSON, invalid recognized fields, or unsupported telemetry versions abort with bounded job/field diagnostics, never raw payloads. Deliberately drop known obsolete counters and unknown extensions. Validate all rows before mutation. DDL, all transformations, and user_version run within one transaction, with user_version last. Avoid helpers that implicitly commit. Roll back on any failure. Migration precedes scheduler startup and restart recovery. Reopening schema 16 performs no conversion/rewrite.

Keep all non-metadata operational data intact: job IDs, states, text, errors, timestamps, sessions, plans, history, and streams. Preserve retry/failure precedence, cancellation, pagination, response limits, terminal telemetry retention, bounded reconciliation, and restart/retry accounting without double-counting. Runtime and dashboard expose identical canonical key sets and null semantics.

Baseline: exact accepted Phase 1 product checkpoint passed 936 Python tests, 15 live tests deselected, plus both plugin checks. Fresh phase guidance selects implement and review profiles. Plan artifacts are tracked. Existing frontend dependency vulnerabilities are outside scope.

## Files

Allowed product/test modifications only:
- server/src/refract/result_metadata.py
- server/src/refract/models.py
- server/src/refract/telemetry.py
- server/src/refract/database.py
- server/src/refract/execution.py
- server/src/refract/runtime.py
- server/src/refract/server.py
- server/src/refract/dashboard.py
- server/tests/test_result_metadata.py
- server/tests/test_telemetry.py
- server/tests/test_database.py
- server/tests/test_database_atomicity.py
- server/tests/test_execution.py
- server/tests/test_runtime.py
- server/tests/test_server.py
- server/tests/test_dashboard.py
- server/tests/test_mcp_schema_contract.py
- server/tests/test_retention.py, coordinator-approved exception for canonical fixtures and explicit fixture timestamps only

Worker evidence:
- docs/plans/remove-legacy-metadata/phase-02/notes.md
- docs/plans/remove-legacy-metadata/phase-02/journal.md

Keep changes within this list. If another path is required, ask before changing it. Coordinator owns handover, plan, design, phase prompt, Git, anchors, and acceptance. Separate telemetry/retry-policy historical plans are out of scope.

## Done When

- All Phase 2 Acceptance Criteria and Reviewer Checklist items in PLAN.md are met.
- Tests precede changed production behavior. Record behavioral RED failure lines and GREEN outcomes per task, not import failures.
- Migration fixtures use genuine synthetic schema-15 layouts, not schema-16 schemas with changed user_version.
- Failed migrations preserve all schema and row data; reopening schema 16 never converts.
- Typed canonical results cover running, terminal, cancelled, interrupted, and retried jobs.
- MCP/dashboard output has identical exact keys and null semantics without internal fields or legacy aliases.
- Retry tokens are read-time only. Accumulator state survives retry/restart.
- Existing API envelope, execution outcomes, streams, and pagination remain intact.
- Run from repository root: (cd server && uv run --extra dev python -m pytest -m 'not live')
- Run from repository root: bash plugin/tests/test-session-start.sh
- Run from repository root: bash plugin/tests/test-contracts.sh

## Rules

Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
- TDD: /home/ngosi/projects/refract/plugin/skills/test-driven-development/SKILL.md

Operate only in the named worktree. No Git mutations. No real operator database or state-directory access, daemon changes/restarts, deployment, network/live probes, or Phase 3/4 implementation. Keep backend usage bridge and dashboard clients/docs/assets unchanged until their planned phases. Test fixtures may update within declared paths. Preserve pre-existing changes.

Use refract ask for unresolved decisions, without printing its injected credentials. If unavailable, return BLOCKED. Report every touched path. Append notes per task and full ERP to the journal without replacing earlier evidence.

## Authorized Targeted Correction Batch

The user answered `yes` to a targeted correction batch after current-tree tests passed but specification failed. Correct these findings without expanding the approved behavior:

1. Enforce read-time-only retry tokens in every canonical persistence path. Coordinator reproduced finish_job persisting retry.next_target from valid canonical input. Clear or reject tokens at the persistence boundary while preserving dynamic routing.
2. Complete read-only structural validation for supported schema 15 and 16, including support-table columns and required integrity constraints/indexes. Use faithful historical fixtures. Reject malformed structures before writable open. Preserve rollback and no-write/cleanup guarantees.
3. Remove silent repair of malformed canonical metadata/internal accounting state in normal schema-16 read/write/recovery paths. Invalid recognized canonical data must fail its boundary, not become an unavailable/default snapshot. Preserve best-effort rejection of invalid external collector observations without changing execution outcomes.
4. Verify and correct terminal/live telemetry merging so newer valid values and original provenance survive. Preserve independent accounting state through retry/restart without duplicate consumption. Add exact MCP/dashboard key/null parity and required pagination/routing regressions where absent.
5. Repair missing test-first evidence for Phase 2 behavior. Notes admit tasks 3 and 4 lacked behavioral RED. Discard only untested Phase 2 behavior and reconstruct with failing behavioral tests before the minimal implementation. Keep accepted Phase 1 code and valid task-1/task-2 evidence. Newly introduced mapping-like model protocols are not required by the strict typed contract; remove newly added compatibility scaffolding if its only purpose is to avoid updating typed callers/tests. Report any unavoidable dependency before expanding the file set.

Baseline diagnostic passed 946 Python tests and both plugin checks. This does not waive missing criteria or TDD. Append exact commands and failure lines to notes, preserve all previous evidence, then run all three unmodified Verification Checks.

## Third Targeted Correction Authorization

The user answered `yes` after the second correction batch remained blocked. This authorizes one additional targeted correction batch, fresh validation, and independent review only after specification passes. No automatic continuation or scope expansion is authorized.

Correct these reproduced defects test-first, preserving all existing partial work and earlier evidence:

1. Terminal accounting retention: in a synthetic temporary database, merge total_input_tokens=10, source=response, quality=reported, observed_at=2026-10-27T00:00:00Z. Finish with canonical terminal total_input_tokens=18 and observed_at=2026-10-27T00:00:01Z. Current terminal public value is 18, but reset_retry reduces it to 10. _finish merges the public snapshot without updating telemetry_state_json. Persist consistent bounded internal accounting transactionally with terminal metadata; reuse the existing accumulator, preserve provenance and timestamps, and prove retry plus reopen/restart retain the newer measurement without double-counting.
2. Output filtering bypass: _public_data({"metadata": {"backend": "synthetic-private-backend", "execution": {"model": "allowed-model"}}}) exposes backend because every metadata key bypasses recursive filtering. Restore forbidden-field filtering without stripping the intentionally public canonical execution.model. Limit any exception to a validated canonical boundary, not arbitrary metadata dictionaries. Add regression coverage for nested arbitrary metadata, exact canonical shape/nulls, and MCP/dashboard parity.
3. Strict terminal response boundary: _page_terminal_result catches invalid canonical metadata and substitutes defaults. Reject invalid canonical input at the boundary instead of silently repairing it. Add behavioral tests for malformed canonical terminal metadata and valid unavailable snapshots, preserving pagination and response-size behavior.

Coordinator full verification selected 959 Python tests but timed out after 300 seconds with exit 124 during test_execution.py and no final count. Both plugin checks passed. Investigate the timeout using bounded diagnostics and retained logs; do not infer test failure or success from a timeout. Run all three unmodified phase verification commands after fixes, retain final output/counts, and leave no test processes behind. Do not weaken tests, fabricate observations, restore mapping shims, or change unrelated behavior. Append exact behavioral RED/GREEN evidence and ERP, never overwrite earlier records.

## Authorized Independent-Review Accounting Correction

The user answered `yes` to a targeted accounting correction and re-review after independent review `9fab1071-2555-438e-a565-93c3ad06a03f` returned FAIL. Correct this High finding only, preserving the validated checkpoint `3526883ff1fcc4c474c92df1d1568f4071ffe31b` and prior evidence:

- database.py:488–491 reconstructs terminal TelemetryData from the public projection, which has no attribution and defaults to attempt 1. merge_telemetry then ignores terminal measurements for stored attempt 2+ even when timestamps are newer.
- Reviewer reproduced with synthetic in-memory SQLite: attempt-1 input 10; finish and reset_retry; persist attempt-2 cumulative input 20; finish with canonical terminal input 28 and newer timestamp; terminal public input stays 20 instead of 28.
- Preserve stored attribution and completed-attempt accounting when incorporating canonical terminal measurements. Never infer accounting identity from a public projection. Reuse the existing bounded accumulator/merger, not a second accounting algorithm.
- Add behavioral RED/GREEN regressions for terminal measurements on attempt 2 and later, subsequent retry/reopen, unchanged provenance/timestamps, and no double-counting. Cover accounting state as well as public output, and retain existing first-attempt behavior.
- Target files database.py and test_database.py; telemetry.py and test_telemetry.py are allowed only if necessary for the same finding. Append phase notes/journal evidence and exact modified paths. No unrelated changes or scope expansion.
- Run all three exact phase verification checks and retain logs/counts. Prior coordinator checkpoint passed 962 Python tests, 15 deselected, and both plugin checks; that is not evidence for the corrected tree.
- This authorization covers one correction batch and independent re-review after verification. Another incomplete result requires user instructions. No Git mutations, real state access, live/daemon/deployment operations, or Phase 3/4.

## Response Format

Return the ERP # EXTERNAL RESPONSE block and matching status line. Coordinator owns independent review and final acceptance.
