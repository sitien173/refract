<!-- refract-shared-version: 2.0.0 -->

# Phase 1 — Decision Notes

## Coordinator

### Spec deviations
- Phase file set widened beyond PLAN.md: `server/src/refract/drivers.py` and
  `server/src/refract/backends/{codex,claude,agy,pi}.py`. `BackendParams` is
  built in `drivers.py:274` and each backend wraps the stream helper with its
  own keyword list, so env injection cannot reach `Popen` otherwise.

## Task 1

### Decisions made
- Used `secrets.token_urlsafe(32)` for generated job tokens.
- Stored revoked tokens in a set to distinguish revoked from unknown tokens while rejecting both with `AskAuthError`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Token validation compares all active and revoked candidates with `secrets.compare_digest`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest -q tests/test_ask.py` failed with `ModuleNotFoundError: No module named 'refract.ask'`, then passed 6 tests after implementing `AskRegistry`.
- Root cause (bugfix only): none

## Task 2

### Decisions made
- Set `DEFAULT_ASK_TIMEOUT_S = 300` as the positive integer default.
- Added `ask_timeout_s` to allowed `[daemon]` keys and validated via `_positive_int`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Valid `ask_timeout_s` values are integers >= 1; booleans, non-integers, and values < 1 are rejected.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest -q tests/test_config.py -k test_ask_timeout_s` failed with `AttributeError` and regex mismatches, then passed all 7 tests after adding `DEFAULT_ASK_TIMEOUT_S` and `[daemon].ask_timeout_s` validation.
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Implemented `POST /ask` guarded by `_loopback_route` in `dashboard.py`.
- Checked for empty / malformed body and empty question returning 400.
- Resolved token to job ID with 403 on unknown, revoked, or wrong-job token; returned 409 when a question is already pending.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Event loop remains unblocked during wait by using async wait on `AskRegistry.ask`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest -q tests/test_dashboard.py -k test_ask_` failed with 404 (route missing) and `AttributeError` (`ask_registry` missing on Runtime), then passed all 6 tests after implementing route and runtime ownership.
- Root cause (bugfix only): none

## Task 4

### Decisions made
- Threaded `env` mapping through `BackendParams`, `consume_stream`, `stream_shell_command_lines`, backend wrappers (`codex`, `claude`, `agy`, `pi`), `DriverRegistry.execute`, and `TargetExecutor._run_target_invocation`.
- Merged `env` into inherited `os.environ` in `_shell.py` at `subprocess.Popen`.
- Issued `REFRACT_ASK_TOKEN` bound to `job_id` and formatted `REFRACT_ASK_URL` at start of attempt; revoked token in `finally` block of `TargetExecutor._execute_attempt`.
- Added pending ask cancellation to `Runtime.cancel(job_id)`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Subprocess environment receives exact `REFRACT_ASK_URL` and `REFRACT_ASK_TOKEN` merged with `os.environ`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest -q tests/test_ask.py` failed on `test_stream_shell_command_lines_injects_env` with missing `env` kwarg, then passed 9 tests after threading env through execution path and adding lifecycle management.
- Root cause (bugfix only): none

## Fix 1

### Decisions made
- Made token validation and pending question registration atomic under a single `self._lock` acquisition in `AskRegistry.ask`.
- Added internal `_validate_token_locked` helper reused by `validate_token` and `ask`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest -q tests/test_ask.py -k test_ask_atomic_validation_and_registration` failed with `Failed: DID NOT RAISE AskAuthError` when token was revoked between validation and registration, then passed after making validation and registration atomic under `self._lock`.
- Root cause (bugfix only): `AskRegistry.ask` previously called `self.validate_token` under its own lock acquisition and released it before acquiring `self._lock` again to register `self._pending`, creating a race window where `revoke_token` could leave a revoked job registered.

## Fix 2

### Decisions made
- Track each active token's monotonic workflow deadline from attempt start; AskRegistry bounds the configured ask timeout by the remaining workflow time, while timeout_s=0 stays unlimited.
- Runtime cancellation now uses token revocation, which atomically invalidates the token and releases any pending question.
- Compare UTF-8 bytes with `secrets.compare_digest` for token and job identifiers so Unicode input remains a normal authentication failure.
- Replaced the global BackendParams environment side table and custom init with a normal `env` dataclass field using `repr=False`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- `TargetSelection.timeout_s` is the finite worker invocation timeout; its deadline begins at attempt start, conservatively accounting for pre-invocation work.

### Follow-ups for human
- none

### Test evidence
- RED: `cd server && uv run pytest -q tests/test_ask.py::test_ask_timeout_is_bounded_by_workflow_deadline tests/test_ask.py::test_ask_timeout_preserves_unlimited_workflow_and_configured_cap tests/test_ask.py::test_runtime_cancel_releases_pending_ask tests/test_dashboard.py::test_ask_token_auth_and_wrong_job tests/test_smoke.py::test_backend_params_are_transport_only` failed all 5 regressions: unsupported deadline argument, post-cancel ask remained authorized, Unicode token comparison raised `TypeError`, and `env` was absent from dataclass fields. The dashboard traceback showed `secrets.compare_digest` rejecting the Unicode token.
- GREEN: the same focused regression command passed 5 tests after the fix; expanded ask/backend focused run passed 18 tests.
- Full verification: `cd /home/ngosi/projects/refract/server && uv run pytest -q` passed: 609 passed, 3 deselected in 225.68s. First run was stopped by the 180s tool timeout after 70%; rerun completed successfully. `cd /home/ngosi/projects/refract && bash plugin/tests/run.sh` passed (manifest validation, session-start tests, and contract tests; validator emitted three existing warnings).

## Fix 3

### Decisions made
- Handled UTF-8 encoding failures for token and job identifiers.
- Mapped `UnicodeEncodeError` directly to `AskAuthError`.
- Preserved constant-time comparison for all valid UTF-8 candidates.
- Added route regressions for escaped surrogate token and wrong-job values.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Escaped surrogates in JSON parse to lone surrogate code points.

### Follow-ups for human
- none

### Test evidence
- RED: `cd server && uv run pytest -q tests/test_dashboard.py -k test_ask_token_auth_and_wrong_job tests/test_ask.py -k test_issue_token_and_validate` failed with `UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800' in position 0: surrogates not allowed` in `src/refract/ask.py:90`.
- GREEN: `cd server && uv run pytest -q tests/test_dashboard.py -k test_ask_token_auth_and_wrong_job tests/test_ask.py -k test_issue_token_and_validate` passed.
- Root cause (bugfix only): Strict `.encode("utf-8")` on strings with lone surrogates raised `UnicodeEncodeError`. Unhandled exceptions bypassed `AskAuthError` handling in the dashboard route.
- Full verification: `cd /home/ngosi/projects/refract/server && uv run pytest -q` passed with 609 passed. `cd /home/ngosi/projects/refract && bash plugin/tests/run.sh` passed with 0 errors.

