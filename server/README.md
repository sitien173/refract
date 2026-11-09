# Refract server

Version 3.0.0 · [Repository](https://github.com/sitien173/refract)

A local daemon that runs coding-agent CLIs as durable jobs. A Coordinator agent submits jobs over MCP. The daemon picks a target from a profile, runs the worker CLI in the project's Git checkout, and stores the session and result.

## Install

```bash
uv tool install "refract @ git+https://github.com/sitien173/refract#subdirectory=server"
```

From a clone:

```bash
cd server
uv sync --all-extras
uv run refract --help
```

## CLI

| Command | Purpose |
| --- | --- |
| `refract serve` | Run the daemon. Flags: `--host`, `--port`, `--log-level`, `--log-file`, `--allow-remote`. |
| `refract doctor` | Check that the state directory is writable and every target executable resolves. |
| `refract status` | Exit 0 when the configured daemon answers, 1 otherwise. |
| `refract ask "<question>"` | Ask the Coordinator a question from inside a worker job. |
| `refract update [--check] [--force]` | Check for or apply updates to the server and installed plugins. |

> [!WARNING]
> The MCP endpoint has no authentication. `refract serve` refuses a non-loopback host unless you pass `--allow-remote`.

## Configuration

The daemon reads `~/.refract/config.toml`. Set `REFRACT_HOME` to use another state directory. [`config.v3.toml`](config.v3.toml) is a complete example covering every key.

The daemon reloads targets and profiles on the next tool call after the file changes. A `[daemon]` host or port change needs a restart.

### `[daemon]`

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

### `[logging]` and `[notifications]`

`[logging]` accepts `level`, `file`, `max_bytes`, and `backup_count`. `file` defaults to `refract.log` under the state directory; set it to `false` to log to stderr. `[notifications].enabled = true` sends a desktop notification when a job finishes.

### `[[targets]]`

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

> [!IMPORTANT]
> Put credentials in each CLI's own login or in `env`. Every target setting except `env` is copied into job records.

[`CLI_ARGUMENTS.md`](CLI_ARGUMENTS.md) lists the flags each backend accepts and which ones Refract owns.

### `[profiles.*]`

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

### Project overrides

A repository can add `.refract/config.toml` with its own `[profiles.*]`. Its `[[targets]]` entries may only add `env` to global targets, matched by `id`.

A `task_guide.json` in `.refract/` or the state directory is returned as `guidance` from `list`. See [`task_guide.json.example`](task_guide.json.example).

## MCP tools

The daemon serves MCP at `http://127.0.0.1:8765/mcp`. Nine self-describing MCP tools cover the job lifecycle:

| Tool | Purpose |
| --- | --- |
| `list` | Active and recent jobs, workflows, profiles, and guidance for a project |
| `submit` | Queue a job with a workflow, prompt, and optional profile and session |
| `wait` | Block until a job finishes or asks a question |
| `answer` | Reply to a worker's pending question |
| `cancel` | Stop a queued or running job |
| `retry` | Create a new job from a finished one on the next target |
| `card_create`, `card_move`, `card_list` | Track work on a per-repository board |

Each project runs one job at a time. Jobs are admitted first in, first out, up to `max_jobs` across projects.

`wait` returns `{job, result}`. Every finished job writes its full text to `result.result_path`; read it when `result.truncated` is true.

### Recovery and Routing

- `retry(job_id)` runs the request again on `result.next_target`, the next healthy target in profile order. `retry(job_id, target=X)` pins a target.
- On `failure_kind` `context_overflow`, submit again with `fresh=true`.
- On `replay_blocked`, the worker already changed files. Inspect the checkout before retrying.
- An open circuit skips a target until its cooldown ends. When no target is available, the error is `targets_unavailable` with `retry_after_s`.
- Errors return `code`, `message`, and `next_action`. `invalid_request` means the arguments did not match the schema or named an unknown target.

The full contract for Coordinator agents is in [`tool-contract.md`](../plugin/skills/coordinating-multi-model-work/references/tool-contract.md).

## Worker questions

Each worker gets `REFRACT_ASK_URL` and `REFRACT_ASK_TOKEN` in its environment. Running `refract ask "<question>"` blocks until the Coordinator calls `answer` or `ask_timeout_s` passes. The worker's tool shell must have `refract` on `PATH`.

## Dashboard

Open `http://127.0.0.1:8765/dashboard/` while the daemon runs. It shows jobs with live transcripts, target health, and the card board. You can cancel, retry, and answer jobs from it. Dashboard routes accept loopback clients only.

## Environment variables

| Variable | Effect |
| --- | --- |
| `REFRACT_HOME` | State directory; default `~/.refract` |
| `REFRACT_URL` | MCP endpoint the plugin connects to |
| `REFRACT_LOG_LEVEL`, `REFRACT_LOG_FILE` | Override logging level and path |
| `REFRACT_LOG_MAX_BYTES`, `REFRACT_LOG_BACKUP_COUNT` | Override log rotation |
| `REFRACT_DISABLE` | Plugin ignores Refract for the session |
| `REFRACT_NO_UPDATE_CHECK` | Plugin skips the update notice and background check |

## Development

```bash
uv sync --all-extras
uv run pytest
```

Tests that call real worker CLIs are marked `live` and skipped by default. Run them with `uv run pytest -m live`.

The dashboard source is in [`web/`](web). `pnpm run build` writes the bundle to `src/refract/dashboard_static/app`, which is committed.
