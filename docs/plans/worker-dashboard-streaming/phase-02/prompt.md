## Original User Request

Turn the confirmed worker dashboard streaming design into an implementation plan,
then execute every phase through completion.

## Phase

Normalize safe provider events and bridge worker-thread output into the durable
stream recorder.

## Tasks

- task-1: Add sanitized RED fixtures for Claude, Codex, Pi, and Agy mappings.
- task-2: Implement synchronous provider adapters without changing final results.
- task-3: Add RED bounded bridge, cancellation, and thread-ownership tests.
- task-4: Implement the bridge, attempt ordering, flushing, and capability fallback.

## Context

Provider commands execute through worker threads while the SQLite connection and
`StreamRecorder` remain event-loop owned. Every adapter emits only normalized
assistant text and safe tool lifecycle events. Exclude prompts, reasoning, tool
arguments, tool results, diagnostics, planted secrets, and nested subagent text.
Preserve final result and session extraction. Claude uses partial stream JSON,
Agy uses stream JSON, Codex uses JSONL, and Pi uses JSON. Agy continuations remain
one OpenMCP target attempt. The bridge has 256 slots and blocking producer
backpressure. Accepted events flush before target lifecycle completion.
Structured-mode capability checks happen before prompt execution. Unsupported
versions use final-only fallback without retrying a submitted prompt.

## Files

- `src/openmcp/backends/__init__.py`
- `src/openmcp/backends/_shell.py`
- `src/openmcp/backends/claude.py`
- `src/openmcp/backends/codex.py`
- `src/openmcp/backends/pi.py`
- `src/openmcp/backends/agy.py`
- `src/openmcp/drivers.py`
- `src/openmcp/execution.py`
- `tests/test_execution.py`
- `tests/test_streaming_backends.py`
- `tests/test_live_backends.py`

## Done When

- Every backend emits provider-neutral assistant events.
- Safe tool lifecycle events emit when providers expose them.
- Unknown and unsafe provider content is ignored.
- Fixture secrets never reach normalized serialization.
- Queue saturation blocks producers without dropping events.
- Provider threads never access the database.
- Accepted events flush before lifecycle completion.
- Failed attempts remain labeled and replayable.
- Only successful `DriverResult.text` becomes `job.result.text`.
- Existing final result and session fixtures remain unchanged.
- `uv run pytest tests/test_streaming_backends.py tests/test_execution.py tests/test_live_backends.py -m 'not live'`
- `git diff --check`

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`. Use RED, GREEN, and REFACTOR for every behavior.
Do not implement dashboard endpoints or frontend code. Do not invoke paid live
providers. Do not persist or emit prompts, reasoning, tool arguments, tool
results, diagnostics, or nested subagent text.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
