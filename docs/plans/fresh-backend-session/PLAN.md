# Fresh Backend Session — Plan

Design: `docs/plans/fresh-backend-session/DESIGN.md`

---

### Phase 1: Persist and execute fresh-session jobs

**Task Guide Input:** Add a `fresh_session` boolean flag to the `job_submit`
MCP tool. The flag defaults to false and must survive queueing and daemon
restart. With `fresh_session=true`, every target attempt must pass an empty
session ID to its backend and must pass the submitted prompt without injected
turn history. A successful attempt must continue using the existing
`append_turn` behavior, so later ordinary jobs resume the newly created
session. Add SQLite schema version 10 with a non-null `jobs.fresh_session`
column defaulting to zero. Preserve existing jobs and resume behavior during
migration. Do not expose the flag in `JobView`, change backend drivers, change
context-key behavior, or add configuration.

**Goal:** Callers can submit durable jobs that begin fully fresh backend
sessions.

**Files:**
- Modify: `src/openmcp/server.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `src/openmcp/database.py`
- Modify: `src/openmcp/execution.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_execution.py`
- Modify: `tests/test_database.py`
- Modify: `README.md`

**Tasks:**
1. Write focused failing tests for the MCP input schema, schema version 10 and
   version 9 upgrade default, then add the smallest server, runtime, database,
   and migration changes that make the flag durable.
2. Write a focused failing asynchronous execution test with a stored session and
   turn history. Assert a fresh job receives an empty session ID and its exact
   submitted prompt. Assert its successful session becomes the one resumed by
   the next standard job. Then add the smallest runner and target-executor
   plumbing to pass the test.
3. Document `fresh_session` in the MCP tool signature and submission payload.

**Acceptance Criteria:**
- `job_submit` exposes `fresh_session` and defaults it to `false`.
- The flag persists in queued job records.
- A fresh job supplies no native session and no injected history.
- A successful fresh job replaces the stored native session.
- A standard job retains current resume and history behavior.
- Fresh databases use schema version 10.
- Version 9 databases upgrade with `fresh_session=0` for existing jobs.
- `JobView` and backend driver interfaces remain unchanged.

**Reviewer Checklist:**
- The runner reads the persisted field rather than request-local state.
- Every retry attempt of a fresh job bypasses session and history.
- An empty session ID cannot accidentally trigger history injection.
- The migration is idempotent and preserves existing jobs.
- Default submissions follow the unchanged path.
- Documentation matches the MCP schema exactly.

**Verification Checks:**
- `uv run pytest tests/test_database.py tests/test_execution.py tests/test_server.py`
- `uv run pytest`
- `tgrep -n "fresh_session" src/openmcp tests README.md`

**Commit:** `feat(runtime): support fresh backend sessions`
