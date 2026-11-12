# Non-interactive backend CLI arguments

Refract 3.0.4 · [Repository](https://github.com/sitien173/refract)

Flags were last checked on 2026-10-26 against:

- Antigravity CLI (`agy`) 1.4.7
- Codex CLI (`codex-cli`) 0.160.1
- Pi coding agent (`pi`) 1.4.0
- Claude Code (`claude`) 2.1.296

CLI flags can change between releases. Re-run `agy --help`, `codex exec --help`,
`codex exec resume --help`, `pi --help`, and `claude --help` after upgrading a
backend.

The `coding_agent_cli` library builds each backend command line, runs the
process, and parses its output. It launches argv directly with `shell=False`.
On Windows, it resolves npm `.cmd` launchers through their matching PowerShell
shim with `-NonInteractive`. Values in target `args` are individual argv
tokens, not a shell command and not a shell-quoted string. Refract adds the
permission flags and the target options, then maps each library outcome to
retry and the circuit breaker.

## Daemon configuration

`~/.refract/config.toml` is required. It must contain non-empty `targets` and
`profiles` sections. `[daemon].default_profile` is also required and must name
one configured profile. Refract does not fabricate configuration entries.

`REFRACT_HOME` overrides the state directory; otherwise it defaults to
`~/.refract`. `REFRACT_LOG_LEVEL`, `REFRACT_LOG_FILE`, `REFRACT_LOG_MAX_BYTES`,
and `REFRACT_LOG_BACKUP_COUNT` override logging settings. Relative log paths
resolve under the state directory. Logs are text in a private rotating file;
when file logging is disabled or fails, they go to stderr.

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
through `answer`, then resumes `wait` on the same job ID.

The worker tool-shell PATH must contain the installed `refract` executable.
Targets whose tools exclude shell execution, such as Claude Code and Pi
targets with `--tools` limited to read and search tools, cannot run
`refract ask` and return `BLOCKED` instead.

## Target configuration

Every target accepts an `args` array for backend-specific options that do not
have a first-class target field:

```toml
[[targets]]
id = "codex-audit"
backend = "codex"
model = "gpt-5.5"
reasoning = "high"
args = ["--color", "never"]

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

Keep one option or value per TOML array item. Repeat both items for repeatable
options, for example `args = ["--add-dir", "D:/one", "--add-dir", "D:/two"]`.
Do not put API keys or other credentials in `args`: target configuration is
snapshotted into job records. Use each CLI's credential store or the target
`env` table instead; `env` values are never stored in job records.

The library owns the non-interactive transport, the workspace, the prompt,
output parsing, and the session argument. Refract adds only the permission
flags and the target `args`. For Claude Code, Pi, and Agy, Refract passes
`model`, `reasoning`, and `system_prompt` as request fields, and the library
turns them into CLI arguments. Agy supports only `model`. For Codex, Refract
translates `model`, `reasoning`, and `backend_profile` itself, so the library
receives no Codex target fields. Target arguments should be options only,
because the library supplies the prompt.

Refract adds these flags to every job:

| `backend` | Refract adds | Position |
|---|---|---|
| `codex` | `--yolo` before target `args`; the `backend_profile`, `model`, and `reasoning` flags after them | Before and after target `args` |
| `claude` | `--permission-mode bypassPermissions` | Before target `args` |
| `agy` | `--dangerously-skip-permissions` | Before target `args` |
| `pi` | `--approve` | After target `args`, so a target cannot disable it |

Refract rejects these target `args` when it loads the config and when a target
is constructed programmatically:

- A value that is not a string.
- A value that contains a NUL byte.
- The reserved end-of-options token `--`.
- For Codex, `--cd`, `-C`, and their attached-value forms, so a target cannot
  leave its isolated worktree.

The library rejects these requests with the code `invalid_args` before it
starts the CLI:

- The same checks as above, for the NUL byte and the `--` token, and for the
  Codex working directory flags.
- A flag the library owns for its transport. The owned flags are `-p`,
  `--output-format`, `--include-partial-messages`, and `--resume` for Claude
  Code; `--json`, `-o`, and `--output-last-message` for Codex; `--mode` and
  `--session` for Pi; and `--output-format`, `--log-file`, `--conversation`,
  `--new-project`, `--print`, `-p`, `--prompt`, `--continue`, and `-c` for Agy.
- A flag in `args` that sets a target field already given. The library checks
  only the fields the target sets, per backend. Set the value in the field or
  in `args`, not both.

  | `backend` | Field | Conflicting `args` flag |
  |---|---|---|
  | `claude` | `model` | `--model` |
  | `claude` | `reasoning` | `--effort` |
  | `claude` | `system_prompt` | `--system-prompt` |
  | `pi` | `model` | `--model` |
  | `pi` | `reasoning` | `--thinking` |
  | `pi` | `system_prompt` | `--system-prompt` |
  | `agy` | `model` | `--model` |

  The check also matches the `flag=value` form. It does not match short forms
  such as `-m`. Agy ignores `reasoning` and `system_prompt`, so they never
  conflict. Codex has no library check: Refract translates `model` and
  `reasoning` itself and places them after `args`, so a Codex target may use
  `-c`, `--model`, and `-m` in `args`, and the Refract flags win.

A job that fails these checks ends as target fatal with the code
`invalid_args`. Refract maps the library codes `invalid_args`,
`unsupported_option`, and `invalid_model` to target fatal, so each opens the
target circuit.

Options such as Codex `--ephemeral` and Pi `--no-session` disable persistence
and therefore prevent resuming that backend context on a later job.

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
subcommands, not execution options.

The library owns `--print`, the prompt, `--conversation`, `--log-file`, and
`--output-format`. Refract adds `--dangerously-skip-permissions`. New sessions
(no stored conversation ID) are created with `--new-project`, so agy registers
the working directory as a project and loads its project context files from
the first job. Everything else uses the Agy CLI default unless selected by
target fields or `args`. The target `model` field is translated to `--model`;
configure `--add-dir` or sandbox behavior explicitly when required. Agy
`reasoning` and `system_prompt` are ignored. The compiled argv has these parts
in order:

```text
agy --output-format stream-json --log-file <path> \
    (--conversation <session-id> | --new-project) [--model <value>] \
    --dangerously-skip-permissions [target args] --print <prompt>
```

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

The library owns `exec`, `--json`, `--output-last-message`, the resume
subcommand and session ID, the prompt, and the working directory, which it sets
on the process. Refract adds `--yolo`. Everything else uses the Codex CLI
default unless selected by target fields or `args`. Refract translates
`backend_profile`, `model`, and `reasoning` itself and places them after target
`args`, so they win over a conflicting `-c` entry: `--profile <name>`,
`--model <value>`, `-c model="<value>"` when a profile is set, and
`-c model_reasoning_effort="<value>"`. Codex `system_prompt` is ignored.
Arbitrary Codex configuration is available through repeated `-c` entries in
`args`. The compiled argv has these parts in order, and the library sends the
prompt on standard input:

```text
codex exec --json -o <path> --yolo [target args] [--profile <name>] \
      [--model <value> [-c model="<value>"]] [-c model_reasoning_effort="<value>"] \
      [resume <session-id>] -
```

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
contain options only because the library supplies the prompt.

The library owns `--mode json`, the prompt, and `--session`. Refract appends
`--approve` after target arguments so it cannot be overridden. To isolate a
target, add `--no-context-files`, `--no-extensions`, `--no-skills`, and
`--no-prompt-templates` to `args`. To limit it to read and search tools, add
`--tools read,grep,find,ls`. `system_prompt`, `model`, and `reasoning` become
`--system-prompt`, `--model`, and `--thinking` respectively. The compiled argv
has these parts in order, and the library sends the prompt on standard input:

```text
pi --mode json [--session <session-id>] [--system-prompt <value>] \
   [--model <value>] [--thinking <value>] [target args] --approve
```

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
working directory, which the library sets.

The library owns `-p`, `--output-format`, `--include-partial-messages`, and
`--resume`. Refract adds `--permission-mode bypassPermissions`, ahead of target
arguments. A target cannot replace a library-owned flag: the library rejects it
as `invalid_args`. The compiled argv has these parts in order, and the library
sends the prompt on standard input, so a prompt that begins with `-` cannot be
read as a flag value:

```text
claude -p --output-format stream-json --include-partial-messages \
       [--resume <session-id>] [--system-prompt <value>] [--model <value>] \
       [--effort <value>] --permission-mode bypassPermissions [target args]
```

Target field translation:

| Field | Emitted argv |
|---|---|
| `system_prompt` | `--system-prompt <value>` |
| `model` | `--model <value>` |
| `reasoning` | `--effort <value>` |

`--safe-mode` disables CLAUDE.md, skills, plugins, hooks, MCP servers, custom
commands, custom agents, output styles, workflows, custom themes, and
keybindings. Authentication, model selection, built-in tools, and permissions
continue to work normally, and admin-managed policy settings still apply. That
combination is what makes it the usable analogue to Pi isolation. To isolate a
target, add `--safe-mode` and `--strict-mcp-config` to `args`. To limit it to
read and search tools, add `--tools Read,Grep,Glob`.

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
the NUL byte check apply to every backend, and the library rejects the owned and
conflicting flags listed under Target configuration. Claude Code has no
workspace-root flag to escape, so `--add-dir` is permitted for the same reason
Codex `--add-dir` is permitted.

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

- **Codex:** The library reads only the rollout session of the current job. Capacity comes from `model_context_window` when present. Occupancy is derived from the latest `last_token_usage` as `input + output - reasoning`; cumulative `total_token_usage` is never treated as occupancy.
- **Claude Code:** Capacity comes from `modelUsage.contextWindow` when the model matches; otherwise it stays null.
- **Pi:** Capacity is not reported and stays null.
- **Antigravity:** Capacity is accepted only when the stream reports it explicitly; otherwise it stays null.

### Semantics, cache accounting, and observation timing

- **Flat counters:** `wait` returns the six counters under `result.tokens`. There is no measurement source, quality or timestamp. Active context occupancy stays separate from cumulative consumption.
- **Cache accounting:** `cache_read` and `cache_write` isolate cache contributions. For Codex, cumulative turn usage is summed across attempts; for Claude Code, response and result usage maps cached read and write tokens.
- **Observation and presentation timing:** Backends send `telemetry.updated` events with the known counters during a run. The final counters are stored in the job's `tok_*` columns when it finishes.
- **Unknown values:** A counter no attempt reported stays null. Missing counts are never filled with zero.
