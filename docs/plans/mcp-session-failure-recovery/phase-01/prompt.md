## Original User Request

Fix OpenMCP after backend errors, retries, or timeouts. Keep API
and MCP tool calls responsive after those outcomes.

## Phase

Bound public MCP job waits.

## Tasks

- task-1: Add failing bounded-wait behavior tests.
- task-2: Normalize only public MCP wait timeouts.
- task-3: Document safe polling behavior.

## Context

`job_wait` currently defaults `timeout_s` to zero. Zero reaches
`Runtime.wait` and `ProjectScheduler.wait` as unlimited waiting.
Codex expires MCP calls after 300 seconds. Later calls can queue
behind the pending wait and lose their response receivers.

This phase must not change runtime, scheduler, backend, retry, or
provider timeout semantics.

## Files

- `src/openmcp/server.py`
- `tests/test_server.py`
- `README.md`
- `docs/plans/mcp-session-failure-recovery/phase-01/notes.md`
- `docs/plans/mcp-session-failure-recovery/phase-01/journal.md`

## Done When

- Omitted `timeout_s` waits at most 30 seconds.
- Explicit zero waits at most 30 seconds.
- Values above 30 seconds are clamped.
- Negative values fail before scheduler waiting.
- Terminal jobs return without waiting.
- Timeout returns the latest durable `JobView`.
- Runtime and scheduler zero semantics remain unchanged.
- `uv run pytest tests/test_server.py -q`
- `uv run pytest tests/test_execution.py::test_retries_reuse_targets_after_each_failover_pass tests/test_execution.py::test_cancellation_interrupts_retry_backoff -q`

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this
phase's `notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
