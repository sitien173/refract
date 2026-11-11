# Refract server

Version 3.0.1 · [Repository](https://github.com/sitien173/refract)

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
| `refract stats [--days N] [--json]` | Show local usage stats. `--days` is `1`, `7`, `30`, or `365`; the default is `7`. `--json` prints the API response unchanged. Needs a running daemon. |
| `refract telemetry` | Show whether telemetry is on, the deciding setting, and the exact next batch. Needs a running daemon. |

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

### `[telemetry]`

Global config only. See [Telemetry](#telemetry).

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | unset, which means off | `true` or `false`; the third step in the consent order |

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

The Insights view at `/dashboard/insights` shows the numbers that `refract stats` prints. See [Stats](#stats).

## Telemetry

Telemetry is off by default. When it is on, the daemon sends usage data to `https://cf-api-gateway.sitienbmt.workers.dev/refract-collector`. A leftover `[telemetry] endpoint` key is ignored and produces a warning. The data informs backend and model priorities, reliability fixes, feature adoption, and install base. Stats work with telemetry on or off.

While telemetry is off, Refract makes no telemetry network call, creates no install ID, and writes no outbox rows. The [price file fetch](#pricing) is not telemetry. It runs in either state and sends no install ID or usage data. A job that ends while telemetry is off is never queued later.

### Consent order

The daemon checks these in order and stops at the first match. It reads environment variables from its own process.

1. `DO_NOT_TRACK=1` forces telemetry off. Any other value is ignored.
2. `REFRACT_TELEMETRY=1` turns it on and `REFRACT_TELEMETRY=0` turns it off. Any other value is ignored.
3. `[telemetry] enabled` in `config.toml`.
4. Otherwise telemetry is off.

A config file that fails to load counts as off. Each enqueue and each send re-reads the config first, so a change applies without a restart. No consent prompt exists in the CLI or the dashboard. Run `refract telemetry` to see the decision, the deciding setting, and the exact next batch. `GET /dashboard/api/telemetry` returns the same data.

`refract telemetry` prints eight fields:

| Field | Content |
| --- | --- |
| `enabled` | `on` or `off` |
| `source` | `DO_NOT_TRACK`, `REFRACT_TELEMETRY`, `config`, or `default` |
| `endpoint` | `https://cf-api-gateway.sitienbmt.workers.dev/refract-collector` |
| `install_id` | Install ID, or `none` while telemetry is off |
| `queued` | Number of events in the outbox |
| `last_send_at` | Time of the last successful send, or `never` |
| `last_error` | Last send error, or `none` |
| `next_batch` | The exact next request body as JSON, or `none` when no event is due |

`last_send_at` and `last_error` are kept in memory, so they reset when the daemon restarts.

### Payload contract v1

Each request is one JSON `POST` with up to 100 events:

```json
{"schema": 1, "install_id": "<uuid4>", "refract_version": "<version>", "sent_at": "<UTC ISO>", "events": []}
```

`sent_at` is set when the batch is sent. The preview from `refract telemetry` shows it as `null`. Every event has an `event` field with the type name.

| Event | When it is queued | Dedup key |
| --- | --- | --- |
| `job` | Once for each job that reaches a terminal state | `job:<job id>` |
| `features` | Hourly and when the daemon closes, only when counts exist | `features:<period start>` |
| `heartbeat` | The first flush of each UTC day | `heartbeat:<date>` |

`job` fields:

| Field | Content |
| --- | --- |
| `event` | `job` |
| `job_id` | Job ID |
| `retry_of` | ID of the job this one retries, or empty |
| `finished_at` | UTC finish time |
| `workflow` | `implement`, `review`, `consult`, or `other` |
| `profile` | Profile name |
| `session` | Session name given to `submit` |
| `target` | Target id, or empty when the job ended before target selection |
| `backend` | `codex`, `claude`, `pi`, `agy`, or empty |
| `model` | Model string, or empty |
| `state` | Terminal job state |
| `failure_kind` | Failure kind, or `null` |
| `duration_ms` | Run time in milliseconds |
| `tokens` | Object with `input`, `output`, `cache_read`, `cache_write`, `context_used`, and `context_window` |
| `attempts` | Retry-loop attempt number, or `null` when unknown |
| `skipped_targets` | Targets passed over because the circuit was open or the driver was unavailable, or `null` when unknown |
| `error` | Redacted error text, at most 500 characters |

`features` fields:

| Field | Content |
| --- | --- |
| `event` | `features` |
| `period_start`, `period_end` | UTC bounds of the counting period |
| `counts` | Map of feature name to use count |

Feature names are `mcp.<tool>` for each MCP tool call, `mcp_client.<client name>` for the MCP client name cut to 64 characters, `ask`, and `dashboard.stats`, `dashboard.jobs`, `dashboard.output`, `dashboard.job_detail`, `dashboard.targets`, `dashboard.cards`, and `dashboard.card`. The map holds at most 200 names per period. Counts live in memory, so a crash loses up to one hour of them.

`heartbeat` fields:

| Field | Content |
| --- | --- |
| `event` | `heartbeat` |
| `os`, `arch` | Operating system and machine architecture |
| `python_version` | Python version |
| `notifications_enabled` | Value of `[notifications].enabled` |
| `backends` | Map of backend kind to the number of configured targets that use it |

### Never sent

Refract never collects the prompt, the result text, the project root, target `args`, or target `env` values as payload fields. Error text is a payload field, so Refract redacts target `args` and `env` values and these paths from it before it is queued. Error text may still carry prompt or code fragments, as the warning below explains.

Error text is redacted in this order, then cut to 500 characters:

1. Target `env` values and `args` values, longest first, become `[REDACTED]`.
2. The project root, the home directory, and the Refract state directory become `[PATH]`. Both `/` and `\` forms match, and Windows ignores case.
3. The log redaction filter removes credential-shaped text.

> [!WARNING]
> Redaction removes known secrets and paths. It cannot detect a worker that echoes prompt text or other content into its error message. Error text can therefore carry fragments of your prompt or code. Turn telemetry off if that is not acceptable. `profile`, `session`, `target`, and `model` are names you chose, and they are sent as written.

### Delivery

- A background task sends. Job execution never waits on the network.
- Each request carries up to 100 events, uses a 10-second timeout, and honors `HTTPS_PROXY`.
- A 2xx response deletes the sent rows.
- A 429, a 5xx, or a network error keeps the rows and retries with backoff that doubles from 1 minute to 24 hours.
- Any other 4xx drops the batch and logs a warning.
- The outbox holds at most 10,000 rows and 30 days of events. Enqueue deletes the oldest rows past either limit.
- A telemetry failure never fails or delays a job.

### Local files and opt-out

| Location | Content |
| --- | --- |
| `telemetry_id` in the state directory | Random UUID4 install ID, mode `0600`. Created at the first enqueue, or by a status request (`refract telemetry` or `GET /dashboard/api/telemetry`) while telemetry is on. |
| `telemetry_heartbeat` in the state directory | UTC date of the last heartbeat |
| `telemetry_outbox` table in `refract.db` | Queued events not yet sent |

When telemetry turns off, the daemon deletes the outbox rows, the in-memory feature counts, `telemetry_id`, `telemetry_heartbeat`, and any leftover `telemetry_heartbeat.tmp`. Pending rows are deleted, not sent. The `job_metrics` table that backs [Stats](#stats) is not touched.

## Pricing

Estimated cost in [Stats](#stats) uses a price file that the daemon fetches from `https://raw.githubusercontent.com/sitien173/refract/refs/heads/main/server/config/pricing.toml`. Refract has no `[pricing]` config section. A leftover `[pricing]` section is ignored and produces a warning.

The file is TOML with `schema = 1` and a `[pricing]` table. `currency` defaults to `"USD"`. Each `[pricing.models."<model>"]` table needs `input`, `output`, `cache_read`, and `cache_write`, as non-negative numbers per 1M tokens. `<model>` is the canonical model name that stats display: the reported string with any provider prefix removed (the text after the last `/`), then resolved through the optional `[pricing.aliases]` table. An alias maps an exact, case-sensitive display name to a priced model. The file is invalid when an alias target is not a priced model, an alias key is also a model key or is empty, or a model or alias key contains `/`. The file is at most 64 KiB, and redirects are refused.

```toml
schema = 1

[pricing]
currency = "USD"

[pricing.models."example-model"]
input = 0.0
output = 0.0
cache_read = 0.0
cache_write = 0.0

[pricing.aliases]
"Example Model (High)" = "example-model"
```

- The daemon fetches at start and then every 24 hours. After a failed fetch it retries after 1 hour and keeps the previous prices.
- A valid file is cached at `$REFRACT_HOME/pricing.toml`. The daemon loads the cache at start, so stats work offline.
- Stats requests read the prices held in memory. They never touch the disk or the network.
- The fetch runs regardless of telemetry consent and `DO_NOT_TRACK`. It sends no install ID and no usage data, only a plain GET with a `User-Agent: refract` header.
- Set `REFRACT_PRICING_FETCH=0` to turn the fetch off. The daemon then uses the cache alone, or no prices when there is no cache.
- A price change re-prices retained history, because cost is computed from token counts at request time.

## Stats

`refract stats` and the Insights view read the `job_metrics` table. Refract writes one row for each terminal job and keeps it for 365 days, so stats outlast the 7-day job history. The row holds no prompt, result, error text, project path, or session.

`GET /dashboard/api/stats?days=<1|7|30|365>&tz_offset_minutes=<int>` serves both. `tz_offset_minutes` ranges from -1440 to 1440 and defaults to `0`. A bad value returns HTTP 400.

### Windows and time zone

A window of N days covers the last N times 24 hours from the request time. It is not calendar days. The daily series groups jobs by the caller's local date. `refract stats` and the dashboard send the local UTC offset. The API uses UTC when you omit it.

### Definitions

| Group | Definition |
| --- | --- |
| Work delegated | Jobs by workflow and state. Worker hours are `sum(duration_ms) / 3,600,000`. Success rate is `succeeded / (succeeded + failed)`. The daily series counts succeeded and failed jobs. |
| Failover saves | `skipped_targets`: succeeded jobs that passed over at least one target. `retries`: succeeded jobs with more than one attempt. `retries_after_failure`: succeeded jobs in the window whose `retry_of` names a failed job anywhere in the retained metrics. Succeeded jobs with unknown values count under `unknown_skipped_targets` and `unknown_attempts`, not as zero. Jobs in other states are not counted in either. |
| Tokens | For each backend, model, and target: uncached input, output, cache read, cache write, and job count. Cache hit ratio is `cache_read / (uncached_input + cache_read)`. |
| Estimated cost | `(uncached_input * input + output * output + cache_read * cache_read + cache_write * cache_write) / 1e6`, using the fetched [Pricing](#pricing) file. Rows group by canonical model name, so a provider-prefixed or aliased name merges into one row. The result has a total, a per-model breakdown, and a list of unpriced models. A job with no model appears as `unassigned` in the per-model breakdown, and the price lookup still uses the empty model string. A model without a price never fails the request. |

Uncached input is `max(0, input - cache components)`, where the components are those that the backend already counts in `input`. These are `cache_read` for `codex`, and `cache_read` plus `cache_write` for `claude` and `pi`. For `agy` and an empty backend, Refract subtracts nothing. A job that ended before target selection appears as `unassigned`.

Cost is an estimate from the published prices. Jobs that migrated from an older database have unknown `attempts` and `skipped_targets`.

`refract stats` prints the job count, worker hours, success rate, failover saves, model count, and total cost. Use `--json` for every field.

### Database schema 20

Schema 20 adds `job_metrics` and `telemetry_outbox`. The first start of this version migrates a schema 19 or 18 database in place and backfills `job_metrics` from jobs still stored. It never backfills the outbox. A Refract version that supports only schema 19 refuses a schema 20 database with an error and leaves the file unchanged. To go back, install the older version and point `REFRACT_HOME` at another state directory, or restore a copy of `refract.db` made before the upgrade.

## Environment variables

| Variable | Effect |
| --- | --- |
| `REFRACT_HOME` | State directory; default `~/.refract` |
| `REFRACT_URL` | MCP endpoint the plugin connects to |
| `REFRACT_LOG_LEVEL`, `REFRACT_LOG_FILE` | Override logging level and path |
| `REFRACT_LOG_MAX_BYTES`, `REFRACT_LOG_BACKUP_COUNT` | Override log rotation |
| `REFRACT_DISABLE` | Plugin ignores Refract for the session |
| `REFRACT_NO_UPDATE_CHECK` | Plugin skips the update notice and background check |
| `REFRACT_TELEMETRY` | `1` turns telemetry on and `0` turns it off, unless `DO_NOT_TRACK=1` is set. Other values are ignored. The daemon reads it. |
| `REFRACT_PRICING_FETCH` | `0` turns off the [pricing](#pricing) fetch. Telemetry consent and `DO_NOT_TRACK` do not affect it. The daemon reads it. |
| `DO_NOT_TRACK` | `1` forces telemetry off and overrides every other setting. Other values are ignored. |

## Development

```bash
uv sync --all-extras
uv run pytest
```

Tests that call real worker CLIs are marked `live` and skipped by default. Run them with `uv run pytest -m live`.

The dashboard source is in [`web/`](web). `pnpm run build` writes the bundle to `src/refract/dashboard_static/app`, which is committed.
