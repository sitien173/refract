## User Request
Implement the approved worker-job-telemetry plan. Expose live worker context snapshots and final per-job token totals for Agy, Codex, Claude Code, and Pi, without replacing transports.

## Phase
Phase 1: Durable telemetry contract and read APIs. Synthetic observations survive persistence and API reads independently from transcripts.

## Read First
- Design: /home/ngosi/projects/refract/docs/plans/worker-job-telemetry/DESIGN.md
- Plan: /home/ngosi/projects/refract/docs/plans/worker-job-telemetry/PLAN.md (read "Shared Contract and Boundaries" and "Phase 1" fully)

## Tasks
- task-1: Add failing tests and the shared typed telemetry contract in `server/src/refract/telemetry.py`. Implement validation, identity-based reconciliation, nullable measurements, provenance (`value`, `source`, `quality`, `observed_at`), and completeness. Cover response snapshots, consumption, and context invalidation separately.
- task-2: Add transactional telemetry merges into `jobs.result_metadata_json`. Preserve unrelated fields, existing v15 records, completed-attempt aggregates, and observed totals across job retry. Protect terminal metadata against stale observations and partial overwrite.
- task-3: Route `telemetry.updated` through execution before transcript recording and quota checks. Assign actual persisted attempt and invocation identities, including session-recovery invocations. Retain observed partial telemetry on cancellation, failure, timeout, and daemon interruption.
- task-4: Expose additive telemetry through runtime (`live_result_metadata`), MCP `job_wait`, and dashboard job reads. Keep result paging, routing tokens, failure metadata, response bounds, and historical metadata behavior intact.

## Context
- Telemetry lives in one versioned `telemetry` object under `result.metadata`.
- Primary measurements: `context_remaining_percent`, `context_window_size`, `context_used_tokens`, `total_input_tokens`, `total_output_tokens`. Also `cache_read_tokens`, `cache_write_tokens`.
- `quality` is `reported`, `derived`, `estimated`, or `unavailable`. Unsupported values are null. Zero is valid. Reject booleans, negatives, malformed types, non-finite numbers.
- Keep SQLite schema version 15. No new table, no migration.
- Legacy top-level metadata keys keep backend-native meaning.
- Backend adapters are out of scope for this phase; use synthetic observations in tests.

## Files
- Create: `server/src/refract/telemetry.py`
- Create: `server/tests/test_telemetry.py`
- Modify: `server/src/refract/models.py`
- Modify: `server/src/refract/database.py`
- Modify: `server/src/refract/drivers.py`
- Modify: `server/src/refract/execution.py`
- Modify: `server/src/refract/runtime.py`
- Modify: `server/src/refract/server.py`
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/tests/test_database.py`
- Modify: `server/tests/test_database_atomicity.py`
- Modify: `server/tests/test_execution.py`
- Modify: `server/tests/test_runtime.py`
- Modify: `server/tests/test_server.py`
- Modify: `server/tests/test_dashboard.py`
- Modify: `server/tests/test_mcp_schema_contract.py`
- Write: `docs/plans/worker-job-telemetry/phase-01/notes.md`

## Done When
- All five primary measurements accept reported zero and unavailable null.
- Invalid numeric inputs cannot create invalid metadata.
- Duplicate and stale observations cannot inflate consumption.
- Missing contributions produce explicit incomplete totals.
- A running job read returns persisted synthetic telemetry.
- Terminal and paginated waits retain identical telemetry.
- Database reopen retains snapshots without a schema upgrade.
- Transcript quota exhaustion and pruning do not erase telemetry.
- Retry preserves prior consumption without treating it as current context.
- Internal session recovery receives a separate invocation identity.
- Cancellation and failure preserve last observed partial measurements.
- Historical jobs with empty metadata remain valid.
- `cd server && uv run pytest` passes.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md

- Write regression tests before production changes.
- Do not commit, stash, reset, or run any Git write command. Coordinator owns Git.
- Do not edit PLAN.md, DESIGN.md, .handover.md, or journal.md.
- Do not modify credentials or global CLI configuration. Do not launch live model requests.
- Do not replace execution transports with RPC.
- Touch only the listed files. Report any needed extra path as a clarification.
- Never put raw payloads, session paths, prompts, or credentials in telemetry.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
