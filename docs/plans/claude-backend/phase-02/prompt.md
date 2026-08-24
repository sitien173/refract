## Original User Request

Integrate Claude Code non-interactive mode as a new OpenMCP backend. Phase 2
wires the Phase 1 adapter into the driver layer.

## Phase

A configured claude target reaches the claude adapter with correctly translated
policy flags, and never reaches the pi adapter.

## Tasks

- task-1: Add `claude` to the backend allowlist in `config.py:384` and the
  execution plan allowlist in `planning.py:81`.
- task-2: Add a `claude` arm to `drivers._target_args`.
- task-3: Replace the bare `else` at `drivers.py:159` with explicit `pi` and
  `claude` branches.
- task-4: Add tests to `tests/test_smoke.py` and `tests/test_config.py`.

## Context

Phase 1 landed `src/openmcp/backends/claude.py` at commit `b85f620`. It exports
`ClaudeParams` and `execute`, and is transport-only. Do not modify it.

Read `docs/plans/claude-backend/DESIGN.md` for the verified CLI facts. Its
"Target field translation" and "Dispatch hazard" sections govern this phase.

### Environment

Run `uv sync --all-extras` before the first test command. Without it pytest
fails with `ModuleNotFoundError: No module named 'openmcp'`. That failure is an
unsynced virtualenv, not a defect in the code.

### Task 1: allowlists

Two literal sets currently read `{"agy", "codex", "pi"}`:

- `src/openmcp/config.py:384`, inside `_targets`
- `src/openmcp/planning.py:81`, inside the execution plan snapshot validator

Add `"claude"` to both. Change nothing else in either file.

### Task 2: argv compilation

Add a `claude` arm to `_target_args` in `src/openmcp/drivers.py`. Follow the
shape of the existing `agy` and `codex` arms, which both end in
`return tuple(args)`. Emit in exactly this order, appended after
`list(target.args)`:

| Condition | Emitted argv |
|---|---|
| `target.isolated` | `--safe-mode`, `--strict-mcp-config` |
| `target.system_prompt` | `--system-prompt`, `<value>` |
| `target.read_only` | `--tools`, `Read,Grep,Glob` |
| `target.model` | `--model`, `<value>` |
| `target.reasoning` | `--effort`, `<value>` |

`backend_profile` has no Claude equivalent. Ignore it. Do not translate it to
any other flag.

Unlike the pi arm, there is no unconditional else-branch flag. The claude
adapter already owns `--permission-mode bypassPermissions`, so nothing is
appended when `isolated` is false.

Leave `validate_target_args` in `config.py` unchanged. Its reserved `--` check
at `config.py:344` and its NUL check already apply to every backend. Claude has
no workspace-root flag to escape, so it needs no backend-specific rule.

### Task 3: dispatch

`DriverRegistry.execute` currently routes `agy`, then `codex`, then falls
through a bare `else` to `pi_execute`. With `claude` now in the allowlist that
`else` would silently run a claude target through the pi adapter.

Replace it with an explicit `elif target.backend == "pi"` arm and an explicit
`claude` arm calling `claude_execute` with `ClaudeParams`, constructed with the
same keyword arguments the other three arms use. Import `ClaudeParams` and
`execute as claude_execute` from `openmcp.backends.claude`, matching the
existing import style at `drivers.py:12-14`.

Every branch must bind `result` before `_normalize(result)` runs. Decide how an
unrecognised backend behaves and state the decision in `notes.md`. Returning a
`DriverResult` with `outcome="TARGET_FATAL"` and `error_code="invalid_args"`
matches how `execute` already reports a rejected target at `drivers.py:130`.
Routing for `agy`, `codex`, and `pi` must be byte-for-byte unchanged.

### Task 4: tests

In `tests/test_smoke.py`, follow
`test_driver_passes_isolated_target_policy_to_pi` and
`test_driver_compiles_agy_and_codex_target_configuration` as models. Both
monkeypatch the module-level executor and assert the full `params.args` tuple.

Cover:

- an isolated claude target, asserting the full compiled argv tuple
- a read-only claude target, asserting `--tools Read,Grep,Glob`
- a claude target with `model` and `reasoning`, asserting `--model` and
  `--effort`
- a claude target dispatching to the claude executor and not to pi. Patch both
  `claude_execute` and `pi_execute`, and assert the pi fake was never called.

Carried from the Phase 1 review, LOW severity: add an argv assertion covering
`--resume`. `ClaudeParams` with a non-empty `SESSION_ID` must produce argv
containing `--resume <session_id>` before the `--` separator. Put it with the
other claude argv tests.

In `tests/test_config.py`, extend the `test_config_rejects_reserved_target_args`
parametrize list at line 503 with `("claude", ("--",))`. Note that this case
passes against unmodified `validate_target_args`; it is a regression guard, so
do not change production code to make it pass.

Also assert that a TOML target with `backend = "claude"` loads without error,
following the existing config-loading tests in that file.

## Files

- `src/openmcp/config.py`
- `src/openmcp/planning.py`
- `src/openmcp/drivers.py`
- `tests/test_config.py`
- `tests/test_smoke.py`

## Done When

- A TOML target with `backend = "claude"` loads without error.
- An execution plan snapshot round-trips a claude target.
- An isolated claude target emits `--safe-mode` and `--strict-mcp-config`.
- A read-only claude target emits `--tools Read,Grep,Glob`.
- `model` becomes `--model`, `reasoning` becomes `--effort`.
- A claude target dispatches to the claude executor and never to pi.
- `validate_target_args("unsafe", "claude", ("--",))` raises `ValueError`.
- `uv run pytest tests/test_config.py tests/test_smoke.py tests/test_planning.py -q`
- `uv run pytest -q`

## Known pre-existing failures

`tests/test_server.py` has four failures that predate this plan and reproduce at
`7a59db2`. Commit `7a59db2` raised the `job_wait` timeout from 30 to 300 without
updating `test_job_wait_bounds_public_timeout` or
`test_mcp_exposes_direct_job_contract`. They are out of scope. Do not fix them.
Expect `uv run pytest -q` to report those four failures and nothing else red.

## Rules

Stay within scope. Do not modify `src/openmcp/backends/`, `backend_runner.py`,
or `server.py`; those belong to Phase 3. Do not modify `CLI_ARGUMENTS.md` or
`README.md`; those belong to Phase 4. Do not add a field to `TargetConfig`. Do
not change `validate_target_args`. Maintain this phase's `notes.md` and
`journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
