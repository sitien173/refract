## Original User Request

Integrate Claude Code non-interactive mode as a new OpenMCP backend. Phase 3
extends the legacy direct-invocation API to accept `claude`.

## Phase

`run("claude", ...)` works through both the compatibility runner and the server
entry point, and a live smoke test can exercise the real CLI.

## Tasks

- task-1: Extend `BackendName`, add a `claude_executor` parameter, and replace
  the bare `else` at `backend_runner.py:90`.
- task-2: Update the `run` signature and executor injection in `server.py`.
- task-3: Verify the imports and transport-only params assertions already cover
  claude.
- task-4: Add a `@pytest.mark.live` PONG test for the claude adapter.

## Context

Phases 1 and 2 are committed and reviewed. `src/openmcp/backends/claude.py`
exports `ClaudeParams` and `execute`. `drivers.py` already dispatches claude
explicitly. Do not modify either file.

Read `docs/plans/claude-backend/DESIGN.md` for the verified CLI facts.

### Environment

Run `uv sync --all-extras` before the first test command. Without it pytest
fails with `ModuleNotFoundError: No module named 'openmcp'`.

### Task 1: the compatibility runner

In `src/openmcp/backend_runner.py`:

- Line 19: `BackendName = Literal["agy", "codex", "pi"]` gains `"claude"`.
- Line 13 area: import `ClaudeParams` and `execute as claude_execute` from
  `openmcp.backends.claude`, matching the existing import style.
- Line 49 area: add a keyword-only `claude_executor` parameter defaulting to
  `claude_execute`, alongside the three existing executor parameters.
- Line 90: replace the bare `else` with an explicit
  `elif backend == "pi"` arm and an explicit `claude` arm.

The `claude` arm constructs `ClaudeParams(PROMPT=..., cd=cd_path,
SESSION_ID=..., timeout_s=...)`. It passes no `args`. The adapter already owns
its transport flags, and the docstring at `backend_runner.py:51` states that
target policy is deliberately absent from this runner. Do not compile any policy
flags here.

The pi arm keeps `args=("--approve",)` exactly as it is today. Do not disturb it.

Every branch must bind `backend_result` before the `outcome == "OK"` check at
line 100. Decide how an unrecognised backend behaves and state the decision in
`notes.md`. `drivers.py` handles the same case by returning a failure rather
than falling through; the runner returns a plain dict, so an equivalent failure
dict with a `success: False` and an `error` naming the backend is consistent
with the shape returned at `backend_runner.py:59`.

### Task 2: the server entry point

In `src/openmcp/server.py`:

- Line 62: the `Literal["agy", "codex", "pi"]` annotation on `run` gains
  `"claude"`.
- Line 64: pass `claude_executor=claude_execute` alongside the three existing
  executor keyword arguments, and add the matching import near line 20.

`test_tool_signature` at `tests/test_smoke.py:327` asserts the parameter names
of `server.run`. Those names do not change, so that test must keep passing
untouched.

### Task 3: verify, do not duplicate

Phase 1 already added `import openmcp.backends.claude` to `test_imports` at
`tests/test_smoke.py:41` and `ClaudeParams` to
`test_backend_params_are_transport_only` at `tests/test_smoke.py:46`. Confirm
both still hold. Add nothing. If they already pass, record that in `notes.md`
and move on.

### Task 4: tests

In `tests/test_smoke.py`, add coverage that `run("claude", ...)` reaches the
claude executor:

- Call `openmcp.backend_runner.run` with `backend="claude"` and injected fake
  executors for both `claude_executor` and `pi_executor`.
- Assert the claude fake received a `ClaudeParams` instance carrying the prompt,
  cd, and session id.
- Assert the pi fake was never called.
- Assert the returned dict has `success: True` and the session id from the
  backend result.

Add one test that an unrecognised backend name does not reach pi, matching
whatever fallback you chose in task 1.

In `tests/test_live_backends.py`, add a claude test following the existing
`test_live_agy_execute` and `test_live_codex_execute`. Use the module `PROMPT`
constant and the shared `_assert_live_result` helper, which already skips on
`missing_cli` and `bad_cd` and asserts a non-empty `SESSION_ID`. Mark it
`@pytest.mark.live` and `@pytest.mark.asyncio`.

## Files

- `src/openmcp/backend_runner.py`
- `src/openmcp/server.py`
- `tests/test_smoke.py`
- `tests/test_live_backends.py`

## Done When

- `run("claude", prompt, cd)` invokes the claude executor with a `ClaudeParams`
  instance.
- The agy, codex, and pi arms behave exactly as before.
- `openmcp.server.run` accepts `"claude"` without a type error.
- `uv run pytest -q`
- `uv run pytest -m live -k claude`

The live command must pass when `claude` is installed and skip cleanly when it
is not. `claude` 2.1.220 is installed in this environment, so expect it to run
for real rather than skip.

## Known pre-existing failures

`tests/test_server.py` has four failures that predate this plan and reproduce at
`7a59db2`. Commit `7a59db2` raised the `job_wait` timeout from 30 to 300 without
updating `test_job_wait_bounds_public_timeout` or
`test_mcp_exposes_direct_job_contract`. Out of scope. Do not fix them. Expect
`uv run pytest -q` to report those four and nothing else red.

## Rules

Stay within scope. Do not modify `src/openmcp/backends/`, `drivers.py`,
`config.py`, or `planning.py`; those are finished. Do not modify
`CLI_ARGUMENTS.md` or `README.md`; those belong to Phase 4. Do not add target
policy to the compatibility runner. Maintain this phase's `notes.md` and
`journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
