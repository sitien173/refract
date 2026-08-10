# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Add the exact job URI through a shared `job_resource_uri()` helper so submissions, retries, and notifications cannot drift.
- Make `resource_uri` required on `SubmissionResult`.

### Spec deviations
- none

### Tradeoffs accepted
- `Runtime.cancel()` is asynchronous so durable cancellation publication can be awaited rather than detached.

### Assumptions
- Existing callers of the MCP `job_cancel` tool already await the tool boundary.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: New submission and notifier tests initially failed with a missing `resource_uri` field and unsupported `Runtime(..., notifier=...)`; after implementation, focused execution and server tests pass.

## Task 2

### Decisions made
- Inject one URI-based async notifier into `Runtime` and pass Runtime's guarded notifier to `JobRunner`.
- Publish only after each database transition and before enqueueing newly queued or retried work, preserving per-job notification order.

### Spec deviations
- none

### Tradeoffs accepted
- Notification failures are logged at the Runtime/JobRunner boundary and suppressed, so a broken listener cannot alter durable job outcomes.

### Assumptions
- SQLite transaction context completion is the persistence boundary for the existing database transition methods.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Transition, cancellation, retry, startup interruption, and notification-failure tests pass; `uv run pytest tests/test_execution.py -q` passes 24 tests.

## Task 3

### Decisions made
- Create one `InMemorySubscriptionBus`, pass it into `MCPServer`, and publish typed `ResourceUpdated` events with the exact job URI.
- Keep scheduler notifications independent of request `Context` and use the existing SDK v2 automatic `subscriptions/listen` handler.

### Spec deviations
- none

### Tradeoffs accepted
- The bus remains in-process and non-replayable as specified; clients recover with an immediate resource read after listening or reconnecting.

### Assumptions
- MCP SDK v2 performs exact URI filtering for `resource_subscriptions`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: The server bus test verifies an exact `ResourceUpdated` URI, and Runtime lifecycle tests verify notifier injection; focused server/execution tests pass 41 tests.

## Task 4

### Decisions made
- Document the submit, listen, acknowledgement, immediate-read, notification-read, reconnect, and `job_wait` fallback flow in README.

### Spec deviations
- none

### Tradeoffs accepted
- Documentation describes level-triggered notifications without duplicating durable job payloads.

### Assumptions
- `job_wait` retains its existing 30-second bound and behavior.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `resource_uri` and `subscriptions/listen` references are present in source, tests, and README; full tests, build, doctor, and diff checks pass.
