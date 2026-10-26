# Non-interactive backend CLI arguments

Refract 2.0.0 · [Repository](https://github.com/sitien173/refract)

Research performed on Windows on 2026-07-18 with:

- Antigravity CLI (`agy`) 1.1.4
- Codex CLI 0.144.5
- Pi coding agent 0.80.10

Claude Code research performed on Linux on 2026-08-24 with Claude Code
(`claude`) 2.1.220.

Verification performed on Linux on 2026-10-26 with:

- Antigravity CLI (`agy`) 1.4.7
- Codex CLI (`codex-cli`) 0.160.1
- Pi coding agent (`pi`) 1.4.0 (`@earendil-works/pi-coding-agent 1.4.0`)
- Claude Code (`claude`) 2.1.296 (Claude Code)


CLI flags can change between releases. Re-run `agy --help`, `codex exec --help`,
`codex exec resume --help`, `pi --help`, and `claude --help` after upgrading a
backend.

Refract launches argv directly with `shell=False`. On Windows, npm `.cmd`
launchers are resolved through their matching PowerShell shim with
`-NonInteractive`; values in target `args` are individual argv tokens, not a
shell command and not a shell-quoted string.

## Daemon configuration

`~/.refract/config.toml` is required. It must contain non-empty `targets` and
`profiles` sections. `[daemon].default_profile` is also required and must name
one configured profile. Refract does not fabricate configuration entries.

`REFRACT_HOME` overrides the state directory; otherwise it defaults to
`~/.refract`. `REFRACT_LOG_LEVEL`, `REFRACT_LOG_FORMAT`, `REFRACT_LOG_FILE`,
`REFRACT_LOG_CONSOLE`, `REFRACT_LOG_MAX_BYTES`,
`REFRACT_LOG_BACKUP_COUNT`, and `REFRACT_LOG_CAPTURE_WARNINGS` override logging
settings. Relative log paths resolve under the state directory.

Profiles may declare one explicit parent with `extends`. A profile can map only
some workflows. Missing workflow mappings fail during execution-plan
resolution, not configuration loading.

```toml
[profiles.base]
implement = "codex-audit"

[profiles.consult-only]
extends = "base"
consult = "pi-offline"
```

## Worker coordinator questions

During a worker job, run `refract ask "<question>"` for an
unresolved decision. The command reads `REFRACT_ASK_URL` and
`REFRACT_ASK_TOKEN` from the injected environment without daemon configuration.
Never print these values or copy them into prompts.

The command blocks until the coordinator answers or the server ask timeout
expires, then prints the answer. The timeout response is exactly:

```text
No answer from coordinator; use your best judgment or end with BLOCKED.
```

Missing environment, connection failures, and HTTP rejection return nonzero.
If the command fails or shell tools are unavailable, return `BLOCKED` with
the unresolved question. The coordinator answers `result.pending_question`
through `job_answer`, then resumes `job_wait` on the same job ID.

The worker tool-shell PATH must contain the installed `refract` executable.
The live probes prepend this checkout's `server/.venv/bin` to PATH. They do
not alter backend credentials, configuration, sandbox controls, or tool lists.

### Live ask reachability evidence

Observed on Linux, 2026-10-26. Command from `server/`:

```sh
uv run pytest -m live -k test_live_ask_coordinator tests/test_live_backends.py -v -s --tb=no
```

Each probe used `DriverRegistry.execute`, a temporary workspace, a 90-second
backend deadline, and an ephemeral loopback listener. Success required a valid
injected token, the exact question, and an exact random answer not present in
the prompt. The listener emulated answer delivery; this was not a full live
daemon/MCP round trip. Server tests cover that integration separately.

| Backend | Target mode | Observed result | Evidence |
|---|---|---|---|
| codex | normal | Prerequisite failure | CLI exited before session creation; inherited `CODEX_HOME` directory does not exist. Reachability unverified. |
| codex | read_only | Prerequisite failure | Same startup failure; reachability unverified. |
| claude | normal | Reached listener | Valid request and exact answer. |
| claude | read_only | BLOCKED fallback | Worker returned BLOCKED; listener not reached. Target tools exclude shell execution. |
| agy | normal | Reached listener | Valid request and exact answer. |
| agy | read_only | Reached listener | Valid request and exact answer; see policy limitation below. |
| pi | normal | Reached listener | Valid request and exact answer. |
| pi | read_only | BLOCKED fallback | Worker returned BLOCKED; listener not reached. Target tools exclude shell execution. |

Initial result: 4 passed, 2 xfailed for explicit BLOCKED fallback,
2 failed for Codex startup, 3 deselected in 113.05 seconds. An xfail records
fallback behavior, not successful env passthrough or loopback reachability.
No successful probe establishes stronger sandbox or isolation guarantees.

The final rerun used the same command with `-v -s -rx --tb=short`.
It reproduced all eight outcomes: 4 passed, 2 xfailed, 2 failed,
3 deselected in 111.78 seconds. Both Codex failure messages explicitly named
the missing inherited `CODEX_HOME` directory.

Codex diagnosis reproduced with `codex --version`, `codex exec --help`, and
`printf '%s\\n' 'Reply with PONG.' | codex exec --cd /tmp --yolo --json -`.
Installed version: `codex-cli 0.160.1`. The last command exited 1 because the
inherited `CODEX_HOME` directory does not exist. No credential or configuration
change was made. Both Codex modes require a valid existing backend home before
reachability can be tested.

Policy limitation: the current driver does not translate `read_only` into
restrictions for Codex or Agy. Their target-mode labels alone do not establish
read-only enforcement. Claude and Pi receive their documented restricted tool
lists. These probes do not add shell tools or weaken target controls.

## Target configuration

Every target accepts an `args` array for backend-specific options that do not
have a first-class target field:

```toml
[[targets]]
id = "codex-audit"
backend = "codex"
model = "gpt-5.5"
reasoning = "high"
args = ["--color", "never", "-c", "web_search=live"]
capabilities = ["review"]

[[targets]]
id = "agy-planner"
backend = "agy"
args = ["--mode", "plan", "--sandbox", "--print-timeout", "10m"]
capabilities = ["reasoning"]

[[targets]]
id = "pi-offline"
backend = "pi"
model = "openai/gpt-5"
args = ["--provider", "openai", "--offline"]
capabilities = ["code"]
```

Keep one option or value per TOML array item. Repeat both items for repeatable
options, for example `args = ["--add-dir", "D:/one", "--add-dir", "D:/two"]`.
Do not put API keys or other credentials in `args`: target configuration is
snapshotted into job records. Use each CLI's credential store or environment
variables instead.

Refract still owns the non-interactive transport, workspace, prompt, output
capture, and durable session argument. The driver translates first-class target
fields such as `model`, `backend_profile`, `reasoning`, `system_prompt`,
`isolated`, and `read_only` into CLI arguments before calling a transport-only
backend. Avoid duplicating those fields or transport-owned options in `args`; target arguments
should be options only because Refract supplies the final prompt. The reserved
end-of-options token `--` is rejected for every backend. Codex `--cd`, `-C`, and
their attached-value forms are also rejected so a target cannot leave its
isolated worktree. Isolated Pi targets cannot explicitly load extensions,
skills, or prompt templates. Options such as Codex `--ephemeral` and Pi
`--no-session` disable persistence and therefore prevent Refract from resuming
that backend context on a later job. These checks apply both when loading TOML
and when a target is constructed programmatically.

## Antigravity (`agy --print`)

Available flags:

| Flag | Value / purpose |
|---|---|
| `--add-dir` | Additional workspace directory; repeatable |
| `--agent` | Agent for this CLI session |
| `-c`, `--continue` | Continue the most recent conversation |
| `--conversation` | Resume a conversation ID |
| `--dangerously-skip-permissions` | Auto-approve tool permission requests; Refract-owned |
| `-i`, `--prompt-interactive` | Initial prompt followed by an interactive session |
| `--log-file` | Override internal log path |
| `--mode` | `accept-edits` or `plan` |
| `--model` | Session model |
| `--new-project` | Create a project for this session |
| `-p`, `--print`, `--prompt` | One-shot non-interactive prompt |
| `--print-timeout` | Print-mode wait duration; default `5m0s` |
| `--project` | Project ID |
| `--sandbox` | Enable terminal restrictions |

`agent`, `models`, plugin management, install, update, and changelog are
subcommands, not execution options. `agy models` listed Gemini 3.5 Flash,
Gemini 3.1 Pro, Claude Sonnet/Opus 4.6 Thinking, and GPT-OSS 120B variants on the
research machine.

Refract owns `--print`, its prompt, `--conversation`, `--log-file`, and
`--dangerously-skip-permissions` for non-interactive execution. New sessions
(no stored conversation ID) are created with `--new-project`, so agy registers
the working directory as a project and loads its project context files from
the first job. Everything else uses the Agy CLI default unless selected by
target fields or `args`. The target `model` field is translated to `--model`;
configure `--add-dir` or sandbox behavior explicitly when required. Agy stdout
is the preferred response channel; the temporary log file is primarily
diagnostic.

## Codex (`codex exec`)

Available `exec` options:

| Flag | Value / purpose |
|---|---|
| `-c`, `--config` | TOML `key=value` override; dotted keys and repeats supported |
| `--enable`, `--disable` | Repeatable feature toggle |
| `--strict-config` | Fail on unknown configuration fields |
| `-i`, `--image` | Initial image(s) |
| `-m`, `--model` | Model |
| `--oss` | Use an open-source provider |
| `--local-provider` | `lmstudio` or `ollama` |
| `-p`, `--profile` | Layer a named Codex configuration profile |
| `-s`, `--sandbox` | `read-only`, `workspace-write`, or `danger-full-access` |
| `--dangerously-bypass-approvals-and-sandbox` | Disable approvals and sandboxing |
| `--yolo` | Non-interactive approval/bypass mode; Refract-owned |
| `--dangerously-bypass-hook-trust` | Bypass hook trust |
| `-C`, `--cd` | Working root |
| `--add-dir` | Additional writable directory |
| `--skip-git-repo-check` | Permit a non-Git working root |
| `--ephemeral` | Do not persist session files |
| `--ignore-user-config` | Ignore `config.toml` (authentication still loads) |
| `--ignore-rules` | Ignore user/project exec-policy rules |
| `--output-schema` | JSON Schema for the final response |
| `--color` | `always`, `never`, or `auto` |
| `--json` | Emit JSONL events |
| `-o`, `--output-last-message` | Write the final agent reply to a file |

`codex exec resume` additionally accepts `--last` and `--all`; its documented
subset also includes config/feature flags, image, model, bypass flags,
skip-check, ephemeral, ignore-config/rules, output schema, JSON, and final
message output. Refract supplies a specific session ID and does not use
`--last`.

Refract owns `exec`, `--cd`, `--json`, `--output-last-message`, the resume
subcommand/session ID, the `--` prompt boundary, and the prompt. Refract always
enables `--yolo` for non-interactive execution. Everything else uses the Codex
CLI default unless selected by target fields or `args`. The driver translates
`backend_profile`, `model`, and `reasoning` to their CLI equivalents; arbitrary
Codex configuration remains available through repeated `-c` entries in `args`.

## Pi (`pi --mode json`)

Available execution options:

| Group | Flags |
|---|---|
| Model | `--provider`, `--model`, `--api-key`, `--thinking`, `--models`, `--list-models` |
| Prompt | `--system-prompt`, repeatable `--append-system-prompt` |
| Output | `--mode` (`text`, `json`, `rpc`), `-p`/`--print`, `--verbose` |
| Session | `-c`/`--continue`, `-r`/`--resume`, `--session`, `--session-id`, `--fork`, `--session-dir`, `--no-session`, `-n`/`--name` |
| Tools | `--no-tools`, `--no-builtin-tools`, `-t`/`--tools`, `--exclude-tools` |
| Resources | repeatable `-e`/`--extension`, `--skill`, `--prompt-template`; `--theme`; and their `--no-*` discovery switches |
| Context/trust | `--no-context-files`, `-a`/`--approve`, `-na`/`--no-approve` |
| Network | `--offline` |
| Export | `--export` |

The built-in tool names are `read`, `bash`, `edit`, `write`, `grep`, `find`, and
`ls`. Pi also supports `@file` message arguments, but target `args` should
contain options only because Refract supplies the final prompt.

Refract owns `--mode json`, the prompt, and `--session`. Direct runs and normal
targets append `--approve` after configurable arguments so it cannot be
overridden. For `isolated = true`, the driver instead adds `--no-approve`,
`--no-context-files`, `--no-extensions`, `--no-skills`, and
`--no-prompt-templates`; explicit extension, skill, and prompt-template args
(including `--extension=...` forms) are rejected. `read_only = true` adds
`--tools read,grep,find,ls`. `system_prompt`, `model`, and `reasoning` become
`--system-prompt`, `--model`, and `--thinking` respectively. Refract places
`--mode json` after target arguments so output parsing cannot be replaced.

## Claude Code (`claude -p`)

Available execution options:

| Group | Flags |
|---|---|
| Model | `--model`, `--fallback-model`, `--effort`, `--betas`, `--max-budget-usd` |
| Prompt | `--system-prompt`, `--append-system-prompt` |
| Output | `-p`/`--print`, `--output-format` (`text`, `json`, `stream-json`), `--input-format`, `--json-schema`, `--include-partial-messages`, `--verbose` |
| Session | `-r`/`--resume`, `-c`/`--continue`, `--session-id`, `--fork-session`, `--no-session-persistence`, `-n`/`--name`, `--from-pr` |
| Tools | `--tools`, `--allowed-tools`, `--disallowed-tools`, `--permission-mode`, `--dangerously-skip-permissions` |
| Resources | `--add-dir`, `--agent`, `--agents`, `--plugin-dir`, `--plugin-url`, `--mcp-config`, `--strict-mcp-config`, `--settings`, `--setting-sources`, `--file` |
| Isolation | `--safe-mode`, `--bare`, `--disable-slash-commands` |
| Execution model | `--bg`/`--background`, `-w`/`--worktree`, `--tmux`, `--ide`, `--chrome` |

`agents`, `auth`, `doctor`, `mcp`, `plugin`, `project`, `install`, `update`, and
`ultrareview` are subcommands, not execution options.

`--permission-mode` accepts `acceptEdits`, `auto`, `bypassPermissions`,
`manual`, `dontAsk`, and `plan`. `--effort` accepts `low`, `medium`, `high`,
`xhigh`, and `max`.

Claude Code has no working-root flag. The workspace comes from the subprocess
working directory, which Refract sets.

Refract owns `-p`, `--output-format json`, `--resume`, the `--` prompt boundary,
and the prompt. Refract always enables `--permission-mode bypassPermissions` for
non-interactive execution. Transport flags are appended after target arguments so
a target cannot replace `--output-format`. The compiled argv is:

```
claude [target args] -p --permission-mode bypassPermissions \
       --output-format json [--resume <session-id>] -- <prompt>
```

The `--` separator is required rather than cosmetic. `--tools` and `--add-dir`
are variadic, so without it a trailing prompt beginning with `-` can be consumed
as a flag value.

Target field translation:

| Field | Emitted argv |
|---|---|
| `isolated = true` | `--safe-mode --strict-mcp-config` |
| `system_prompt` | `--system-prompt <value>` |
| `read_only = true` | `--tools Read,Grep,Glob` |
| `model` | `--model <value>` |
| `reasoning` | `--effort <value>` |

`--safe-mode` disables CLAUDE.md, skills, plugins, hooks, MCP servers, custom
commands, custom agents, output styles, workflows, custom themes, and
keybindings. Authentication, model selection, built-in tools, and permissions
continue to work normally, and admin-managed policy settings still apply. That
combination is what makes it the usable analogue to Pi isolation.

`backend_profile` has no Claude Code equivalent and is ignored.

Unsupported target arguments, documented rather than rejected in code, matching
the existing treatment of Codex `--ephemeral` and Pi `--no-session`:

| Argument | Reason |
|---|---|
| `--no-session-persistence` | Sessions are never written to disk, so Refract cannot resume the context on a later job. |
| `--fork-session` | Resuming allocates a new session ID instead of reusing the original, breaking durable session continuity. |
| `--bg`, `--background` | Returns immediately as a background agent, so there is no result to capture. |
| `-w`, `--worktree` | Creates its own git worktree, which conflicts with the workspace Refract assigns. |
| `--bare` | Restricts Anthropic authentication to `ANTHROPIC_API_KEY` or `apiKeyHelper` and never reads OAuth or the keychain, so subscription logins fail. Use `--safe-mode` for isolation instead. |

`validate_target_args` adds no Claude-specific rule. The reserved `--` token and
the NUL byte check already apply to every backend. Claude Code has no
workspace-root flag to escape, so `--add-dir` is permitted for the same reason
Codex `--add-dir` is permitted.

## Worker telemetry and context measurement capabilities

Telemetry exposes job consumption and live context snapshots. Unsupported values remain null.

| Measurement | Meaning | Codex | Claude Code | Pi | Agy |
|---|---|---|---|---|---|
| `context_remaining_percent` | Context remaining percentage | Derived when latest rollout snapshot includes capacity | Derived from capacity | Unavailable null | Unavailable null |
| `context_window_size` | Context capacity limit | Reported in latest rollout `token_count` when present | Observed in `modelUsage` | Unavailable null | Unavailable null |
| `context_used_tokens` | Current occupied context | Derived from latest `token_count.last_token_usage` response | Derived response usage | Derived response usage | Derived step usage |
| `total_input_tokens` | Normalized input tokens | `turn.completed.usage` | Response and result | Message and summary | Step and result |
| `total_output_tokens` | Normalized output tokens | `turn.completed.usage` | Response and result | Message and summary | Step and result |
| `cache_read_tokens` | Cached input read tokens | `turn.completed.usage` | Response and result | Message and summary | Step and result |
| `cache_write_tokens` | Cache write tokens | `turn.completed.usage` | Response and result | Message and summary | Step and result |

### Measurement evidence and status

Capabilities are categorized by evidence level: package/CLI documentation evidence, synthetic fixture-only testing, and runtime unverified/unavailable limitations.

- Codex:
  - Installed CLI evidence: `codex --version` reports `codex-cli 0.160.1`; `codex exec --help` documents JSONL output. The public version-matched protocol source is [Codex `rust-v0.160.1` protocol.rs](https://raw.githubusercontent.com/openai/codex/rust-v0.160.1/codex-rs/protocol/src/protocol.rs), definitions `TokenUsageInfo`, `TokenUsage`, and `TokenCountEvent`. It defines nested `total_token_usage` and `last_token_usage` `TokenUsage` values and optional `model_context_window`; TokenUsage has input, cached input, output, reasoning output, and total counts. The `total_` record is cumulative and is never treated as occupancy.
  - Runtime collection: only the exact known rollout session is read. Capacity is the `model_context_window` value when valid. Occupancy is derived from the latest `last_token_usage` response components (`input + output - reasoning`), not cumulative totals. `turn.completed.usage` remains invocation consumption; cached input is already included.
  - Synthetic fixture-only: nested version-matched schema parsing, exact-session identity, bounded reads, rotation/truncation, and compaction invalidation are covered offline. No user conversations were inspected and no live probe was run; actual rollout availability and event timing remain runtime-unverified.
- Claude Code:
  - Package/CLI evidence: `claude 2.1.296 (Claude Code)`. `result` usage provides input, output, cache reads, and cache writes. `modelUsage` exposes model `contextWindow` when model matches.
  - Runtime unverified: unmatched models in `modelUsage` leave capacity null.
- Pi:
  - Installed CLI evidence: `pi --version` reports `1.4.0` (`@earendil-works/pi-coding-agent 1.4.0`); JSON `message_end` usage is exercised by sanitized offline fixtures. See [Pi CLI documentation](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent).
  - Synthetic fixture-only: response consumption and derived context behavior are tested. No installed-version session-format source has established effective model capacity; capacity remains unavailable null. This is not a verified claim that all Pi session artifacts lack capacity.
- Antigravity:
  - Installed CLI evidence: `agy --version` reports 1.4.7. Sanitized stream fixtures exercise step usage normalization; they do not establish a documented public event contract or live capability.
  - Synthetic fixture-only: optional explicit capacity metadata is accepted in fixtures. This does not establish that the installed CLI emits it, nor does it prove that a fixture-derived occupied count is an authoritative live context snapshot.
  - Runtime unverified: headless capacity and occupied-context semantics have not been verified; unsupported capacity remains null.

### Opt-in live telemetry probes

Live telemetry probes are located in `server/tests/test_live_backends.py`:
- Selector: `server/tests/test_live_backends.py::test_live_telemetry_probe`
- Status: Opt-in only via `REFRACT_LIVE_TELEMETRY_OPT_IN=1`. Marked `not run` in standard test runs.
- Missing prerequisites (such as missing CLI binaries, unauthenticated credentials, or non-existent `CODEX_HOME`) immediately fail the probe rather than reporting a false pass.
- No live model requests or probe runs are authorized without explicit user direction.

