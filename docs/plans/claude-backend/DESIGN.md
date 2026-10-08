# Add the `claude` Backend

## Purpose

Add Claude Code as a fourth backend alongside `agy`, `codex`, and `pi`. It runs
through the Claude Code CLI in non-interactive print mode. It becomes selectable
as a target for every workflow.

## Research basis

Verified live on 2026-08-24 against `claude` 2.1.220 on Linux. Re-run
`claude --help` after upgrading the CLI.

- Non-interactive entry is `claude -p`. There is no working-root flag. The
  workspace comes from the subprocess `cwd`, which `_shell.py` already sets.
- `--output-format` accepts `text`, `json`, and `stream-json`. `stream-json`
  fails unless `--verbose` is also passed.
- `--output-format json` emits one JSON object. Observed keys include `type`,
  `subtype`, `is_error`, `session_id`, `result`, `total_cost_usd`,
  `permission_denials`, `terminal_reason`, and `api_error_status`.
- `--resume <uuid>` preserves the original `session_id` in the next result.
  `--fork-session` is what allocates a new one.
- A default run inherits the host user's Claude Code environment. A probe run
  fired three local `SessionStart` hooks and created 18944 cache tokens of
  context before the prompt.
- `--tools` and `--add-dir` are variadic. A trailing prompt can be consumed as a
  flag value. The `--` end-of-options separator prevents this and was confirmed
  to work with `--tools` present.

## Decisions

- Use the exact lowercase backend name `claude`. The executable name matches, so
  `DriverRegistry.available` needs no change.
- Parse `--output-format json`, not `stream-json`. One line, least parsing code,
  smallest memory. Accept that a timeout or cancel yields no partial agent text.
- Honor the existing `isolated` field, mirroring the pi arm. Do not force
  isolation and do not add new `TargetConfig` fields.
- Own the session lifecycle through `--resume`. Do not use `--session-id`,
  `--fork-session`, or `--continue`.
- Place OpenMCP transport flags after target `args` so a target cannot replace
  the result protocol.
- Always pass `--` before the prompt.
- Reuse `classify_backend_output` unchanged.

## Argv contract

```
claude [*target_args] -p --permission-mode bypassPermissions \
       --output-format json [--resume <uuid>] -- <PROMPT>
```

OpenMCP owns `-p`, `--permission-mode`, `--output-format`, `--resume`, the `--`
separator, the prompt, and the cwd. `--permission-mode bypassPermissions` lives
in the backend module, matching how codex owns `--yolo`.

## Target field translation

Compiled in `drivers._target_args`, in this order:

| Field | Emitted argv |
|---|---|
| `isolated` | `--safe-mode --strict-mcp-config` |
| `system_prompt` | `--system-prompt <value>` |
| `read_only` | `--tools Read,Grep,Glob` |
| `model` | `--model <value>` |
| `reasoning` | `--effort <value>` |

`--safe-mode` disables CLAUDE.md, skills, plugins, hooks, MCP servers, custom
commands, and custom agents, while leaving auth, model selection, built-in
tools, and permissions working. It is the usable analogue to pi isolation.

`--bare` is rejected as an isolation mechanism. It forces `ANTHROPIC_API_KEY` or
`apiKeyHelper` auth and never reads OAuth or the keychain, which breaks
subscription logins.

`--effort` accepts `low`, `medium`, `high`, `xhigh`, and `max`. Targets carrying
any other `reasoning` value fail at the CLI, as with the other backends.

`backend_profile` has no Claude equivalent and is ignored.

## Session handling

A new session omits `--resume`. The adapter reads `session_id` from the result
object and returns it as `SESSION_ID`. A resumed session passes
`--resume <SESSION_ID>`. When the result carries no `session_id`, fall back to
`params.SESSION_ID`, as `pi.py:170` does.

## Result parsing

Collect stdout lines, JSON-decode each, and keep the last object whose `type` is
`result`.

- `agent_messages` comes from the `result` field.
- `session_id` comes from the `session_id` field.
- `is_error` true, or a `subtype` other than `success`, produces error text from
  `result` and `api_error_status`.
- Lines that fail to decode become diagnostics. `_shell.py:54` merges stderr
  into stdout, so non-JSON output is expected.
- Results pass to `classify_backend_output` with `backend_name="claude"`.

## Failure mapping

Structured like `pi._execute_sync`.

| Condition | error_class | DriverOutcome |
|---|---|---|
| cd is not a directory | `bad_cd` | REQUEST_FATAL |
| `claude` absent from PATH | `missing_cli` | TARGET_FATAL |
| auth or unknown-model text | `fatal_backend` | TARGET_FATAL |
| `subprocess.TimeoutExpired` | `timeout` | RETRYABLE |
| non-zero exit status | `execution_error` | RETRYABLE |
| `cancel_event` set | `cancelled` | CANCELLED |

`TARGET_FATAL` and `RETRYABLE` behave identically in `execution.py:81`. Both
record a failure and fall through to the next target, with the circuit breaker
opening after three consecutive failures. Only `REQUEST_FATAL` and `CANCELLED`
abort the attempt loop.

## Dispatch hazard

`drivers.py:159` and `backend_runner.py:90` both route pi through a bare `else`.
Adding `claude` to the configuration allowlist without changing those branches
would make a claude target silently execute pi. Both must dispatch explicitly.

## Files

- New: `src/openmcp/backends/claude.py`
- Modify: `src/openmcp/drivers.py`, argv compiler and dispatch
- Modify: `src/openmcp/config.py:384`, backend allowlist
- Modify: `src/openmcp/planning.py:81`, backend allowlist
- Modify: `src/openmcp/backend_runner.py`, `BackendName` and dispatch arm
- Modify: `src/openmcp/server.py:62`, `run` signature and executor injection
- Modify: `tests/test_smoke.py`, `tests/test_config.py`,
  `tests/test_live_backends.py`
- Modify: `CLI_ARGUMENTS.md`, `README.md`

## Unsupported target arguments

Documented, not rejected in code. This matches the existing treatment of Codex
`--ephemeral` and Pi `--no-session`.

- `--no-session-persistence` and `--fork-session` prevent resume.
- `--bg` and `-w`, `--worktree` break the execution model.
- `--bare` breaks OAuth authentication.

`validate_target_args` gains no claude-specific rule. The reserved `--` token and
the NUL check already apply. Claude has no workspace-root flag to escape, and
`--add-dir` is permitted for the same reason Codex `--add-dir` is permitted.

## Non-goals

- Streaming output, partial-message events, and `--verbose`.
- Cost, usage, and rate-limit telemetry from the result object.
- MCP server injection through `--mcp-config`.
- Structured output through `--json-schema`.
- New `TargetConfig` fields.
- Changes to `classify_backend_output`.

## Compatibility

- No database migration.
- Existing targets, profiles, and job records remain valid.
- Existing three-backend configurations behave unchanged.
- `run("claude", ...)` becomes supported in the direct-invocation API.

## Testing

- Import the new module and assert params dataclass parity in smoke tests.
- Reject the reserved `--` token for a claude target in config tests.
- Parse a success result line, an `is_error` result, a result missing
  `session_id`, and interleaved non-JSON diagnostic lines.
- Confirm the argv layout places transport flags after target args and ends with
  `--` before the prompt.
- Confirm `isolated` and `read_only` emit the documented flags.
- Confirm claude dispatch does not fall through to pi.
- Run a `@pytest.mark.live` PONG test that skips on `missing_cli`.
