# Plan: Add the `claude` Backend

Design: [DESIGN.md](DESIGN.md)

Adds Claude Code as a fourth backend behind the existing transport contract.
Phases move outward from the adapter to the driver, then to the direct
invocation API, then to documentation. Each phase leaves the tree green.

---

### Phase 1: Claude adapter executes and parses print-mode JSON

**Task Guide Input:** Add a new transport-only backend adapter module for the
Claude Code CLI in a Python daemon that already has three sibling adapters. The
module runs `claude` in non-interactive print mode, assembles argv with an
end-of-options separator, parses a single-line JSON result object, resolves the
session identifier, and maps subprocess failures onto the shared backend result
classifier. Distinct use cases are new-session execution, resumed-session
execution, timeout, cancellation, non-zero exit, and an error result carrying a
zero exit status.

**Goal:** `claude_execute` returns a correct `BackendResult` for every documented
outcome, without any wiring into the driver.

**Files:**
- Create: `src/openmcp/backends/claude.py`
- Modify: `tests/test_smoke.py`

**Tasks:**
1. Add `ClaudeParams` with the same transport-only fields as `PiParams`, plus a
   `run_shell_command` wrapper over `stream_shell_command_lines` using
   `executable_name="claude"` and `check_returncode=True`.
2. Assemble argv as `["claude", *params.args, "-p", "--permission-mode",
   "bypassPermissions", "--output-format", "json"]`, append
   `["--resume", SESSION_ID]` when a session exists, then append `"--"` and the
   prompt. Transport flags must follow target args.
3. Parse stdout lines, keep the last JSON object whose `type` is `result`, and
   extract `result` as `agent_messages` and `session_id`. Treat `is_error` true
   or a non-`success` `subtype` as error text built from `result` and
   `api_error_status`. Collect undecodable lines as diagnostics. Fall back to
   `params.SESSION_ID` when the result omits one.
4. Map failures to `bad_cd`, `missing_cli`, `timeout`, `execution_error`, and
   `cancelled`, then classify through `classify_backend_output` with
   `backend_name="claude"`. Add unit tests in `tests/test_smoke.py` covering a
   success result, an `is_error` result, a result missing `session_id`,
   interleaved non-JSON diagnostics, a non-zero exit despite agent output, and a
   bad working directory.

**Acceptance Criteria:**
- `claude.py` imports cleanly and exports `ClaudeParams` and `execute`.
- `ClaudeParams` carries only transport fields and no policy fields.
- A success result yields `outcome="OK"` with non-empty `agent_messages` and the
  `session_id` from the result object.
- An `is_error` result yields `outcome="FATAL"`.
- A missing `session_id` falls back to the input `SESSION_ID`.
- A non-zero exit yields `outcome="FATAL"` with `error_class="execution_error"`
  even when agent output was produced.
- A non-existent working directory yields `error_class="bad_cd"`.
- Argv places `--` immediately before the prompt.

**Reviewer Checklist:**
- The prompt is passed as a single argv token and is never pre-escaped.
- Transport flags appear after `params.args` so a target cannot replace
  `--output-format`.
- Log statements record metadata only and never the prompt or full argv, as in
  `pi.py:133` and `codex.py:267`.
- Only the last `type: result` object is used when several are present.
- `cancel_event` is checked after streaming, matching `pi.py:182`.

**Verification Checks:**
- `uv run pytest tests/test_smoke.py -q`
- `uv run python -c "import openmcp.backends.claude"`

**Commit:** `feat(backends): add claude print-mode adapter`

---

### Phase 2: Driver compiles claude argv and dispatches explicitly

**Goal:** A configured claude target reaches the claude adapter with correctly
translated policy flags, and never reaches the pi adapter.

**Task Guide Input:** Wire an already-implemented backend adapter into a Python
orchestration daemon's driver layer. Add the backend name to two configuration
allowlists, compile first-class target policy fields into backend argv inside the
existing translation function, and replace a bare else-branch dispatch that
would otherwise route the new backend to the wrong adapter. Distinct use cases
are an isolated target, a read-only target, a target with model and reasoning
set, and a target that must not fall through to the previous default adapter.

**Files:**
- Modify: `src/openmcp/config.py`
- Modify: `src/openmcp/planning.py`
- Modify: `src/openmcp/drivers.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_smoke.py`

**Tasks:**
1. Add `claude` to the backend allowlist in `config.py:384` and the execution
   plan allowlist in `planning.py:81`.
2. Add a `claude` arm to `drivers._target_args` emitting, in order,
   `--safe-mode --strict-mcp-config` when `isolated`, `--system-prompt` when
   set, `--tools Read,Grep,Glob` when `read_only`, `--model` when set, and
   `--effort` when `reasoning` is set. Leave `validate_target_args` unchanged and
   ignore `backend_profile`.
3. Replace the bare `else` at `drivers.py:159` with explicit `pi` and `claude`
   branches so no backend can silently reach the wrong adapter.
4. Add tests asserting the full compiled argv for isolated, read-only, and
   model-plus-reasoning claude targets, that a claude target invokes the claude
   executor rather than pi, and that `("claude", ("--",))` is rejected by
   `validate_target_args`.

