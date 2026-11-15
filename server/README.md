# Refract server

Version 3.0.8 · [Repository](https://github.com/sitien173/refract)

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
| `refract serve` | Run the daemon. Flags: `--host`, `--port`, `--log-level`, `--log-file`. |
| `refract doctor` | Check that the state directory is writable and every target executable resolves. |
| `refract status` | Report whether the configured daemon answers and its PID when available. Exit 0 when running, 1 otherwise. |
| `refract stop [--force]` | Stop the daemon when idle. `--force` interrupts running jobs and keeps queued jobs for the next start. |
| `refract restart [--force]` | Stop and start the daemon. `--force` interrupts running jobs; queued jobs remain queued for the restarted daemon. |
| `refract ask "<question>"` | Ask the Coordinator a question from inside a worker job. |
| `refract update [--check]` | Check for the latest Refract release and print the server and per-host update commands (`--check` updates the 24-hour cache quietly). |
| `refract install -p <host> [--scope S] [--dry-run] [--source SOURCE]` | Install the plugin through each host's own CLI, except `agy-ide`, which Refract installs by copying files itself. `-p` takes `claude`, `codex`, `agy`, `agy-ide`, `pi`, or `all`, as a comma list or repeated. `--scope` is `user`, `project`, or `local`: `claude` accepts all three, `pi` and `agy-ide` accept `user` and `project`, `codex` and `agy` accept `user` only. `agy-ide` copies to `~/.gemini/config/plugins/refract/` for `user` and to `<cwd>/.agents/plugins/refract/` for `project`, and, for a remote `--source` or none, it shallow-clones the repository to a temporary directory, which needs `git` on PATH. `--dry-run` prints the host commands, or for `agy-ide` the file operations, without running them. `--source` is a plugin path or URL; the default is the GitHub repository. Exits 0 when every host succeeded or was already installed, 1 when a host failed, a named host is not on PATH or, for `agy-ide`, not found, `-p all` found no host, another install holds the lock, or the lock file cannot be opened, and 2 for a usage error or unsupported scope. |
| `refract uninstall -p <host> [--scope S] [--dry-run]` | Remove the plugin through each host's own CLI. For `agy-ide`, it deletes the copied directory only when Refract's ownership marker in it names that same path, and refuses an unmarked directory or a link. Takes the same `-p`, `--scope`, and `--dry-run` options and returns the same exit codes. |
| `refract stats [--days N] [--json]` | Show local usage stats. `--days` is `1`, `7`, `30`, or `365`; the default is `7`. `--json` prints the API response unchanged. Needs a running daemon. |

> [!WARNING]
> The MCP endpoint has no authentication. `refract serve` refuses a non-loopback host and has no override flag. `/mcp` rejects a request with a non-loopback Host or Origin.

## Configuration

The daemon reads `~/.refract/config.toml`. Set `REFRACT_HOME` to use another state directory. [`config.v3.toml`](config.v3.toml) is a complete example covering every key.

The file must set `schema_version = 1` at the top level. A missing `schema_version` or an unknown key stops the daemon with `config_invalid`, a `loc`, and a fix hint.

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
| `args` | Extra CLI options, one token per array item |
| `max_concurrency` | Jobs this target runs at once; default `1` |
| `retry` | `{ attempts, codes, patterns }`: retry a matching failure on the same target. A policy without `codes` or `patterns` retries nothing. |
| `env` | Environment variables for the worker process |

> [!IMPORTANT]
> Put credentials in each CLI's own login or in `env`. Every target setting except `env` is copied into job records.

[`CLI_ARGUMENTS.md`](CLI_ARGUMENTS.md) lists the flags each backend accepts and which ones the `coding_agent_cli` library or Refract owns.

### Retry Codes

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

An unknown `retry.codes` value fails config loading with `config_invalid` at the exact `loc`. A value removed in 3.0.4 names its replacement:

| Removed code | Replacement |
| --- | --- |
| `no_agent_messages` | `no_output` |
| `fatal_backend` | `auth`, `invalid_model`, or `service_error` |
| `bad_cd` | `bad_cwd` |
| `request_fatal` | `no_output` |

`retry.patterns` match the error text. The library changed some error messages, so re-check any pattern that matched the old text, for example `backend command exited with status` or `The <backend> CLI was not found on PATH`.

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
| `submit` | Queue a job with a workflow and prompt, or pass `from_job` to copy a finished job. With `from_job`, only `target` and `fresh` may be set. |
| `get` | Read a job without waiting: its result, pending question, and attempts |
| `wait` | Block until any of 1 to 16 listed `job_ids` finishes or asks a question |
| `cancel` | Stop a queued or running job; returns `cancel_status` |
| `answer` | Reply to a worker's pending question |
| `list` | Active and recent jobs, workflows, profiles, and guidance for a project |
| `card_create`, `card_move`, `card_list` | Track work on a per-repository board |

The same URL serves two protocol generations. Requests for protocol 2026-07-28 are stateless: there is no `initialize` call and no session. Clients from 2025 call `initialize` and receive an `Mcp-Session-Id` session. Those sessions do not expire while idle. Refract advertises no change notifications and no resource subscriptions, and `subscriptions/listen` is refused. For protocol 2026-07-28 only, `tools/list` carries a cache hint of 5 minutes with private scope. Responses to 2025-era clients carry no cache hint.

Jobs are admitted first in, first out, up to `max_jobs` across all projects. Several jobs in one project can run at once and edit the same checkout. Jobs that share a project, session, workflow, and target run one at a time.

`wait` and `get` return `{job, result, truncated, result_path, pending_question, failure_kind, next_target, model, duration_ms, tokens}`; `get` adds `attempts`. A response stays below 9,000 UTF-8 bytes. A longer result is truncated and carries `truncated: true` and `result_path`; read the full text from that file. `cancel` returns `{job, cancel_status}`, where `cancel_status` is `terminated` for a queued job, `requested` for a running job, and `already_terminal` for a finished job, which is never changed.

### Recovery and Routing

- `submit(from_job=X)` runs a finished job again. The source job must be terminal and not pruned. Without `target`, the new job uses the target after the source job's last attempt; with none left, the error is `targets_unavailable`. `target` and `fresh` are the only other parameters. `fresh` defaults to null. Without `from_job`, null means false. With `from_job`, omitting `fresh` copies the source job's value, and an explicit `fresh=false` overrides a source job that used `fresh=true`.
- When an attempt is `replay_safe`, the server recovers inside the same job and records one `attempts` row per step. A failure that matches `retry.codes` or `retry.patterns` retries on the same target. `context_overflow` opens one fresh session. A `transient` or `target_fatal` failure falls back to the next eligible target. The `attempts.reason` values are `initial`, `retry`, `fresh_session`, and `fallback`.
- An attempt is `replay_safe` only when the target streams events, no `tool.started` event occurred, and the worker asked no question. A failed attempt that is not `replay_safe` is not recovered, so the job ends with `failure_kind`, plus `next_target` when one remains. Inspect the checkout before calling `submit(from_job=...)`.
- An open circuit skips a target until its cooldown ends. When no target is available, the error is `targets_unavailable` with `retry_after_s`.
- Errors return `code`, `message`, and `next_action`. `invalid_request` means the arguments did not match the schema or named an unknown target.

### Restart policy

On daemon start, `running` jobs become `interrupted`, `open` questions become `expired`, and `queued` jobs resume. Refract never re-runs an interrupted job by itself. The Coordinator calls `submit(from_job=...)` to run it again. A blocked `wait` sees the new state on its next DB read.

On the first start, a database with a `user_version` other than 1 is renamed to `refract.db.<user_version>.bak`, with its `-wal` and `-shm` files, and a new database is created. Refract never deletes the `.bak` file, and the old job history does not appear in the dashboard.

The full contract for Coordinator agents is in [`tool-contract.md`](../plugin/skills/coordinating-multi-model-work/references/tool-contract.md).

## Worker questions

Each worker gets `REFRACT_ASK_URL` and `REFRACT_ASK_TOKEN` in its environment. Running `refract ask "<question>"` blocks until the Coordinator calls `answer` or `ask_timeout_s` passes. The worker's tool shell must have `refract` on `PATH`.

## Dashboard

Open `http://127.0.0.1:8765/dashboard/` while the daemon runs. It shows jobs with live transcripts, target health, and the card board. You can cancel, retry, and answer jobs from it. Retry calls `POST /dashboard/api/jobs` with `from_job`. The page subscribes to `GET /dashboard/api/events` and falls back to 30-second polling. Dashboard routes accept loopback clients only.

The Insights view at `/dashboard/insights` shows the numbers that `refract stats` prints. See [Stats](#stats).

## Stats

`refract stats` and the Insights view read the `jobs` and `attempts` tables. Job rows are kept for 365 days. The prompt, result, and transcript are pruned after 7 days, so stats outlast the 7-day job content.

`GET /dashboard/api/stats?days=<1|7|30|365>&tz_offset_minutes=<int>` serves both. `tz_offset_minutes` ranges from -1440 to 1440 and defaults to `0`. A bad value returns HTTP 400.

### Windows and time zone

A window of N days covers the last N times 24 hours from the request time. It is not calendar days. The daily series groups jobs by the caller's local date. `refract stats` and the dashboard send the local UTC offset. The API uses UTC when you omit it.

### Definitions

| Group | Definition |
| --- | --- |
| Work delegated | Jobs by workflow and state, plus a breakdown by profile, workflow, target, and state. Worker hours are `sum(duration_ms) / 3,600,000`. Success rate is `succeeded / (succeeded + failed)`. The daily series counts succeeded and failed jobs. |
| Failover saves | `skipped_targets`: succeeded jobs that passed over at least one target. `retries`: succeeded jobs with more than one attempt. `attempts_by_reason`: attempt counts grouped by `attempts.reason`: `initial`, `retry`, `fresh_session`, and `fallback`. Succeeded jobs with unknown values count under `unknown_skipped_targets` and `unknown_attempts`, not as zero. Jobs in other states are not counted in either. |
| Tokens | For each backend, model, and target: uncached input, output, cache read, cache write, and job count. Cache hit ratio is `cache_read / (uncached_input + cache_read)`. |

Uncached input is `max(0, input - cache components)`, where the components are those that the backend already counts in `input`. These are `cache_read` for `codex`, and `cache_read` plus `cache_write` for `claude` and `pi`. For `agy` and an empty backend, Refract subtracts nothing. A job that ended before target selection appears as `unassigned`.

`refract stats` prints the job count, worker hours, success rate, failover saves, and model count. Use `--json` for every field.

### Database schema 1

The database has `PRAGMA user_version=1`. A database created by a Refract version that predates schema 1, or by a schema 1 build before commit `45139dd5`, must be recreated; see [Restart policy](#restart-policy) for the `.bak` rename.

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
