---
layout: default
title: Backends
nav_order: 6
---

# Backends

Refract accepts exactly four `backend` values: `agy`, `codex`, `pi`, and `claude`. The daemon resolves each through `PATH`.

Refract launches argv directly with `shell=False`. On Windows, npm `.cmd` launchers are resolved through their matching PowerShell shim with `-NonInteractive`. Values in target `args` are individual argv tokens, not a shell command and not a shell-quoted string.

## Target fields

`id` and `backend` are required. Optional: `model`, `backend_profile`, `reasoning`, `system_prompt`, `args`, `max_concurrency`, `context_window`, `retry`, `env`. Credentials stay in each CLI's own store or in the target `env` table, never in `args`: target settings other than `env` are snapshotted into job records.

## Profile fields

A profile maps workflows `implement`, `review`, `consult`, and `other` to a target id or an ordered list of ids; later ids are fallbacks. `extends` inherits another profile. `other` never falls back and needs an explicit mapping. `[daemon].default_profile` must name a declared profile.

See [Configuration]({% link configuration.md %}) for the full key tables.

## Backend summary

| `backend` | Detect | List models | `reasoning` becomes |
| --- | --- | --- | --- |
| `agy` | `command -v agy` | `agy models` | ignored; pick a model variant whose name carries the level, e.g. `"Gemini 3.1 Pro (High)"` |
| `codex` | `command -v codex` | no listing command; ask the user, or omit `model` to use the Codex default | `-c model_reasoning_effort=<value>` |
| `pi` | `command -v pi` | `pi --list-models` | `--thinking <value>` |
| `claude` | `command -v claude` | aliases such as `opus`, `sonnet`; see `claude --help` | `--effort <value>` |

Valid `reasoning` values belong to each CLI; confirm them in its `--help` before writing them.

- `system_prompt` is passed to `pi` and `claude`.
- To isolate a `pi` worker from context files, extensions, skills, and prompt templates, set `args = ["--no-context-files", "--no-extensions", "--no-skills", "--no-prompt-templates"]`. Add `"--tools", "read,grep,find,ls"` to limit it to read and search tools.
- To isolate a `claude` worker from CLAUDE.md, plugins, hooks, and MCP servers, set `args = ["--safe-mode", "--strict-mcp-config"]`. Add `"--tools", "Read,Grep,Glob"` to limit it to read and search tools.

## Target arguments

Every target accepts an `args` array for backend-specific options that do not have a first-class target field:

```toml
[[targets]]
id = "codex-audit"
backend = "codex"
model = "gpt-5.5"
reasoning = "high"
args = ["--color", "never", "-c", "web_search=live"]

[[targets]]
id = "agy-planner"
backend = "agy"
args = ["--mode", "plan", "--sandbox", "--print-timeout", "10m"]

[[targets]]
id = "pi-offline"
backend = "pi"
model = "openai/gpt-5"
args = ["--provider", "openai", "--offline"]
```

Keep one option or value per TOML array item. Repeat both items for repeatable options, for example `args = ["--add-dir", "D:/one", "--add-dir", "D:/two"]`. Do not put API keys or other credentials in `args`: target configuration is snapshotted into job records. Use each CLI's credential store or the target `env` table instead; `env` values are never stored in job records.

Refract still owns the non-interactive transport, workspace, prompt, output capture, and durable session argument. The driver translates first-class target fields such as `model`, `backend_profile`, `reasoning`, and `system_prompt` into CLI arguments before calling a transport-only backend. Avoid duplicating those fields or transport-owned options in `args`; target arguments should be options only because Refract supplies the final prompt. The reserved end-of-options token `--` is rejected for every backend. Codex `--cd`, `-C`, and their attached-value forms are also rejected so a target cannot leave its isolated worktree. Options such as Codex `--ephemeral` and Pi `--no-session` disable persistence and therefore prevent Refract from resuming that backend context on a later job. These checks apply both when loading TOML and when a target is constructed programmatically.

Flags were last checked on 2026-10-26 against:

- Antigravity CLI (`agy`) 1.4.7
- Codex CLI (`codex-cli`) 0.160.1
- Pi coding agent (`pi`) 1.4.0
- Claude Code (`claude`) 2.1.296

CLI flags can change between releases. Re-run `agy --help`, `codex exec --help`, `codex exec resume --help`, `pi --help`, and `claude --help` after upgrading a backend.

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

`agent`, `models`, plugin management, install, update, and changelog are subcommands, not execution options.

Refract owns `--print`, its prompt, `--conversation`, `--log-file`, and `--dangerously-skip-permissions` for non-interactive execution. New sessions (no stored conversation ID) are created with `--new-project`, so agy registers the working directory as a project and loads its project context files from the first job. Everything else uses the Agy CLI default unless selected by target fields or `args`. The target `model` field is translated to `--model`; configure `--add-dir` or sandbox behavior explicitly when required. Agy stdout is the preferred response channel; the temporary log file is primarily diagnostic.

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

`codex exec resume` additionally accepts `--last` and `--all`; its documented subset also includes config/feature flags, image, model, bypass flags, skip-check, ephemeral, ignore-config/rules, output schema, JSON, and final message output. Refract supplies a specific session ID and does not use `--last`.

Refract owns `exec`, `--cd`, `--json`, `--output-last-message`, the resume subcommand/session ID, the `--` prompt boundary, and the prompt. Refract always enables `--yolo` for non-interactive execution. Everything else uses the Codex CLI default unless selected by target fields or `args`. The driver translates `backend_profile`, `model`, and `reasoning` to their CLI equivalents; arbitrary Codex configuration remains available through repeated `-c` entries in `args`.

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