**Acceptance Criteria:**
- A TOML target with `backend = "claude"` loads without error.
- An execution plan snapshot round-trips a claude target.
- An isolated claude target emits `--safe-mode` and `--strict-mcp-config`.
- A read-only claude target emits `--tools Read,Grep,Glob`.
- `model` becomes `--model` and `reasoning` becomes `--effort`.
- A claude target dispatches to the claude executor and never to pi.
- `validate_target_args("unsafe", "claude", ("--",))` raises `ValueError`.

**Reviewer Checklist:**
- Flag order in the claude arm matches the design table exactly.
- `backend_profile` is not silently translated to an unrelated flag.
- No new field is added to `TargetConfig`.
- The dispatch change cannot alter routing for `agy`, `codex`, or `pi`.
- Existing three-backend configurations still load unchanged.

**Verification Checks:**
- `uv run pytest tests/test_config.py tests/test_smoke.py tests/test_planning.py -q`
- `uv run pytest -q`

**Commit:** `feat(drivers): route claude targets through the claude adapter`

---

### Phase 3: Direct-invocation API accepts claude

**Goal:** `run("claude", ...)` works through both the compatibility runner and
the server entry point, and a live smoke test can exercise the real CLI.

**Task Guide Input:** Extend a Python daemon's legacy direct-invocation backend
runner and its server-level wrapper to accept a fourth backend name. The runner
uses a typed literal, injected per-backend executors, and a bare else-branch
default that must become explicit. Add a live-marked integration test that skips
when the CLI is absent. Distinct use cases are a direct claude run, preserving
the three existing backend arms, and a live run against the installed CLI.

**Files:**
- Modify: `src/openmcp/backend_runner.py`
- Modify: `src/openmcp/server.py`
- Modify: `tests/test_smoke.py`
- Modify: `tests/test_live_backends.py`

**Tasks:**
1. Extend `BackendName` to include `claude`, add a `claude_executor` keyword
   parameter defaulting to `claude_execute`, and replace the bare `else` at
   `backend_runner.py:90` with explicit `pi` and `claude` branches.
2. Update the `run` signature literal at `server.py:62` and pass
   `claude_executor=claude_execute` alongside the existing executors.
3. Add `import openmcp.backends.claude` to the imports smoke test and include
   `ClaudeParams` in the transport-only params assertion.
4. Add a `@pytest.mark.live` PONG test for the claude adapter that skips on
   `missing_cli`, matching the existing agy and codex live tests.

**Acceptance Criteria:**
- `run("claude", prompt, cd)` invokes the claude executor with a `ClaudeParams`
  instance.
- The agy, codex, and pi arms behave exactly as before.
- `openmcp.server.run` accepts `"claude"` without a type error.
- `uv run pytest -m live -k claude` passes when `claude` is installed and skips
  cleanly when it is not.

**Reviewer Checklist:**
- The pi arm keeps its `args=("--approve",)` default and is not disturbed.
- No target policy leaks into the compatibility runner, per the note at
  `backend_runner.py:51`.
- The live test asserts a non-empty `SESSION_ID`, as the shared helper requires.
- Executor injection stays consistent across all four backends.

**Verification Checks:**
- `uv run pytest -q`
- `uv run pytest -m live -k claude`

**Commit:** `feat(runner): support claude in the direct-invocation API`

---

### Phase 4: Documentation reflects the claude backend

**Goal:** Operators can configure a claude target from the documentation alone,
including the flags OpenMCP owns and the arguments that break it.

**Task Guide Input:** Update the operator documentation for a Python
orchestration daemon after adding a fourth coding-agent CLI backend. One
document is a per-backend CLI flag reference with an ownership statement per
backend. The other is a project README with an architecture diagram, a feature
list, and a worked configuration example. Distinct use cases are documenting the
flag table, documenting the arguments that break resume or the execution model,
and adding a configuration example.

**Files:**
- Modify: `CLI_ARGUMENTS.md`
- Modify: `README.md`

**Tasks:**
1. Add a `## Claude Code (claude -p)` section to `CLI_ARGUMENTS.md` with the
   available-flags table, the OpenMCP ownership statement, the target field
   translation table, and the unsupported arguments list from the design. Record
   the verified CLI version and research date in the existing header.
2. Update the README feature list, the ASCII architecture diagram, and the
   backend prerequisites to include claude.
3. Add a claude target and a claude-based profile to the README configuration
   example, without changing the existing default profile.

**Acceptance Criteria:**
- `CLI_ARGUMENTS.md` documents the exact argv OpenMCP owns for claude.
- The unsupported arguments list names `--no-session-persistence`,
  `--fork-session`, `--bg`, `--worktree`, and `--bare`, each with its reason.
- The README architecture diagram shows a fourth adapter.
- The README configuration example loads under `uv run openmcp doctor` when
  copied to `~/.openmcp/config.toml`.

**Reviewer Checklist:**
- Documented flags match the installed CLI, not a guessed surface.
- The `--bare` warning states that it breaks OAuth authentication.
- The isolation description matches what `--safe-mode` actually disables.
- No credentials appear in any example `args` array.
- Existing sections for agy, codex, and pi are untouched.

**Verification Checks:**
- `uv run openmcp doctor`
- `uv run pytest -q`

**Commit:** `docs: document the claude backend and its flag ownership`
