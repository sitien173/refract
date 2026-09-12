# Phase 1: Persist complete tool activity

## Objective

Extend the provider-neutral transcript contract for new jobs. Persist each provider's available raw tool input and output. Keep this phase limited to backend normalization, persistence tests, and dashboard API tests.

Raw tool payload exposure is approved for the local dashboard. Continue excluding prompts, reasoning, thinking, unrelated diagnostics, environment data, arbitrary provider objects, and hidden transcript material. Historical jobs are not backfilled.

## Scope

Modify only:

- `src/openmcp/backends/claude.py`
- `src/openmcp/backends/codex.py`
- `src/openmcp/backends/pi.py`
- `src/openmcp/backends/agy.py`
- `tests/test_streaming_backends.py`
- `tests/test_execution.py`
- `tests/test_dashboard.py`

Do not modify `src/openmcp/streaming.py`, `src/openmcp/execution.py`, frontend source, or generated assets.

## Contract

Preserve existing event kinds, identifiers, ordering, and status fields. Add optional fields only when the provider supplied them:

```text
tool.started.data.input
tool.completed.data.output
```

Values may be any JSON value. Preserve objects, arrays, strings, numbers, booleans, and null without stringification. Property absence means unavailable. Provider-supplied null remains a present value.

## Provider mappings

### Claude

- Read tool start from `content_block_start` where `content_block.type == "tool_use"`.
- Preserve `content_block.name` as the tool name.
- Copy `content_block.input` only when that field exists.
- Do not invent output from `content_block_stop`.
- Retain a result only if an existing supported structured event supplies one and it safely matches the existing tool entity.

### Codex

- On tool `item.started`, copy `item.input` when present.
- On tool `item.completed`, copy `item.output` when present.
- Preserve raw provider ID to normalized entity ID mapping.

### Pi

- On `tool_execution_start` or supported `tool_call`, copy `args` when present.
- Use another input field only when existing fixtures prove that shape.
- On `tool_execution_end` or supported `tool_result`, copy `result` when present.
- Preserve camelCase and snake_case tool-call ID matching.
- Preserve current error status normalization.

### Agy

- On `tool.started` or `tool_started`, copy the observed `arguments` field.
- Support `input` or `args` only when represented by actual fixtures.
- On `tool.completed` or `tool_completed`, normalize the observed `output` or `result` field into `data.output`.
- Never pass through unrelated event fields.

## Tasks

1. Update backend characterization tests first.
2. Add distinct nested tool payload fixtures.
3. Confirm the tests fail before implementation.
4. Implement minimal provider-specific normalization.
5. Add persistence and dashboard retrieval coverage.
6. Run lifecycle, quota, and security regressions.

Existing security tests must be narrowed, not removed. Approved tool payloads must persist. Prompt, reasoning, thinking, diagnostic, environment, and unrelated secrets must remain absent. Tool payloads must remain absent from `job.result.text`.

Verify this path preserves structural equality:

```text
provider event
→ normalized event
→ StreamRecorder
→ job_stream_events.data_json
→ dashboard output API
```

The SSE channel remains cursor notification only.

## Constraints

- Do not copy complete provider events.
- Do not add generic field pass-through.
- Do not redact approved `input` or `output` values.
- Do not change event or byte quotas.
- Do not exempt tool payloads from quotas.
- Do not change truncation calculations.
- Do not change `attempt.finished` behavior.
- Do not change retries, cancellation, or attempt ordering.
- Do not change assistant or final-result extraction.
- Do not add a database migration.
- Do not change non-streaming behavior.
- Missing values must remain absent, not fabricated.

## Acceptance criteria

- Every backend has tests for its real event shape.
- Available input persists under `data.input`.
- Available output persists under `data.output`.
- Missing fields remain absent.
- Present null, false, zero, empty strings, arrays, and objects survive.
- Nested JSON survives storage and API retrieval unchanged.
- Tool entity pairing and event ordering remain unchanged.
- Tool payloads never enter assistant or final result text.
- Non-tool private content remains excluded.
- Existing quotas and truncation behavior remain unchanged.
- Attempt completion, retries, cancellation, and failures remain unchanged.
- Historical rows without payload fields remain valid.

## Verification

```bash
uv run pytest -q tests/test_streaming_backends.py
uv run pytest -q tests/test_streaming_backends.py tests/test_execution.py tests/test_dashboard.py
uv run pytest -q tests/test_execution.py -k "attempt or stream or quota or truncat or cancel or retry or provider"
uv run pytest -q tests/test_dashboard.py -k "output or stream or security"
git diff --check
```

Confirm only the seven scoped files changed.

## Commit

```text
feat(streaming): persist raw tool transcript details
```
