## Original User Request

Implement support for a fresh backend session through a new `job_submit` flag.

## Phase

Persist and execute fully fresh backend session jobs.

## Tasks

- task-1: Add failing MCP-schema and SQLite migration coverage. Make the
  `fresh_session` flag durable with the smallest API, runtime, and database
  changes. Keep `Database.create_job` compatible with direct callers through a
  false default.
- task-2: Add failing asynchronous execution tests with existing native sessions
  and turn history. Prove every fresh attempt receives an empty session ID and
  the exact validated, persisted prompt. Prove a successful fresh job clears all
  preexisting sessions for its project, workflow, and context key. Prove the
  next standard job resumes only the newly returned session.
- task-3: Add coverage for failover, retry, restart, and standard sessionless
  history reconstruction. Document the new MCP parameter and JSON payload.

## Context

`Runtime.submit` validates and persists queued jobs. `JobRunner.run` reads the
record after scheduling and calls `TargetExecutor.execute`. The executor
currently resumes a stored target session when present, otherwise it injects
prior turns. A fresh job must bypass both paths for every target attempt.

Freshness is context-stream-wide after success. Before recording a successful
fresh turn, remove all `context_sessions` rows for the same project, context
key, and workflow. Then retain `append_turn` behavior. This also removes an old
session when the backend succeeds without returning a new session ID. Do not
clear old sessions when the fresh job fails.

Schema version 9 is current. Version 10 adds
`jobs.fresh_session INTEGER NOT NULL DEFAULT 0`. Make v8-to-v9 migration target
version 9 explicitly, then add a separate transactional v9-to-v10 migration.
Test direct v8-to-v10 and v9-to-v10 upgrades. Existing jobs must retain normal
behavior. Do not add this flag to `JobView`.

## Files

- `src/openmcp/server.py`
- `src/openmcp/runtime.py`
- `src/openmcp/database.py`
- `src/openmcp/execution.py`
- `tests/test_server.py`
- `tests/test_execution.py`
- `tests/test_database.py`
- `README.md`

## Done When

- `job_submit` accepts `fresh_session` with default `false`.
- The flag survives asynchronous queueing, retry, and restart in the job record.
- Every fresh attempt supplies empty session ID and exact validated prompt.
- A fresh job never injects stored history.
- Successful fresh execution clears all prior sessions in its context stream.
- A successful fresh session becomes the only resumable session in that stream.
- Standard sessionless jobs still inject stored history.
- Fresh databases use schema version 10.
- Version 8 and version 9 databases upgrade with `fresh_session=0`.
- `JobView` and drivers stay unchanged.
- `python -m pytest tests/test_database.py tests/test_execution.py tests/test_server.py`
- `python -m pytest`

## Rules

Follow the supplied worker contract. Work test-first. Stay within scope.
Maintain this phase's `notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
