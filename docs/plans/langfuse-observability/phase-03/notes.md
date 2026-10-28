# Phase 3 Decision Notes

## Task 1

### Decisions made
- Use the SDK's private per-client OpenTelemetry tracer and observation-conversion method to create an ended tool span with explicit start/end nanosecond timestamps; installed SDK `start_observation` has no `start_time` parameter.
- Bind the wrapped function arguments using its original signature, omit `ctx` from tool input, and retain the existing response/error handling and logging.
- Use job trace IDs for known job calls and `propagate_attributes(session_id=project_id)` for standalone calls. Resolve project ID from the successful `project_resolve` response.

### Spec deviations
- none

### Tradeoffs accepted
- Retrospective timestamps rely on the verified installed Langfuse v4 private `_otel_tracer` and `_create_observation_from_otel_span` APIs because its public observation API cannot accept a start timestamp.

### Assumptions
- Tool response strings and argument values are suitable for direct Langfuse serialization, consistent with the confirmed design's unredacted-content policy.

### Follow-ups for human
- none

### Test evidence
- Historical evidence retained: the earlier helper-only test initially failed because `record_tool_observation` did not exist. As the coordinator correctly noted, this is not a behavioral RED and does not establish MCP-hook acceptance.
- Fresh behavioral RED -> GREEN: actual `_logged_request` integration first asserted missing job tool spans. Cause: runtime config discovery replaced the injected in-memory tracer because test config remained disabled. The test now enables Langfuse in its temporary test TOML and confirms actual `project_resolve`, `task_guide`, `job_submit`, and `job_wait` spans.
- Behavioral RED -> GREEN: conversion-failure injection after raw span creation failed the `is_recording() is False` assertion. Production cleanup now ends any still-recording raw span in `finally`; the in-memory exporter confirms closure.
- Actual MCP error test confirms the unchanged `unknown_job` envelope and `OrchestrationError` metadata. Injected SDK conversion errors preserve both the successful task-guide response and failed MCP response envelope.
- Long-poll test holds the actual MCP request at an await point and verifies no tool span is started/open during the poll; after completion, exactly one ended span is exported with request interval agreeing with `duration_ms` within 5 ms.
- Focused checks: server hook tests 3 passed; observability tests 2 passed.
- Final full checks: `uv run --exact pytest -q` (1207 passed, 23 skipped, 15 deselected); `UV_PROJECT_ENVIRONMENT=/tmp/refract-langfuse-sdk-acceptance uv run --extra langfuse pytest -q` (1230 passed, 15 deselected).

## Task 2

### Decisions made
- Documented all four `[langfuse]` fields, environment-only credential variables, both optional installation methods, and the unredacted prompt/result content upload risk.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Documentation checked alongside the two full-suite commands above; both passed.
