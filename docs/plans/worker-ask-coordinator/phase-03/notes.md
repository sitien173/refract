<!-- refract-shared-version: 2.0.0 -->

# Phase 3 Decision Notes

## Task 1

### Decisions made
- Continued directly after the user cancelled implementation job `f6caa2a4-7f0e-4a25-b97e-866e5db26a87` and requested direct handling.
- Preserved its seven CLI regression tests and bounded their HTTP server threads.
- Added `refract ask` using standard-library HTTP before daemon config loading.
- Printed HTTP status and generic transport/parse errors without echoing response bodies or token values.
- Kept the blocking request governed by the server ask timeout instead of imposing a shorter fixed client deadline.

### Spec deviations
- Independent review waived by the user. Direct implementation authorized.

### Tradeoffs accepted
- none

### Assumptions
- Worker environment supplies the daemon ask URL and token.

### Follow-ups for human
- none

### Test evidence
- RED: `cd server && uv run pytest -q tests/test_smoke.py -k 'test_ask_'`; 6 failed, 1 passed, 59 deselected in 6.00s. Missing command produced `invalid choice: 'ask'`; successful-answer and timeout assertions observed exit 2 rather than 0. Background task `be0cee995` retained output.
- GREEN: same command; 7 passed, 59 deselected in 0.24s after implementation.
- LSP checked CLI and smoke tests. Corrected new handler signature diagnostics and the new invalid-answer exception type. Existing logging protocol typing errors, old smoke-test typing errors and unrelated lint warnings remain outside this phase.
- Root cause: ask subcommand and HTTP client were absent.

## Task 2

### Decisions made
- Worker contract asks only about unresolved decisions and falls back to BLOCKED on command failure.
- Coordinator Gate 2 answers pending_question through job_answer and resumes job_wait on the same ID.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- `bash plugin/tests/run.sh` passed: session-start tests, contract tests, both manifest validations; 3 existing Antigravity warnings.
- `cd server && uv run pytest -q` passed: 627 passed, 11 deselected in 161.35s. New live cases were excluded as intended. The current-tree rerun after test import formatting changes timed out after 300s, exit 143, with no failure reported before termination. A bounded 600s `cd server && uv run pytest -vv` diagnostic rerun then passed: 627 passed, 11 deselected in 132.84s, exit 0. Latest-tree validation passed; the intervening timeout remains unexplained and is not claimed fixed.
- Root cause: n/a.

## Task 3

### Decisions made
- Added eight live-marked target-policy probes using DriverRegistry, temporary workspaces, injected env and an ephemeral loopback listener.
- Required a valid token and exact question at the listener, then an exact random answer absent from the worker prompt.
- Used 90-second backend deadlines. Recorded explicit BLOCKED fallbacks as xfail, never as successful reachability.
- Documented all eight initial outcomes and the Codex prerequisite failure in server/CLI_ARGUMENTS.md.
- Did not alter credentials, backend configuration, daemon state, target permissions, or dependencies.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- All four CLI executables were found on PATH. Codex startup requires a valid inherited CODEX_HOME directory.
- Codex/Agy read_only target fields currently add no restrictions; documented this existing driver limitation without changing drivers.

### Follow-ups for human
- none

### Test evidence
- Initial run: `cd server && uv run pytest -m live -k test_live_ask_coordinator tests/test_live_backends.py -v -s --tb=no`; 4 passed, 2 xfailed, 2 failed, 3 deselected in 113.05s. Claude/Agy/Pi normal and Agy read_only reached the listener and returned exact answers. Claude/Pi read_only returned BLOCKED without reaching it. Both Codex modes failed before creating a session.
- Diagnostic rerun: `cd server && uv run pytest -m live -k 'test_live_ask_coordinator and codex' tests/test_live_backends.py -v -s --tb=short`; 2 failed, 9 deselected in 1.17s, outcome RETRYABLE, listener not reached.
- H1: Codex startup prerequisite is invalid. Predict: an ask-free direct invocation fails before model startup. Confirmed: `printf '%s\\n' 'Reply with PONG.' | codex exec --cd /tmp --yolo --json -` exited 1 and reported that inherited CODEX_HOME does not exist. `codex --version` reported codex-cli 0.160.1.
- No production fix attempted: backend home/config changes are outside the authorized scope.
- Final probe command: `cd server && uv run pytest -m live -k test_live_ask_coordinator tests/test_live_backends.py -v -s -rx --tb=short`; 4 passed, 2 xfailed, 2 failed, 3 deselected in 111.78s. Reproduced all eight outcomes. Both Codex failures explicitly named the missing inherited CODEX_HOME directory. Quality remains WAIVED.
- The user subsequently instructed "skip live probe test." Further live verification is WAIVED, including unavailable Codex evidence. Prior failures and fallbacks remain recorded accurately. This resolves the acceptance blocker without changing credentials/configuration or claiming Codex reachability.
- Root cause: inherited Codex home points to a nonexistent directory, before ask execution. This does not establish Codex env passthrough or loopback reachability.
