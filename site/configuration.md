---
layout: default
title: Configuration
nav_order: 4
---

# Configuration

The daemon reads `~/.refract/config.toml`. Set `REFRACT_HOME` to use another state directory. [`config.v3.toml`](https://github.com/sitien173/refract/blob/main/server/config.v3.toml) is a complete example covering every key.

The daemon reloads targets and profiles on the next tool call after the file changes. A `[daemon]` host or port change needs a restart.

## `[daemon]`

| Key | Default | Meaning |
| --- | --- | --- |
| `default_profile` | required | Profile used when `submit` names none |
| `host` | `"127.0.0.1"` | Bind address |
| `port` | `8765` | Bind port |
| `max_jobs` | `4` | Jobs running at once across all projects |
| `breaker_failure_threshold` | `3` | Consecutive failures before a target's circuit opens |
| `breaker_base_cooldown_s` | `60` | First cooldown for an open circuit |
| `breaker_max_cooldown_s` | `900` | Cooldown ceiling |
| `ask_timeout_s` | `300` | How long `refract ask` waits for an answer |

## `[logging]` and `[notifications]`

`[logging]` accepts `level`, `file`, `max_bytes`, and `backup_count`. `file` defaults to `refract.log` under the state directory; set it to `false` to log to stderr. `[notifications].enabled = true` sends a desktop notification when a job finishes.

## `[[targets]]`

A target is one worker CLI with fixed settings. `id` and `backend` are required. `backend` is one of `codex`, `claude`, `pi`, or `agy`.

| Key | Meaning |
| --- | --- |
| `model` | Model passed to the CLI |
| `reasoning` | Reasoning level, translated per backend |
| `backend_profile` | Codex configuration profile |
| `system_prompt` | System prompt for `pi` and `claude` |
| `args` | Extra CLI options, one token per array item |
| `max_concurrency` | Jobs this target runs at once; default `1` |
| `context_window` | Context capacity reported in `result.tokens`; overrides the backend's value |
| `retry` | `{ attempts, codes, patterns }`: retry a retryable failure on the same target |
| `env` | Environment variables for the worker process |

**Important:** Put credentials in each CLI's own login or in `env`. Every target setting except `env` is copied into job records.

The [Backends]({% link backends.md %}) page lists the flags each backend accepts and which ones the `coding_agent_cli` library or Refract owns.

## Retry Codes

`retry.codes` matches the `error_code` of a retryable failure. The codes come from the `coding_agent_cli` library. The outcome column shows how Refract treats each code.

| Code | Outcome | Meaning |
| --- | --- | --- |
| `timeout` | Retryable | The run hit its time limit. |
| `service_error` | Retryable | The provider reported a service error. |
| `execution_error` | Retryable | The CLI failed without a more specific code, such as a nonzero exit. |
| `stdin_failed` | Retryable | Writing the prompt to the CLI standard input failed. |
| `no_output` | Retryable | The CLI produced no assistant text. |
| `context_overflow` | Retryable, never retried on the same target | The prompt exceeded the context window. |
| `bad_cwd` | Request fatal | The working directory is not a directory. |
| `invalid_prompt` | Request fatal | The prompt is not valid UTF-8 or contains a NUL byte. |
| `invalid_args` | Target fatal | `args` conflicts with a flag the driver owns. |
| `unsupported_option` | Target fatal | The backend does not support a target field. |
| `invalid_model` | Target fatal | The CLI rejected the model. |
| `missing_cli` | Target fatal | The CLI is not on `PATH`. |
| `spawn_failed` | Target fatal | The CLI could not start. |
| `auth` | Target fatal | The CLI is not logged in or the credential failed. |

A request fatal failure is not retried and does not count toward the circuit breaker. A target fatal failure is not retried and opens the target circuit at once.

Config loading rejects a removed code in `retry.codes` and names the replacement. Update the config before you start the daemon.

| Removed code | Replacement |
| --- | --- |
| `no_agent_messages` | `no_output` |
| `fatal_backend` | `auth`, `invalid_model`, or `service_error` |
| `bad_cd` | `bad_cwd` |
| `request_fatal` | `no_output` |

`retry.patterns` match the error text. The library changed some error messages, so re-check any pattern that matched the old text, for example `backend command exited with status` or `The <backend> CLI was not found on PATH`.

## `[profiles.*]`

A profile maps the workflows `implement`, `review`, `consult`, and `other` to targets. A value can be one target id, an ordered list where later ids are fallbacks, or a table with `targets` and `timeout_s`. `timeout_s` limits each attempt in seconds; `0` means no limit.

```toml
[profiles.base]
implement = "codex-high-code"
review = ["pi-high-review", "claude-opus-code"]
consult = { targets = ["agy-gemini-consult"], timeout_s = 1800 }

[profiles.claude_impl]
extends = "base"
implement = "claude-opus-code"
```

`extends` inherits one parent profile. `other` never falls back and needs an explicit mapping.

## Project overrides

A repository can add `.refract/config.toml` with its own `[profiles.*]`. Its `[[targets]]` entries may only add `env` to global targets, matched by `id`.

A `task_guide.json` in `.refract/` or the state directory is returned as `guidance` from `list`. See [`task_guide.json.example`](https://github.com/sitien173/refract/blob/main/server/task_guide.json.example).

## Environment variables

| Variable | Effect |
| --- | --- |
| `REFRACT_HOME` | State directory; default `~/.refract` |
| `REFRACT_URL` | MCP endpoint the plugin connects to |
| `REFRACT_LOG_LEVEL`, `REFRACT_LOG_FILE` | Override logging level and path |
| `REFRACT_LOG_MAX_BYTES`, `REFRACT_LOG_BACKUP_COUNT` | Override log rotation |
| `REFRACT_DISABLE` | Plugin ignores Refract for the session |
| `REFRACT_NO_UPDATE_CHECK` | Plugin skips the update notice and background check |

Source: [server/README.md](https://github.com/sitien173/refract/blob/main/server/README.md)
