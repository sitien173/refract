## Original User Request

Turn the confirmed worker dashboard streaming design into an implementation plan,
then execute every phase through completion.

## Phase

Add durable stream storage and an event-loop recorder.

## Tasks

- task-1: Add RED migration and cursor persistence tests.
- task-2: Implement schema version 11 and stream database methods.
- task-3: Add RED recorder batching, coalescing, quota, and failure tests.
- task-4: Implement the recorder and runtime retention cleanup.

## Context

OpenMCP stores jobs and lifecycle events in one SQLite connection created with
default same-thread enforcement. Provider execution later runs in worker threads,
so this phase must keep every database call on the daemon event-loop thread.
Lifecycle events and `job.result.text` remain unchanged. Transcript events use a
separate table and globally monotonic cursor scoped by job.

The confirmed defaults are 50-event or 64-KiB batches, a 100-millisecond timer,
8-KiB text events, 8 MiB or 20,000 events per job, one truncation marker, and
seven-day retention for terminal transcripts only.

## Files

- `src/openmcp/database.py`
- `src/openmcp/models.py`
- `src/openmcp/streaming.py`
- `src/openmcp/runtime.py`
- `tests/test_database.py`
- `tests/test_streaming.py`
- `tests/test_runtime.py`

## Done When

- Version 10 databases migrate to version 11 safely.
- Stream batches persist transactionally and replay exactly by cursor.
- Recorder text coalescing and every confirmed limit have tests.
- Active transcripts are never pruned.
- Persistence failures cannot alter final job results.
- `uv run pytest tests/test_database.py tests/test_streaming.py tests/test_runtime.py`
- `git diff --check`

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`. Use RED, GREEN, and REFACTOR for every behavior.
Do not implement provider adapters or dashboard endpoints in this phase.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
