## Original User Request

Integrate Claude Code non-interactive mode as a new OpenMCP backend. Phase 1
delivers the transport-only adapter module.

## Phase

`claude_execute` returns a correct `BackendResult` for every documented outcome,
with no wiring into the driver layer.

## Tasks

- task-1: Add `ClaudeParams` and a `run_shell_command` wrapper in a new
  `src/openmcp/backends/claude.py`.
- task-2: Assemble non-interactive argv with transport flags after target args
  and a `--` separator before the prompt.
- task-3: Parse the print-mode JSON result, resolve the session id, and collect
  diagnostics.
- task-4: Map subprocess failures onto `classify_backend_output` and add unit
  tests to `tests/test_smoke.py`.

## Context

Read `docs/plans/claude-backend/DESIGN.md` first. It records CLI facts verified
live against `claude` 2.1.220 on 2026-08-24.

`src/openmcp/backends/pi.py` is the closest sibling and the structural model for
this module. Follow its shape: a slotted params dataclass, a `run_shell_command`
generator delegating to `stream_shell_command_lines`, a pure extraction helper, a
`_execute_sync` body, and an async `execute` wrapper using `asyncio.to_thread`.

`src/openmcp/backends/__init__.py` provides `BackendResult` and
`classify_backend_output`. Do not modify either. The classifier already handles
auth and unknown-model tokens, empty agent messages, and the missing-session
warning case.

`src/openmcp/backends/_shell.py` merges stderr into stdout at line 54, so
non-JSON lines are expected in the stream and must be treated as diagnostics.

### Verified CLI facts

- Non-interactive entry is `claude -p`. There is no working-root flag; the
  workspace comes from the subprocess `cwd`.
- `--output-format json` emits one JSON object. Observed keys include `type`,
  `subtype`, `is_error`, `session_id`, `result`, and `api_error_status`.
- `--resume <uuid>` preserves the original `session_id` in the next result.
- `--tools` and `--add-dir` are variadic, so a trailing prompt can be consumed as
  a flag value. The `--` separator prevents this and was confirmed to work.

### Required argv

```
claude [*params.args] -p --permission-mode bypassPermissions \
       --output-format json [--resume <uuid>] -- <PROMPT>
```

`--permission-mode bypassPermissions` is transport-owned and belongs in this
module, matching how `codex.py` owns `--yolo`. Target policy flags arrive through
`params.args` and are compiled elsewhere in a later phase. Do not add policy
translation to this module.

### Required parsing

Keep the last JSON object whose `type` is `result`. Take `agent_messages` from
its `result` field and the session id from its `session_id` field. Treat
`is_error` true, or a `subtype` other than `success`, as error text built from
`result` and `api_error_status`. Fall back to `params.SESSION_ID` when the result
carries no session id, as `pi.py:170` does.

### Required failure mapping

| Condition | error_class |
|---|---|
| cd is not a directory | `bad_cd` |
| `claude` absent from PATH | `missing_cli` |
| `subprocess.TimeoutExpired` | `timeout` |
| non-zero exit status | `execution_error` |
| `cancel_event` set | `cancelled` |

## Files

- `src/openmcp/backends/claude.py`
- `tests/test_smoke.py`

## Done When

- `claude.py` imports cleanly and exports `ClaudeParams` and `execute`.
- `ClaudeParams` carries only transport fields and no policy fields.
- A success result yields `outcome="OK"` with non-empty `agent_messages` and the
  `session_id` from the result object.
- An `is_error` result yields `outcome="FATAL"`.
- A result missing `session_id` falls back to the input `SESSION_ID`.
- A non-zero exit yields `outcome="FATAL"` with `error_class="execution_error"`
  even when agent output was produced.
- A non-existent working directory yields `error_class="bad_cd"`.
- Argv places `--` immediately before the prompt, and transport flags after
  `params.args`.
- `uv run pytest tests/test_smoke.py -q`
- `uv run python -c "import openmcp.backends.claude"`

## Rules

Follow the supplied worker contract. Stay within scope. Do not modify
`drivers.py`, `config.py`, `planning.py`, `backend_runner.py`, or `server.py`;
those belong to later phases. Do not modify `backends/__init__.py` or
`backends/_shell.py`. Log metadata only, never the prompt or full argv. Maintain
this phase's `notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
