# Langfuse Observability Plan

**Design:** `docs/plans/langfuse-observability/DESIGN.md`
**Base:** `refs/plans/langfuse-observability/base`
**Commit:** `feat(observability): add optional Langfuse tracing for jobs and MCP tools`

All commands run from `server/`. Baseline `uv run pytest -q` passes at the plan base, confirmed by the user on 2026-10-28.

Out of scope for every phase: any file holding credentials, `~/.config` or daemon home config files, `.env*`. Workers must not read or write them.

### Phase 1: Optional Langfuse client with config and runtime lifecycle

**Task Guide Input:** Server implementation. Add an optional `langfuse` extra, a `[langfuse]` daemon config section, a no-op-safe `observability.py` client wrapper, and wire it into runtime start, close, and config reload, with tests.
**Goal:** The daemon builds, flushes, rebuilds, and shuts down a Langfuse client from config, and is a no-op whenever tracing is inactive.
**Files:**
- Modify: `server/pyproject.toml`
- Modify: `server/uv.lock`
- Modify: `server/src/refract/config.py`
- Modify: `server/src/refract/runtime.py`
- Create: `server/src/refract/observability.py`
- Create: `server/tests/test_observability.py`
- Modify: `server/tests/test_config.py`
- Modify: `server/tests/test_runtime.py`
**Tasks:**
1. Add `[project.optional-dependencies] langfuse = ["langfuse>=4.15,<5"]`. If an in-memory OpenTelemetry span exporter is not importable from the `langfuse` dependency tree, add the needed `opentelemetry-sdk` pin to `dev`. Run `uv lock`. Verify the SDK `usage_details` keys for cache read and cache write tokens from installed SDK source, and record the result in the phase journal.
2. Add `LangfuseConfig` to `config.py` with `enabled: bool = False`, `base_url: str = "http://localhost:3000"`, `environment: str = ""`, `sample_rate: float = 1.0`, parsed from `[langfuse]` following `LoggingConfig`. Reject `sample_rate` outside `[0, 1]` and non-http(s) `base_url` through the existing config error path. Credentials are read only from `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`.
3. Create `observability.py`: a `Tracer` holder that builds `Langfuse(public_key, secret_key, base_url, environment, sample_rate, release=<refract version>, tracer_provider=<private TracerProvider>)`; `trace_id_for_job(job_id) = sha256(("refract:job:" + job_id).encode()).hexdigest()[:32]`; `flush()` and `shutdown()`. Every public function catches `Exception`, logs one `WARNING` with `event="langfuse.error"`, and returns. Disabled config, missing keys, or `ImportError` yield a no-op and one startup `WARNING` when `enabled = true`.
4. In `runtime.py`, create the tracer in `Runtime.start`, call flush then shutdown via `run_sync` in `Runtime.close`, and rebuild it in `publish_configuration` when the `[langfuse]` section changes, flushing the old client first.
**Acceptance Criteria:**
- Default config parses with `enabled = False`; invalid `sample_rate` and `base_url` raise the existing config error type.
- `trace_id_for_job` returns the same 32-char lowercase hex for the same job ID.
- With the extra absent, `enabled = true` logs one `WARNING` and all helpers are no-ops.
- A Langfuse constructor or `flush` exception is swallowed and logged with `event="langfuse.error"`.
- `Runtime.close` calls flush then shutdown; a `[langfuse]` change during `publish_configuration` replaces the client.
- No credential is read from TOML.
**Reviewer Checklist:**
- The `langfuse` import is lazy and confined to `observability.py`.
- The global OpenTelemetry tracer provider is never set or replaced.
- No blocking SDK call runs on the event loop thread.
- Config parsing mirrors existing `LoggingConfig` style and error messages.
**Verification Checks:**
- `uv run --exact pytest -q`
- `uv run --extra langfuse pytest -q tests/test_observability.py tests/test_config.py tests/test_runtime.py`

### Phase 2: Job, attempt, and worker-question tracing

