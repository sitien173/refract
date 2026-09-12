## Original User Request

Turn the confirmed worker dashboard streaming design into an implementation plan,
then execute every phase through completion.

## Phase

Expose durable job transcripts through cursor replay and SSE invalidation.

## Tasks

- task-1: Add RED dashboard replay tests for cursor pagination, limits, retained
  cursors, statuses, unknown jobs, and redaction.
- task-2: Add safe dashboard output models and database-backed cursor replay.
- task-3: Add RED SSE tests for initial and committed cursors, coalescing,
  disconnect cleanup, keepalives, and the REST-to-subscription race.
- task-4: Add the runtime stream hub and cursor-only SSE endpoint.

## Context

Durable normalized events already exist in `job_stream_events`. REST is the only
transcript payload transport. SSE only sends committed high-water cursors and
keepalive comments. The runtime-owned hub must retain no transcript payload and
must notify only after durable database commits. Status is one of unavailable,
active, complete, truncated, or failed. Derive it from job state, retained
events, truncation markers, and safe lifecycle failure kinds. Preserve existing
dashboard security, route behavior, and URI-only MCP resource notifications.

## Files

- `src/openmcp/streaming.py`
- `src/openmcp/runtime.py`
- `src/openmcp/dashboard.py`
- `src/openmcp/models.py`
- `tests/test_streaming.py`
- `tests/test_dashboard.py`
- `tests/test_server.py`

## Done When

- REST replay is the only transcript payload transport.
- SSE sends the current high-water immediately and only after commits thereafter.
- Missed or coalesced SSE notifications cannot lose committed events.
- Slow subscribers retain only the latest pending cursor.
- Unknown jobs return the existing safe not-found shape.
- Existing dashboard and MCP contracts remain unchanged.
- `uv run pytest tests/test_streaming.py tests/test_dashboard.py tests/test_server.py`
- `git diff --check`

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`. Use RED, GREEN, and REFACTOR for every behavior.
Do not add frontend work. Do not expose prompts, provider-native payloads,
lifecycle payloads, or internal exception details. Place new dashboard routes
before fallback routes. Do not change MCP subscription behavior.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
