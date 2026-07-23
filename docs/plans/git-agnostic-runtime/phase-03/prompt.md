## Original User Request
Finalize the `git-agnostic-runtime` folder plan.

## Phase
Migrate schema v5 to v6 and remove all Git fields.

## Tasks
- task-1: Create the trimmed v6 schema and portable v5 rebuild migration.
- task-2: Remove Git fields from database methods and row readers.
- task-3: Remove Git fields from public models and runtime callers.
- task-4: Update migration, database, execution, server, and dashboard tests.
- task-5: Remove Git fields from dashboard types and views.
- task-6: Rebuild committed dashboard assets and update public documentation.

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
- Dropped columns are absent from both tables.
- Public project and job models expose no Git fields.
- Dashboard types and views expose no Git fields.
- `uv run python -m pytest`
- `npm --prefix web test -- --run`
- `npm --prefix web run build`
- `tgrep -n "base_commit|result_commit|head_commit|commit_message|\\.writes|inspect_repository|repositories" src/openmcp -g '*.py' || echo NONE`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.
Use table rebuilds. Do not use `ALTER TABLE DROP COLUMN`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