**Task Guide Input:** Server implementation. Emit Langfuse observations from the job runner, target executor attempts, and the worker ask path using the Phase 1 `observability.py` helpers, with in-memory exporter integration tests.
**Goal:** Each job produces one trace with a job span, one generation per target attempt, and worker question events.
**Files:**
- Modify: `server/src/refract/observability.py`
- Modify: `server/src/refract/execution.py`
- Modify: `server/src/refract/ask.py`
- Modify: `server/src/refract/runtime.py`, limited to passing the existing per-runtime tracer holder into execution and ask hooks.
- Modify: `server/tests/test_observability.py`
- Modify: `server/tests/test_execution.py`
**Tasks:**
1. In `JobRunner.run`, open an `agent` span named `job` on `trace_id_for_job(job_id)` with `session_id = f"{project_id}:{context_key}"` via `propagate_attributes`. Input is the prompt. On finish, set output to the result text, metadata to workflow, profile, final state, and `failure.kind`, and level `ERROR` for failure or `WARNING` with `status_message="cancelled"` for cancellation.
2. In `TargetExecutor._execute_attempt`, open a `generation` child per attempt with model, effective prompt as input, result text as output, `usage_details` from the attempt `TelemetryAccumulator` using only available measurements and the key names verified in Phase 1, and metadata target ID, backend, and attempt number. Retries and failover produce sibling generations.
3. In `ask.py`, emit an event on the job trace when a worker question is raised and when an answer is delivered, carrying question and answer text.
**Acceptance Criteria:**
- Integration test with an in-memory span exporter: one successful job yields one job span and one generation sharing `trace_id_for_job(job_id)`, with model, usage, input, and output attributes present.
- A retried or failed-over job yields sibling generations under the same job span.
- A cancelled job yields `WARNING` level with `cancelled` status message.
- A worker question and answer yield two events on the job trace.
- With tracing inactive, `tests/test_execution.py` passes unchanged.
- An exception raised inside any observability helper does not change job state or result.
**Reviewer Checklist:**
- Every opened observation is ended on all paths, including `asyncio.CancelledError`.
- Usage fields are omitted, not zeroed, when a measurement is unavailable.
- Hook code in `execution.py` and `ask.py` is limited to calls into `observability.py`.
**Verification Checks:**
- `uv run --exact pytest -q`
- `uv run --extra langfuse pytest -q tests/test_observability.py tests/test_execution.py tests/test_ask.py`

### Phase 3: MCP tool spans and documentation

**Task Guide Input:** Server implementation plus docs. Add a Langfuse `tool` span for every MCP tool call in `_logged_request`, joined to the job trace when a job ID is known, and document the feature.
**Goal:** Every MCP tool call appears in Langfuse, joined to its job trace when it concerns a job, and operators can enable the feature from the README.
**Files:**
- Modify: `server/src/refract/observability.py`
- Modify: `server/src/refract/server.py`
- Modify: `server/tests/test_observability.py`
- Modify: `server/tests/test_server.py`
- Modify: `server/README.md`
- Modify: `CHANGELOG.md`
**Tasks:**
1. In `_logged_request` at `server/src/refract/server.py:496`, record a `tool` span named after the operation with tool arguments as input, response as output, and outcome, `error_type`, and `duration_ms` as metadata. Use `trace_id_for_job` when the call has a `job_id` argument or `job_submit` returns a job ID; otherwise use a standalone trace with `session_id = project_id` when known. The span covers only the actual request duration.
2. Document the `[langfuse]` section, the `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` variables, `pip install 'refract[langfuse]'` or `uv sync --extra langfuse`, and a warning that prompt and result text, including any repository code or secrets in them, are uploaded to the Langfuse server. Add an `Unreleased` entry to `CHANGELOG.md`.
**Acceptance Criteria:**
- Integration test: `job_submit` then `job_wait` for one job yields two `tool` spans on `trace_id_for_job(job_id)`.
- `project_resolve` and `task_guide` yield standalone traces.
- A tool call that raises still yields its span with `error_type`, and the MCP error response is unchanged.
- `tests/test_mcp_schema_contract.py` and `tests/test_server.py` pass unchanged with tracing inactive.
- README and CHANGELOG contain the documented items.
**Reviewer Checklist:**
- Tool responses, error envelopes, and request logging are byte-identical with tracing inactive.
- No observation stays open across a `job_wait` long poll.
- Docs state the content-upload risk plainly.
**Verification Checks:**
- `uv run --exact pytest -q`
- `uv run --extra langfuse pytest -q`
