# Fresh Backend Session

## Purpose

Allow a caller to start a job in a new backend session while retaining the
existing context key. The caller sets `fresh_session=true` on `job_submit`.

## Decisions

- Add `fresh_session: bool = False` to the MCP tool and runtime facade.
- Store the flag in the `jobs` table as `fresh_session INTEGER NOT NULL DEFAULT 0`.
- Advance the SQLite schema from version 9 to version 10.
- A fresh job passes the submitted prompt verbatim.
- A fresh job supplies an empty backend session ID.
- A successful fresh job replaces the stored session for its context stream.
- The public `JobView` remains unchanged.

## Execution Semantics

`fresh_session=false` preserves current behavior. The executor resumes the
stored target session when available. Without a stored session, it adds bounded
turn history to the submitted prompt.

`fresh_session=true` bypasses both behaviors for every target attempt. The
executor passes an empty session ID and the original submitted prompt. It still
records the successful turn and backend-provided session ID. A later standard
job in the same project, workflow, context key, and target resumes that new
session.

A retry retains its original job flag. Therefore, retrying a fresh job starts a
new backend session again.

## Data Flow

1. `job_submit(..., fresh_session=true)` forwards the flag to `Runtime.submit`.
2. `Runtime.submit` persists the flag with the queued job.
3. `JobRunner.run` reads the persisted flag after asynchronous scheduling.
4. `TargetExecutor.execute` suppresses session lookup and history injection.
5. The existing driver starts a new backend session from the empty session ID.
6. Existing `append_turn` logic stores the new session after success.

## Migration

Fresh databases create the version 10 column. Version 9 databases add the
non-null column with a zero default. Existing queued and historical jobs retain
normal resume behavior.

## Non-goals

- No backend CLI or driver changes.
- No new context key behavior.
- No change to job result resources.
- No configurable history policy.

## Testing

- MCP discovery exposes `fresh_session` with a false default.
- A queued fresh job stores the flag durably.
- A preexisting session and history are both bypassed.
- The fresh job receives the original prompt exactly.
- The next standard job resumes the fresh job session.
- Fresh and upgraded databases report version 10 with the zero default.
- Existing schema migration coverage remains valid.
