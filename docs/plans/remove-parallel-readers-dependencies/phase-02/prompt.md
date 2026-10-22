## User Request
Remove parallel readers and job dependencies from Refract. This phase removes the parallel-reader feature from the Python daemon. Job dependencies stay until Phase 3.

## Phase
No reader or access-class logic remains in server code; `max_project_readers` is an unsupported daemon key.

## Tasks
- task-1: In `server/src/refract/scheduler.py`, remove `AccessMode`, `max_project_readers`, `_writer_barrier`, `_position`, and `_Dispatch.access_mode`, `workflow`, `context_key`, `session_scope`. `_schedule` selects the first ready pending dispatch whose project has no active dispatch, bounded by global `max_jobs`, FIFO. `enqueue(job_id, project_id)` takes only those arguments. Remove reader, barrier, and session branches from `waiting_reason`. Update callers in `runtime.py`. Keep `complete(job_id, signal=False)`, `_terminal_waiters`, `cancel`, `wait`, `signal`, `close` semantics unchanged. Keep dependency readiness `is_ready` and `reevaluate`.
- task-2: Remove `derive_access_mode` from `planning.py` and `DriverRegistry.supports_verified_read_only` from `drivers.py`. In `database.py`, stop writing `access_mode` in the job insert and remove its validation and parameter; keep the column in schema and migrations. Remove `access_mode` from `models.py` job models and `dashboard.py` job output.
- task-3: Remove `max_project_readers` from `config.py` defaults, the supported `[daemon]` key set, and parsing; from `config_mutation.py`; from `models.py` settings models; and from `dashboard.py` settings GET output. Remove the `PUT /dashboard/api/settings` route and its update model.
- task-4: Update tests. Delete reader, barrier, session-scope, and `max_project_readers` tests only. Add scheduler tests: one job per project, FIFO within a project, cross-project overlap up to `max_jobs`, release at terminal commit without waiting for the notifier. Add a config test that `[daemon] max_project_readers = 2` raises `Unsupported daemon settings`. Add a dashboard test that `PUT /dashboard/api/settings` no longer succeeds.

## Context
- Design: docs/plans/remove-parallel-readers-dependencies/DESIGN.md. Plan: PLAN.md Phase 2.
- Baseline: server pytest 578 passed, 3 deselected.
- Use `rg` to find every reference before deleting.

## Files
- Modify: server/src/refract/{scheduler,planning,drivers,runtime,database,models,config,config_mutation,dashboard}.py
- Modify: server/tests/{test_scheduler,test_planning,test_execution,test_database,test_config,test_config_mutation,test_dashboard,test_server}.py
- Append only: docs/plans/remove-parallel-readers-dependencies/phase-02/notes.md and journal.md

## Done When
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest -q` passes.
- `rg -n 'access_mode|parallel_read|max_project_readers|derive_access_mode|supports_verified_read_only|session_scope' server/src/refract --glob '!dashboard_static/**'` matches only `database.py` schema and migration lines for the retained column.
- `cd /home/ngosi/projects/refract && git diff --check` passes.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
- Do not touch server/web or dashboard_static; Phase 4 owns UI.
- No Git writes. Do not read or edit secrets, `~/.refract`, the live daemon, or its database. Do not edit other files under `docs/plans/`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
