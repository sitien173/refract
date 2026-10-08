## Original User Request

Execute the `mcpserver-v2-subscriptions` plan. This phase adds durable job
resource update subscriptions to the SDK v2 server.

## Phase

Let capable clients observe durable job updates without polling.

## Tasks

- task-1: Add failing submission URI and transition notification tests.
- task-2: Add one asynchronous notifier across Runtime and JobRunner.
- task-3: Connect notifications to the MCPServer subscription bus.
- task-4: Document listener ordering, recovery, and fallback behavior.

## Context

Add `resource_uri` to every `SubmissionResult`, using the existing exact
`openmcp://jobs/{job_id}` URI. Publish ResourceUpdated events after durable
queued, running, succeeded, failed, cancelled, interrupted, and retry
transitions. Use `subscriptions/listen`. `job_wait` remains unchanged.
Notification delivery failures must be logged and must never change a job
outcome. Do not add persistence or replay for notifications, stdio, a second
URI scheme, or scheduler changes.

## Consultation Findings

Use one MCP SDK v2 `InMemorySubscriptionBus` and publish exact job URIs only
after database transitions persist. Inject an async notifier through Runtime
and JobRunner, logging ordinary notification failures without affecting job
outcomes. Await publication rather than creating detached tasks. Cover startup
interruption, queued and running cancellation, and retry-to-queued transitions.
Do not retain request Context for scheduler notifications.

## Files

- `src/openmcp/models.py`
- `src/openmcp/runtime.py`
- `src/openmcp/execution.py`
- `src/openmcp/server.py`
- `tests/test_execution.py`
- `tests/test_server.py`
- `README.md`

## Done When

- The phase acceptance criteria in `PLAN.md` all hold.
- `uv run pytest tests/test_server.py tests/test_execution.py -q`
- `uv run pytest -q`
- `uv build`
- `uv run openmcp doctor`
- `tgrep -n -e 'resource_uri' -e 'subscriptions/listen' src tests README.md`
- `git diff --check`

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
