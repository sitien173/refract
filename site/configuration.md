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
| `isolated` | Strip context files, extensions, plugins, hooks, and MCP servers; `pi` and `claude` only |
| `read_only` | Limit the worker to read and search tools; `pi` and `claude` only |
| `args` | Extra CLI options, one token per array item |
| `max_concurrency` | Jobs this target runs at once; default `1` |
| `context_window` | Context capacity reported in `result.tokens`; overrides the backend's value |
| `retry` | `{ attempts, codes, patterns }`: retry a retryable failure on the same target |
| `env` | Environment variables for the worker process |

**Important:** Put credentials in each CLI's own login or in `env`. Every target setting except `env` is copied into job records.

The [Backends]({% link backends.md %}) page lists the flags each backend accepts and which ones Refract owns.

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
