# Non-interactive backend CLI arguments

Research performed on Windows on 2026-07-18 with:

- Antigravity CLI (`agy`) 1.1.4
- Codex CLI 0.144.5
- Pi coding agent 0.80.10

CLI flags can change between releases. Re-run `agy --help`, `codex exec --help`,
`codex exec resume --help`, and `pi --help` after upgrading a backend.

OpenMCP launches argv directly with `shell=False`. On Windows, npm `.cmd`
launchers are resolved through their matching PowerShell shim with
`-NonInteractive`; values in target `args` are individual argv tokens, not a
shell command and not a shell-quoted string.

## Daemon configuration

`~/.openmcp/config.toml` is required. It must contain non-empty `targets` and
`profiles` sections. `[daemon].default_profile` is also required and must name
one configured profile. OpenMCP does not fabricate configuration entries.

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

OpenMCP still owns the non-interactive transport, workspace, prompt, output
capture, and durable session argument. The driver translates first-class target
fields such as `model`, `backend_profile`, `reasoning`, `system_prompt`,
`isolated`, and `read_only` into CLI arguments before calling a transport-only
backend. Avoid duplicating those fields or transport-owned options in `args`; target arguments
should be options only because OpenMCP supplies the final prompt. The reserved
end-of-options token `--` is rejected for every backend. Codex `--cd`, `-C`, and
their attached-value forms are also rejected so a target cannot leave its
isolated worktree. Isolated Pi targets cannot explicitly load extensions,
skills, or prompt templates. Options such as Codex `--ephemeral` and Pi
`--no-session` disable persistence and therefore prevent OpenMCP from resuming
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
| `--dangerously-skip-permissions` | Auto-approve tool permission requests; OpenMCP-owned |
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

OpenMCP owns `--print`, its prompt, `--conversation`, and `--log-file`.
OpenMCP always enables `--dangerously-skip-permissions` for non-interactive
execution. Everything else uses the Agy CLI default unless selected by target
fields or `args`. The target `model` field is translated to `--model`; configure
`--add-dir` or sandbox behavior explicitly when required. Agy stdout is the
preferred response channel; the temporary log file is primarily diagnostic.

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
| `--yolo` | Non-interactive approval/bypass mode; OpenMCP-owned |
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
message output. OpenMCP supplies a specific session ID and does not use
`--last`.

OpenMCP owns `exec`, `--cd`, `--json`, `--output-last-message`, the resume
subcommand/session ID, the `--` prompt boundary, and the prompt. OpenMCP always
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
contain options only because OpenMCP supplies the final prompt.

OpenMCP owns `--mode json`, the prompt, and `--session`. Direct runs and normal
targets append `--approve` after configurable arguments so it cannot be
overridden. For `isolated = true`, the driver instead adds `--no-approve`,
`--no-context-files`, `--no-extensions`, `--no-skills`, and
`--no-prompt-templates`; explicit extension, skill, and prompt-template args
(including `--extension=...` forms) are rejected. `read_only = true` adds
`--tools read,grep,find,ls`. `system_prompt`, `model`, and `reasoning` become
`--system-prompt`, `--model`, and `--thinking` respectively. OpenMCP places
`--mode json` after target arguments so output parsing cannot be replaced.
