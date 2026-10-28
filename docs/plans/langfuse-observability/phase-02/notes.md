# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Used the existing per-runtime `Tracer` holder for job and observation helpers; explicit holder injection into `JobRunner`, `TargetExecutor`, and `AskRegistry` is the minimal runtime wiring needed to share its current replaceable instance.
- Job observation context propagates `session_id` via the SDK `propagate_attributes` helper and pins its root trace with the deterministic job trace ID.

### Spec deviations
- none

### Tradeoffs accepted
- Observability wrappers use guarded context-manager entry/exit so an SDK exception cannot change job control flow.

### Assumptions
- The phase-01 persisted job view exposes result text and result metadata through `JobView.result`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: SDK-present in-memory exporter test first failed because `job_observation` was absent (`AttributeError`), then passed after implementation; it asserts job trace ID, session, prompt/output, job metadata and child parentage.

## Task 2

### Decisions made
- Generation usage comes from `_calculate_attempt_totals(actual_attempt_number)`; missing loaded-state fields are filtered instead of exporting synthesized zeros. Cache names use SDK-verified `input_cached_tokens` and `cache_creation_input_tokens`.
- Recovery invocations remain within their target-attempt generation; policy retries open a new sibling generation.

### Spec deviations
- none

### Tradeoffs accepted
- Attempt input captures the effective prompt at policy-attempt start; a recovery invocation does not create another target-attempt generation.

### Assumptions
- Persisted attempt numbers and TelemetryAccumulator attempt attribution share the same numbering.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: first SDK-present focused run exposed a cancellation-path regression (`JobView.text` did not exist); changed output lookup to `JobView.result.text`. The cancellation characterization plus the in-memory exporter checks then passed.
- Integration assertions verify generation model, effective input, output, attempt-local usage, and that retry generations share the job parent. A Runtime+FakeDrivers integration independently exercises the actual JobRunner/TargetExecutor hook path and verifies the job/generation trace and parent identities; a separate streaming retry integration exercises two actual attempts and verifies sibling parentage.

## Task 3

### Decisions made
- AskRegistry emits question events after publishing outside its lock and answer events only after removing a real pending question.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: test first failed because helper API was absent; SDK-present in-memory integration then verified published question and delivered answer text on the deterministic job trace, with unsuccessful duplicate delivery producing no event.

## Acceptance

- Worker-reported SDK-present subset: 185 passed in 200.94s.
- Worker-reported SDK-absent full suite: 1207 passed, 11 skipped, 15 deselected in 203.64s.
- These worker runs predate coordinator corrections and do not validate the corrected tree.

## Review Fix Cycle 1 — P2 Observation Finalization and Loaded Telemetry

### Decisions
- Added an unconditional finally around entered job and generation observation contexts. Generation fallback update marks cancellation/error before manager exit; job manager exits even when its final database read raises or is cancelled.
- When there are no attempt-local response/cumulative records, derive each independently available measurement from the loaded cumulative value minus its completed-attempt aggregate. Missing fields remain omitted; input cache categories remain exclusive.

### Behavioral TDD evidence
- RED: loaded output-only and cache-only in-memory exporter cases both failed at `tests/test_observability.py:132` with `KeyError: 'langfuse.observation.usage_details'`.
- RED: with context managers deliberately retained to prevent garbage collection, final job-read exception leaked the current job span (`assert not ...is_valid` failed); attempt-finished await cancellation exported no generation; the diagnostics also emitted `Failed to detach context` because cleanup happened in the wrong context.
- GREEN: the loaded output/cache cases export their respective delta-only usage values. Job-read exception and cancellation during final job read both finish the job observation and restore context. Cancellation during the `target.attempt_finished` await exports a generation with WARNING/cancelled and restores context.
- Final SDK-absent full suite: `uv run --exact pytest -q` — 1207 passed, 18 skipped, 15 deselected in 241.88s.
- Final SDK-present required subset: `UV_PROJECT_ENVIRONMENT=/tmp/refract-langfuse-sdk-acceptance uv run --extra langfuse pytest -q tests/test_observability.py tests/test_execution.py tests/test_ask.py` — 192 passed in 229.12s.
- `git diff --check` passed. No credentials/config files or exporter network were used; no Git changes or checkpoints were made.

## Coordinator Corrections

- Missing-helper AttributeErrors above establish API absence, not behavioral RED. Coordinator runtime integrations reproduced real missing usage and leaked session context before correction. Evidence: `b69dc9cd3` and `b78aa63d3`.
- Attempt usage is calculated after execution inside the guarded observation finish helper. Canonical input includes caches; emitted input subtracts reported cache categories to avoid double-counting.
- Nested observations exit before session propagation to restore the previous context.
- Real Runtime integration covers successful jobs, cancellation, SDK helper failure isolation, and streaming retry usage.
- Fresh focused correction checks `bc027e31c`: 19 passed in 8.93s.
- Fresh SDK-present specified subset `b2fe7ab95`: 187 passed in 241.93s.
- Fresh SDK-absent full acceptance `bfdb70111`: 1207 passed, 13 skipped, 15 deselected in 256.56s.
- Independent review `dca8081049ead9ac3bd881b26c480147c` found finalization cleanup and loaded-usage blockers; first fix cycle implemented. Coordinator fresh acceptance and fix-delta re-review remain pending.

## Review Fix Cycle 1

### Decisions made
- Protect job and generation observation exits with unconditional finalization.
- Recover each available loaded usage field independently.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Worker journal records behavioral RED for retained observation contexts on final-read failure and attempt finalization cancellation, plus output-only and cache-only usage omission.
- Added deterministic final-read cancellation coverage and in-memory loaded-measurement assertions, including subtraction of completed-attempt contributions.
- Worker-reported acceptance: SDK-absent 1207 passed, 18 skipped, 15 deselected in 241.88s; SDK-present subset 192 passed in 229.12s.
- Coordinator fresh acceptance `b6e67f48f` passed: SDK-absent 1207 passed, 18 skipped, 15 deselected; SDK-present subset 192 passed. Source stayed unchanged during verification.
- Independent fix-delta review `d89fe1b0fde254b1b4bbec10c86907674` returned PASS at clean checkpoint `b0f726d3485e092633c92985b61b97958033db90`. Both prior blockers resolved; no debt.
