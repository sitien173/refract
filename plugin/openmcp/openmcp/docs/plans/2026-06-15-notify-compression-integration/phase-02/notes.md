# Phase 2 - Decision Notes

## Task 1
### Decisions made (not in spec)
- Kept the compression-specific unit and integration checks in a dedicated `tests/test_compression.py` file so the lossy-response behavior stays isolated from the existing smoke and notify suites.

### Spec deviations
- none

### Tradeoffs accepted
- The ERP fixture is asserted as a byte-sensitive string rather than a looser structural parser so the tests directly guard the coordinator-scanned lines against accidental mutation.

### Assumptions
- `thetokencompany.AsyncTheTokenCompany` is the async entrypoint the optional dependency exposes for response compression.

### Follow-ups for human
- none

### Test evidence (RED->GREEN, or root cause for a fix)
- RED: `rtk uv run pytest tests/test_compression.py -v` failed with `ModuleNotFoundError: No module named 'openmcp.compression'` across the new compression tests and with `AttributeError` because `openmcp.server` did not yet expose `compress_response`.

## Task 2
### Decisions made (not in spec)
- Reused `server._env_truthy()` lazily instead of duplicating the repo’s truthy parsing, so compression and notification gating stay aligned.
- Opened a single `AsyncTheTokenCompany` client per compression request and reused it across both ERP sections rather than reconnecting once per section.

### Spec deviations
- none

### Tradeoffs accepted
- The ERP parser is intentionally line-oriented and conservative: it only rewrites bodies under explicit `## SUMMARY` and `## NOTES` headers and otherwise leaves the response verbatim.

### Assumptions
- Falling back to the original text when `result.output` is empty is the right best-effort behavior for lossy compression failures.

### Follow-ups for human
- none

### Test evidence (RED->GREEN, or root cause for a fix)
- Partial GREEN: after adding `src/openmcp/compression.py`, `rtk uv run pytest tests/test_compression.py -v` passed all direct `compress_response()` tests; the only remaining failure was the expected task-3 hook gap in `openmcp.server` (`AttributeError: ... has no attribute 'compress_response'`).

## Task 3
### Decisions made (not in spec)
- Applied compression after the final notify event and immediately before building the `run()` response dict, so notifications still reflect the pre-compression worker output as required by the plan.

### Spec deviations
- none

### Tradeoffs accepted
- The optional dependency is still installed from git, which required a direct-reference package name that matches upstream metadata exactly (`the-token-company`).

### Assumptions
- Compressing failed-run `agent_messages` is acceptable because the phase goal is scoped to the returned response text, and best-effort fallback preserves the original on any compressor problem.

### Follow-ups for human
- none

### Test evidence (RED->GREEN, or root cause for a fix)
- RED: the first task-3 test run failed during dependency resolution because the optional extra used the import name `thetokencompany`, but the upstream package metadata name is `the-token-company`.
- GREEN: after fixing the extra name and wiring `compress_response()` into `run()`, `rtk uv run pytest tests/test_compression.py -v` passed with `9 passed`.

## Task 4
### Decisions made (not in spec)
- Strengthened the `run()` integration test to assert both env passthrough and prompt isolation, so the phase verifies that only returned `agent_messages` flow into compression.

### Spec deviations
- none

### Tradeoffs accepted
- The integration assertion uses a monkeypatched `compress_response()` boundary instead of the real compressor because the phase contract explicitly wants offline, deterministic tests.

### Assumptions
- Capturing `params.PROMPT` inside the fake retry path is sufficient evidence that `run()` did not substitute the prompt text into the compressor input.

### Follow-ups for human
- none

### Test evidence (RED->GREEN, or root cause for a fix)
- GREEN: after refining the integration assertion, `rtk uv run pytest tests/test_compression.py -v` still passed with `9 passed`.
