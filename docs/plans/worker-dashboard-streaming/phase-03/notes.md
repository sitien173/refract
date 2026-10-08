<!-- ccg-shared-version: 10.5.0 -->

# Phase 3 — Decision Notes

## Task 1

### Decisions made
- Added replay tests for cursor pagination and bounds.
- Tested all five stream status variations.
- Verified 404 response for unknown jobs.
- Verified exclusion of sensitive fields from response.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Unknown job returns 404 with not_found code.

### Follow-ups for human
- none

### Test evidence
- RED: `uv run pytest tests/test_dashboard.py -k "test_job_output"` failed with 4 errors.
- Root cause: `/dashboard/api/jobs/{job_id}/output` route was missing.

## Task 2

### Decisions made
- Implemented `GET /dashboard/api/jobs/{job_id}/output` handler.
- Derived stream status from events, truncation, and state.
- Bounded limit between 1 and 500.
- Registered output route before fallback routes.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Clamped query parameters handle invalid input safely.

### Follow-ups for human
- none

### Test evidence
- GREEN: `uv run pytest tests/test_dashboard.py -k "test_job_output"` passed 4 tests.
- Root cause: not applicable.

## Task 3

### Decisions made
- Added unit tests for JobStreamHub in test_streaming.
- Added tests for SSE endpoint in test_dashboard.
- Covered initial cursor, post-commit delivery, and keepalives.
- Covered capacity-one coalescing and disconnect cleanup.
- Covered REST replay to subscription race condition.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- SSE client uses standard text/event-stream parsing.

### Follow-ups for human
- none

### Test evidence
- RED: `tests/test_streaming.py` failed with ImportError for JobStreamHub.
- RED: `tests/test_dashboard.py` failed with 6 errors for SSE endpoint.

## Task 4

### Decisions made
- Implemented `JobStreamHub` in `src/openmcp/streaming.py`.
- Bound `stream_hub` into `Runtime` in `src/openmcp/runtime.py`.
- Hooked `database.append_stream_events` to notify hub post-commit.
- Implemented `GET /dashboard/api/jobs/{job_id}/output/updates` SSE handler.
- Emitted initial high-water cursor immediately upon connection.
- Cleaned up subscription on client disconnect in finally block.
- Emitted keepalive comments every 20 seconds.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Queue size 1 provides bounded memory per subscriber.

### Follow-ups for human
- none

### Test evidence
- GREEN: `uv run pytest tests/test_streaming.py tests/test_dashboard.py tests/test_server.py` passed 72 tests.
- Root cause: not applicable.
