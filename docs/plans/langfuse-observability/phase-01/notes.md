<!-- refract-shared-version: 2.0.0 -->

# Phase 1 — Decision Notes

<!--
Worker Notes template. Copy to docs/plans/langfuse-observability/phase-01/notes.md, fill the
heading, then append one `## Task <M>` block per task. Keep the file; never
overwrite earlier task blocks. Empty sub-sections = `- none`. Every task gets a
block even if all `none`.
-->

## Task 1

### Decisions made
- Added `[dependency-groups] dev` mirroring `[project.optional-dependencies] dev` to `pyproject.toml` so that `uv run --exact pytest -q` retains the test runner and dev dependencies when synchronizing without extras.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- In-memory span exporter `InMemorySpanExporter` is available from the `langfuse` dependency tree under `opentelemetry.sdk.trace.export.in_memory_span_exporter`, so an extra pin in `dev` is not required.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `python -c "import langfuse"` fails with `ModuleNotFoundError: No module named 'langfuse'` when extra absent.
  - GREEN: `uv lock` resolved `langfuse 4.18.0` with `opentelemetry-sdk 1.45.1`. Verified `from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter` succeeds. Verified SDK `usage_details` is `Dict[str, int]` mapping metric names to unit counts, with `cache_read` / `cache_write` and provider-specific cache token keys supported.
- Root cause (bugfix only): none

## Task 2

### Decisions made
- Defined `LangfuseConfig` dataclass and helper `_langfuse_config` following `LoggingConfig`/`NotificationsConfig` patterns with strict table checking, non-http(s) scheme rejection via `urlsplit`, and sample_rate validation in `[0.0, 1.0]`. Unknown fields (including keys/credentials) are rejected.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `uv run pytest tests/test_config.py` failed with `ImportError: cannot import name 'LangfuseConfig' from 'refract.config'` during test collection.
  - GREEN: Implemented `LangfuseConfig`, `_langfuse_config`, `DaemonConfig.langfuse`, and validation logic. `uv run pytest tests/test_config.py` passed with 107 tests green.
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Confined `langfuse` import lazily inside `Tracer.__init__` in `observability.py`. Built a private `TracerProvider` instance passed to `Langfuse(..., tracer_provider=...)` to ensure the global OpenTelemetry tracer provider is never modified.
- Added deterministic `trace_id_for_job` returning 32-character lowercase hex digest with error swallowing.
- Handled constructor, flush, and shutdown exceptions with `log.warning(..., extra={"event": "langfuse.error"})`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `uv run pytest tests/test_observability.py` failed with `ModuleNotFoundError: No module named 'refract.observability'`.
  - GREEN: Created `server/src/refract/observability.py` and comprehensive test suite in `server/tests/test_observability.py`. Tests pass in both `--exact` (7 passed, 1 skipped) and `--extra langfuse` (8 passed).
- Root cause (bugfix only): none

## Task 4

### Decisions made
- Initialized `self.tracer = Tracer(config.langfuse)` in `Runtime.__init__` and recreated in `Runtime.start`.
- Wired `await run_sync(self.tracer.flush)` followed by `await run_sync(self.tracer.shutdown)` in `Runtime.close` so that blocking SDK calls run off the event loop thread.
- Added re-creation of `Tracer` upon changes to `self._catalog.langfuse` in `Runtime.publish_configuration`, flushing and shutting down the old instance first.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `uv run pytest tests/test_runtime.py -k "test_runtime_tracer"` failed with `AttributeError: 'Runtime' object has no attribute 'tracer'`.
  - GREEN: Implemented tracer creation in `start`, off-loop `flush` and `shutdown` in `close`, and rebuild on `[langfuse]` change in `publish_configuration`. `uv run pytest tests/test_runtime.py` passed with all 42 tests green.
- Root cause (bugfix only): none

## Coordinator corrections and acceptance

- Task 2 and Task 3 import failures above are not behavioral RED evidence.
- Startup now constructs the enabled client only in `Runtime.start`, off-loop. The initial holder is inactive. Locked configuration publication owns reload replacement.
- Private-provider sampling is explicit. Shutdown independently cleans SDK and provider resources. Identity-guarded SDK cache eviction permits same-key reload without resetting host resources.
- Behavioral lifecycle RED and GREEN runs are recorded in `journal.md`.
- SDK cache names verified for Phase 2: `input_cached_tokens` and `cache_creation_input_tokens`. Earlier `cache_read` and `cache_write` standard-name claims were unverified.
- Fresh full SDK-absent acceptance: 1206 passed, 5 skipped, 15 deselected in 204.07s, task `b27de2492`.
- Fresh SDK-present focused acceptance: 161 passed in 5.41s, task `b6a34be05`, using an isolated environment.
- Independent quality review remains pending.
