## Original User Request
Finalize the `git-agnostic-runtime` folder plan.

## Phase
Migrate schema v5 to v6 and remove all Git fields.

## Tasks
- task-1: Create the trimmed v6 schema and portable v5 rebuild migration.
- task-2: Rewrite older legacy normalization to create v6 directly.
- task-3: Remove Git fields from database methods and row readers.
- task-4: Remove Git fields from public models and runtime callers.
- task-5: Update migration, database, execution, server, and dashboard tests.
- task-6: Remove Git fields from dashboard types and views.
- task-7: Rebuild committed dashboard assets and update public documentation.

## Context
Preserve every project and job row during migration. Keep `jobs.result_text`.
Do not change scheduler, target execution, drivers, or backend contracts.

## Files
- `src/openmcp/database.py`
- `src/openmcp/models.py`
- `src/openmcp/runtime.py`
- `src/openmcp/execution.py`
- `tests/test_database.py`
- `tests/test_execution.py`
- `tests/test_server.py`
- `tests/test_dashboard.py`
- `web/src/`
- `src/openmcp/dashboard_static/`
- `README.md`

## Done When
- Fresh databases use schema version 6.
- Populated v5 databases migrate with all rows preserved.
- Migration failures roll back schema, rows, and version.
- Reopening v6 performs no migration.
- Dropped columns are absent from both tables.
- Public project and job models expose no Git fields.
- Dashboard types and views expose no Git fields.
- `uv run python -m pytest`
- `npm --prefix web test -- --run`
- `npm --prefix web run build`
- `tgrep -n "base_commit|result_commit|head_commit|commit_message|\\.writes|inspect_repository|repositories" src/openmcp -g '*.py' || echo NONE`
- `tgrep -n "base_commit|result_commit|head_commit|commit_message|result\\.commit|\\.clean" web/src -g '*.{ts,tsx}' || echo NONE`
- `tgrep -n "base_commit|result_commit|head_commit|commit_message" README.md src/openmcp/dashboard_static || echo NONE`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.
Use table rebuilds. Do not use `ALTER TABLE DROP COLUMN`.
Disable foreign keys before the transaction and restore them in `finally`.
Use individual statements inside `BEGIN IMMEDIATE`; never use `executescript`
inside the rebuild. Drop child before parent. Recreate `jobs_state_idx`. Run
`foreign_key_check` and `integrity_check`. Preserve events, contexts, turns,
target health, and all surviving project and job values. Assert exact column
sets and no temporary v6 tables.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
