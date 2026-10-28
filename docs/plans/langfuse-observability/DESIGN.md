# Langfuse Observability Design

**Status:** Confirmed 2026-10-28
**Consultation:** Job `4bae2844-9bec-4515-9348-931bb151e7d2` agreed on a thin direct-SDK wrapper with job-derived trace IDs; it cited no file:line evidence, and its API names `langfuse.utils.get_uuid5` and `input_cached` are unverified and not relied on.

## Purpose

Send Refract daemon activity to a self-hosted Langfuse instance so operators can inspect jobs, target attempts, model usage, and MCP tool requests in one place.

## Users and Success Criteria

Users: Refract operators debugging jobs and tracking model cost.

Success criteria:

- With `[langfuse] enabled = true` and keys set, one job produces one Langfuse trace containing the job span, one generation per target attempt, worker question events, and the `job_submit`, `job_wait`, `job_cancel`, `job_retry`, and `job_answer` tool spans for that job.
- Generations carry model name and token usage from `TelemetryAccumulator`.
- Job span and generations carry prompt and result text.
- With the feature disabled, unconfigured, or the extra absent, behavior and test results are unchanged.
- A Langfuse outage or SDK exception never fails, delays, or alters a job or tool response.

## Constraints and Non-Goals

Constraints:

- Langfuse Python SDK v4 line, verified at v4.15.4 via Context7 `/langfuse/langfuse-python`.
- `langfuse` is an optional extra `refract[langfuse]`, not a core dependency.
- Credentials come only from `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`, never from TOML.
- Prompt and result text are always sent when tracing is enabled. User-confirmed.

Non-goals:

- Langfuse prompt management, datasets, evaluations, or scores.
- Generic OpenTelemetry instrumentation for other exporters.
- Backfilling traces for jobs that finished before enablement.
- Content redaction or truncation.

## Chosen Approach

Thin direct-SDK wrapper in a new module `server/src/refract/observability.py`, called from a small set of existing hook points.

Rejected:

- Generic OpenTelemetry plus OTLP export: Langfuse-specific generation attributes are still required, and it adds operator config.
- Post-hoc exporter reading SQLite: no live traces and no MCP tool spans.

## Architecture and Data Flow

Module `observability.py` owns a single `Langfuse` client built from `DaemonConfig.langfuse`. It passes its own `TracerProvider` so a host application's global OpenTelemetry provider is neither used nor exported. Every public helper is a no-op when tracing is inactive.

Trace identity:

- `trace_id = sha256("refract:job:" + job_id).hexdigest()[:32]`, stable across daemon restarts.
- Langfuse `session_id = f"{project_id}:{context_key}"` for job traces, set via `propagate_attributes`.

Hook points:

| Location | Observation | Payload |
|---|---|---|
| `server/src/refract/server.py:496` `_logged_request` | `tool` span per MCP tool call. Joins the job trace when the call has a `job_id` argument or `job_submit` returns one; otherwise a standalone trace with `session_id = project_id` when known. | Input: tool arguments. Output: response. Metadata: outcome, `error_type`, `duration_ms`. |
| `server/src/refract/execution.py:957` `JobRunner.run` | Root `agent` span on the job trace | Input: prompt. Output: result text. Metadata: workflow, profile, final state, `failure.kind`. |
| `server/src/refract/execution.py:273` `TargetExecutor._execute_attempt` | `generation` child per attempt | Model, `usage_details` from `TelemetryAccumulator`, effective prompt, result, target ID, backend, attempt number. |
| Worker ask path and `job_answer` | Event on the job trace | Question text and answer text. |

Mapping rules:

- Retries and target failover produce sibling generations under the job span.
- Cancellation ends open observations with `level="WARNING"` and `status_message="cancelled"`.
- Failed attempts use `level="ERROR"` with the failure kind as status message.
- `job_wait` spans cover only the actual request duration; no observation stays open across the long poll.

Lifecycle:

- `Runtime.start` creates the client.
- `Runtime.close` calls `flush()` then `shutdown()` through `run_sync`.
- `Runtime.publish_configuration` rebuilds the client when `[langfuse]` changes, flushing the old client first.

Config, parsed in `server/src/refract/config.py` following `LoggingConfig`:

```toml
[langfuse]
enabled = false
base_url = "http://localhost:3000"
environment = ""
sample_rate = 1.0
```

`release` is set to the Refract package version.

## Errors and Edge Cases

- Every helper catches `Exception`, logs one `WARNING` with `event="langfuse.error"`, and returns.
- Enabled with missing keys, or with the extra not installed: one startup `WARNING`, then no-op.
- Invalid `sample_rate` outside `[0, 1]` or non-http(s) `base_url`: config validation error, same path as existing config errors.
- Export runs on the SDK background thread; Langfuse downtime drops spans only.
- Daemon restart mid-job: the new process emits a new job span on the same trace ID; the open span from the old process is lost.
- Large prompts and results are sent unmodified; Langfuse server limits apply.

## Migration

n/a. No schema change. Default `enabled = false`. Docs update in `server/README.md` and `CHANGELOG.md`.

## Testing

- Unit tests for `observability.py`: deterministic trace ID; disabled, missing-key, and missing-import no-op paths; SDK exceptions swallowed and logged.
- Integration tests using an in-memory OpenTelemetry span exporter passed via `Langfuse(span_exporter=...)`: one job yields job span, attempt generations, and joined tool spans on one trace ID; retry or failover yields sibling generations; cancellation yields `WARNING`; model and usage attributes present.
- Config tests: parsing, validation, hot reload rebuilds the client.
- Full suite `uv run pytest` in `server/` passes with and without the extra installed.

## Risks and Open Questions

- Open: exact Langfuse `usage_details` keys for cache read and cache write tokens. Verify against SDK docs before implementation.
- Open: whether `InMemorySpanExporter` is available through the `langfuse` dependency tree or needs `opentelemetry-sdk` in the dev extra.
- Risk: always-on content upload sends repository code and any secrets present in prompts to the Langfuse server. Accepted by the user; documented in README.
- Risk: span volume from frequent `job_wait` calls. Mitigated by `sample_rate`.
