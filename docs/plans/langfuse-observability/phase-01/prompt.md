## User Request
Complete the confirmed langfuse-observability plan, Phase 1 only in this job.

## Phase
Optional Langfuse client with config and runtime lifecycle.

## Tasks, Files, and Done When
The following phase specification is authoritative:

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


## Context
Read /home/ngosi/projects/refract/docs/plans/langfuse-observability/DESIGN.md and PLAN.md. Existing clean HEAD was 758fc975639586bb5b71515981a40c4680189f96. The plan base is refs/plans/langfuse-observability/base.
Verify actual Langfuse v4 SDK APIs and usage token keys from installed source, not guessed names. Use Context7 current docs. A prior design API citation is not implementation evidence.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
Use TDD with credible behavior-failure RED and GREEN evidence. Keep tests isolated from real exporter network activity.
Never read or write credential files, .env*, ~/.config, or daemon home configuration. Do not print environment secrets.
No Git commits, resets, stashes, branch changes, or ref edits. Coordinator owns Git.
Only declared source/test files and this phase's notes.md and journal.md may change. Do not edit PLAN.md, DESIGN.md, prompt.md, or .handover.md.
Ask through refract ask for unresolved specification conflicts. Do not silently weaken acceptance criteria.

## Response Format
Return the ERP # EXTERNAL RESPONSE block and matching status line.