The built-in tool names are `read`, `bash`, `edit`, `write`, `grep`, `find`, and `ls`. Pi also supports `@file` message arguments, but target `args` should contain options only because Refract supplies the final prompt.

Refract owns `--mode json`, the prompt, and `--session`. The driver appends `--approve` after target arguments so it cannot be overridden. To isolate a target, add `--no-context-files`, `--no-extensions`, `--no-skills`, and `--no-prompt-templates` to `args`. To limit it to read and search tools, add `--tools read,grep,find,ls`. `system_prompt`, `model`, and `reasoning` become `--system-prompt`, `--model`, and `--thinking` respectively. Refract places `--mode json` after target arguments so output parsing cannot be replaced.

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

`agents`, `auth`, `doctor`, `mcp`, `plugin`, `project`, `install`, `update`, and `ultrareview` are subcommands, not execution options.

`--permission-mode` accepts `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, and `plan`. `--effort` accepts `low`, `medium`, `high`, `xhigh`, and `max`.

Claude Code has no working-root flag. The workspace comes from the subprocess working directory, which Refract sets.

Refract owns `-p`, `--output-format json`, `--resume`, the `--` prompt boundary, and the prompt. Refract always enables `--permission-mode bypassPermissions` for non-interactive execution. Transport flags are appended after target arguments so a target cannot replace `--output-format`. The compiled argv is:

```
claude [target args] -p --permission-mode bypassPermissions \
       --output-format json [--resume <session-id>] -- <prompt>
```

The `--` separator is required rather than cosmetic. `--tools` and `--add-dir` are variadic, so without it a trailing prompt beginning with `-` can be consumed as a flag value.

Target field translation:

| Field | Emitted argv |
|---|---|
| `system_prompt` | `--system-prompt <value>` |
| `model` | `--model <value>` |
| `reasoning` | `--effort <value>` |

`--safe-mode` disables CLAUDE.md, skills, plugins, hooks, MCP servers, custom commands, custom agents, output styles, workflows, custom themes, and keybindings. Authentication, model selection, built-in tools, and permissions continue to work normally, and admin-managed policy settings still apply. That combination is what makes it the usable analogue to Pi isolation. To isolate a target, add `--safe-mode` and `--strict-mcp-config` to `args`. To limit it to read and search tools, add `--tools Read,Grep,Glob`.

`backend_profile` has no Claude Code equivalent and is ignored.

Unsupported target arguments, documented rather than rejected in code, matching the existing treatment of Codex `--ephemeral` and Pi `--no-session`:

| Argument | Reason |
|---|---|
| `--no-session-persistence` | Sessions are never written to disk, so Refract cannot resume the context on a later job. |
| `--fork-session` | Resuming allocates a new session ID instead of reusing the original, breaking durable session continuity. |
| `--bg`, `--background` | Returns immediately as a background agent, so there is no result to capture. |
| `-w`, `--worktree` | Creates its own git worktree, which conflicts with the workspace Refract assigns. |
| `--bare` | Restricts Anthropic authentication to `ANTHROPIC_API_KEY` or `apiKeyHelper` and never reads OAuth or the keychain, so subscription logins fail. Use `--safe-mode` for isolation instead. |

`validate_target_args` adds no Claude-specific rule. The reserved `--` token and the NUL byte check already apply to every backend. Claude Code has no workspace-root flag to escape, so `--add-dir` is permitted for the same reason Codex `--add-dir` is permitted.

## Worker telemetry and context measurement capabilities

Each job stores six nullable token counters. Values a backend does not report remain null.

| Counter | Meaning | Codex | Claude Code | Pi | Agy |
|---|---|---|---|---|---|
| `context_window` | Context capacity limit | Reported in latest rollout `token_count` when present | Observed in `modelUsage` | Unavailable null | Unavailable null |
| `context_used` | Current occupied context | Derived from latest `token_count.last_token_usage` response | Derived response usage | Derived response usage | Derived step usage |
| `input` | Normalized input tokens | `turn.completed.usage` | Response and result | Message and summary | Step and result |
| `output` | Normalized output tokens | `turn.completed.usage` | Response and result | Message and summary | Step and result |
| `cache_read` | Cached input read tokens | `turn.completed.usage` | Response and result | Message and summary | Step and result |
| `cache_write` | Cache write tokens | `turn.completed.usage` | Response and result | Message and summary | Step and result |

### Backend notes

- **Codex:** Refract reads only the rollout session of the current job. Capacity comes from `model_context_window` when present. Occupancy is derived from the latest `last_token_usage` as `input + output - reasoning`; cumulative `total_token_usage` is never treated as occupancy.
- **Claude Code:** Capacity comes from `modelUsage.contextWindow` when the model matches; otherwise it stays null.
- **Pi:** Capacity is not reported and stays null.
- **Antigravity:** Capacity is accepted only when the stream reports it explicitly; otherwise it stays null.

### Semantics, cache accounting, and observation timing

- **Flat counters:** `wait` returns the six counters under `result.tokens`. There is no measurement source, quality or timestamp. Active context occupancy stays separate from cumulative consumption.
- **Cache accounting:** `cache_read` and `cache_write` isolate cache contributions. For Codex, cumulative turn usage is summed across attempts; for Claude Code, response and result usage maps cached read and write tokens.
- **Observation and presentation timing:** Backends send `telemetry.updated` events with the known counters during a run. The final counters are stored in the job's `tok_*` columns when it finishes.
- **Unknown values:** A counter no attempt reported stays null. Missing counts are never filled with zero.

Source: [server/CLI_ARGUMENTS.md](https://github.com/sitien173/refract/blob/main/server/CLI_ARGUMENTS.md), [plugin/setup/backends.md](https://github.com/sitien173/refract/blob/main/plugin/setup/backends.md)
