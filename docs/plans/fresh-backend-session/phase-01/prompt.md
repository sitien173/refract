## Original User Request

Implement support for a fresh backend session through a new `job_submit` flag.

## Phase

Persist and execute fully fresh backend session jobs.

## Tasks

- task-1: Add failing MCP-schema and SQLite migration coverage. Make the
  `fresh_session` flag durable with the smallest API, runtime, and database
  changes.
- task-2: Add a failing asynchronous execution test with existing native session
  and turn history. Prove fresh jobs receive an empty session ID and exact prompt,
  then prove their successful session is resumed by the next standard job.
- task-3: Document the new MCP parameter and JSON payload.

## Context

`Runtime.submit` persists queued jobs. `JobRunner.run` reads the record after
scheduling and calls `TargetExecutor.execute`. The executor currently resumes a
stored session when present, otherwise it injects prior turns. A fresh job must
bypass both paths for every target attempt. `Database.append_turn` must remain
unchanged so successful fresh jobs replace the stored target session.

Schema version 9 is current. Version 10 adds
`jobs.fresh_session INTEGER NOT NULL DEFAULT 0`. Existing jobs must retain
normal behavior. Do not add this flag to `JobView`.

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
- The flag survives asynchronous queueing in the job record.
- A fresh job supplies empty session ID and exact submitted prompt.
- A fresh job never injects stored history.
- The next standard job resumes the successful fresh session.
- Fresh databases use schema version 10.
- Existing version 9 jobs migrate with `fresh_session=0`.
- `JobView` and drivers stay unchanged.
- `python -m pytest tests/test_database.py tests/test_execution.py tests/test_server.py`
- `python -m pytest`

## Rules

Follow the supplied worker contract. Work test-first. Stay within scope.
Maintain this phase's `notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
