# Phase 1 - Decision Notes

## Task 1
### Decisions made (not in spec)
- Used a dedicated `tests/test_notify.py` file to keep the new notification behavior isolated from the existing smoke suite while the feature is being introduced.

### Spec deviations
- none

### Tradeoffs accepted
- The tests assert concrete notification message strings so the production wrapper has a stable external contract instead of an underspecified payload.

### Assumptions
- `py-notify-system` exposes a top-level synchronous `notify()` function imported from `notify_system`.

### Follow-ups for human
- none

### Test evidence (RED->GREEN, or root cause for a fix)
- RED: `rtk uv run pytest tests/test_notify.py -v` failed with `ModuleNotFoundError: No module named 'openmcp.notify'` across all 6 tests.
- GREEN: after implementing the wrapper in Task 2, `rtk uv run pytest tests/test_notify.py -v` passed with `6 passed`.

## Task 2
### Decisions made (not in spec)
- Reused `server._effective_env()` and `server._env_truthy()` lazily inside the notify wrapper so notification config follows the existing env precedence without duplicating parsing logic.

### Spec deviations
- none

### Tradeoffs accepted
- The optional dependency is cached after the first import attempt to avoid repeated import failures and repeated logging during a run.

### Assumptions
- Notification delivery defaults to `desktop=True`, `webhook=False`, and `sound=False` when the corresponding env vars are unset.

### Follow-ups for human
- none

### Test evidence (RED->GREEN, or root cause for a fix)
- GREEN: `rtk uv run pytest tests/test_notify.py -v` passed with `6 passed` after adding `src/openmcp/notify.py`.

## Task 3
### Decisions made (not in spec)
- Kept retry notifications inside `run_with_retry()` so attempt-failed events reflect the actual retry loop rather than reconstructed state in `run()`.
- Emitted final success/error notifications from `run()` using the retry payload before any later response-pipeline changes, matching the phase requirement for pre-compression state.

### Spec deviations
- none

### Tradeoffs accepted
- Added `tool.hatch.metadata.allow-direct-references = true` because the new `notify` extra uses a direct git dependency and Hatch refuses to build without the explicit opt-in.

### Assumptions
- Using `result.SESSION_ID` when available is the correct session identifier to surface for retry notifications and final run notifications.

### Follow-ups for human
- none

### Test evidence (RED->GREEN, or root cause for a fix)
- RED: after adding the `notify` extra, `rtk uv run pytest tests/test_notify.py -v` failed during editable build because Hatch rejected the direct git reference without `allow-direct-references = true`.
- GREEN: after enabling direct references and wiring the hooks, the notify test file built and executed successfully again.

## Task 4
### Decisions made (not in spec)
- Put the run-level integration checks in `tests/test_notify.py` instead of the existing smoke file so the phase-specific coverage stays grouped with the new feature.

### Spec deviations
- none

### Tradeoffs accepted
- The integration tests pin environment variables such as `OPENMCP_CODEX_MODEL_DEFAULT` and `OPENMCP_GEMINI_ROUTE_TO_AGY` to avoid host-environment flakiness while still exercising the real `run()` path.
- The existing smoke suite needed the same env pin for `OPENMCP_GEMINI_ROUTE_TO_AGY` so the full offline suite remains deterministic under developer machines that set that env globally.

### Assumptions
- A byte-identical regression guard for default-disabled behavior is adequately represented by asserting the returned `run()` payload remains exactly unchanged.

### Follow-ups for human
- none

### Test evidence (RED->GREEN, or root cause for a fix)
- RED: the first integration-test run failed because the host environment supplied a codex default model and gemini routing env, changing the observed notification context.
- GREEN: after pinning those env vars inside the tests, `rtk uv run pytest tests/test_notify.py -v` passed with `10 passed`.
- GREEN: `rtk uv run pytest` initially failed in `tests/test_smoke.py::test_env_defaults_applied_for_gemini_model` for the same gemini-routing env leak; after pinning `OPENMCP_GEMINI_ROUTE_TO_AGY=false` in that test, the full offline suite passed with `44 passed, 4 deselected`.
