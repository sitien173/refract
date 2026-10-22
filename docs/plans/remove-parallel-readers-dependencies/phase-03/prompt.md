## User Request
Remove parallel readers and job dependencies from Refract. Phase 2 removed readers. This phase removes job dependencies from the Python daemon and adds schema migration v14.

## Phase
No dependency code remains in the server, and existing databases migrate to v14 safely.

## Tasks
- task-1: In `server/src/refract/database.py`, add `_migrate_v13_to_v14` in one `BEGIN IMMEDIATE` transaction matching existing steps: for each queued job with any dependency whose state is not `succeeded`, set state `cancelled`, error `Dependency <id> was removed before completion`, `updated_at`, and insert a `job.cancelled` event with `{"error": ...}` matching `finish_job`; then `DROP TABLE IF EXISTS job_dependencies`; then `ALTER TABLE jobs DROP COLUMN access_mode` when present; then `PRAGMA user_version=14`. Set `_SCHEMA_VERSION = 14`, call the step from `_migrate`, and remove the column and table from `_create_schema`. Replace `create_job_with_dependencies` with a plain job insert; remove `dependencies_for_job` and `dependents_for_job`. Keep earlier migration steps working on old databases.
- task-2: In `scheduler.py`, remove `is_ready`, `reevaluate`, and `waiting_reason`. In `runtime.py`, remove `_dependencies_succeeded`, `_failed_dependency`, `_cancel_queued_dependent`, `_cancel_for_failed_parent`, `_cascade_unsuccessful`, `waiting_metadata`, and the startup repair loop; `_job_terminal` only calls `scheduler.complete(job_id, signal=False)`; `submit` drops `depends_on`; `cancel` drops `cancelled_dependents`; `retry` drops the `dependency_failed` check. Adjust `execution.py` only where the callback return value is consumed.
- task-3: In `models.py`, remove `depends_on`, `waiting_on`, `waiting_reason`, and `ActionResult.cancelled_dependents`. In `server.py`, remove the `depends_on` argument and validation, the `invalid_dependency` and `dependency_failed` error codes, `cancelled_dependents` from `job_cancel`, and dependency text from instructions and tool descriptions. In `dashboard.py`, remove dependency and waiting job fields. Update `server/README.md` to describe one-job-per-project FIFO admission and the reduced `job_submit` signature, and set its version line to `2.0.0`.
- task-4: Update tests. Delete dependency, cascade, waiting-metadata, `invalid_dependency`, `dependency_failed`, and `cancelled_dependents` tests. For mixed-purpose tests, remove only the dependency assertions and keep the rest; Phase 2 review failed for deleting mixed-purpose coverage. Add migration tests: a v13 database loses the column and table; a queued job with an unfinished dependency becomes `cancelled` with the error and one `job.cancelled` event; a queued job whose dependencies all succeeded stays `queued`; re-running migration is a no-op. Add a fresh-schema test. Add an MCP test that `job_submit` with `depends_on` returns `invalid_request` and summaries contain exactly `id, project_id, workflow, profile, state, context_key, attempts, created_at, updated_at`.

## Context
- Design: docs/plans/remove-parallel-readers-dependencies/DESIGN.md. Plan: PLAN.md Phase 3.
- Baseline after Phase 2: server pytest 555 passed, 3 deselected.
- Existing migration steps `_migrate_v10_to_v11` through `_migrate_v12_to_v13` in database.py show the transaction pattern.
- Startup recovery of interrupted jobs, the failover probe reset, and terminal-commit admission release via `complete(job_id, signal=False)` and `_terminal_waiters` must stay unchanged.

## Files
- Modify: server/src/refract/{database,scheduler,runtime,models,server,dashboard}.py
- Modify only if required: server/src/refract/execution.py
- Modify: server/README.md
- Modify: server/tests/{test_database,test_scheduler,test_execution,test_server,test_dashboard}.py
- Append only: docs/plans/remove-parallel-readers-dependencies/phase-03/notes.md and journal.md

## Done When
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest -q` passes.
- `rg -n 'depends_on|job_dependencies|cancelled_dependents|waiting_on|waiting_reason|dependency_failed|invalid_dependency|access_mode|is_ready|reevaluate' server/src/refract server/README.md --glob '!dashboard_static/**'` matches only `database.py` migration steps v11-to-v12 and v13-to-v14.
- `job_cancel` returns `{job:summary}` only.
- `cd /home/ngosi/projects/refract && git diff --check` passes.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
- Remove no error code other than the two named.
- Do not touch server/web, dashboard_static, or plugin; later phases own them.
- No Git writes. Do not read or edit secrets, `~/.refract`, the live daemon, or its database. Do not edit other files under `docs/plans/`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
