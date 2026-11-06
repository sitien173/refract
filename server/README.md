# Refract

Version 2.5.0 · [Repository](https://github.com/sitien173/refract)

Refract is a loopback HTTP orchestration daemon for durable coding jobs.
It exposes AI agent workflows through Model Context Protocol tools.

## Key Features

- Durable direct-directory jobs; Refract does not create worktrees or make Git commits.
- One-job-per-project FIFO admission with multi-project concurrency bounded by global `max_jobs`.
- Immutable execution plan snapshots for every job.
- Multi-provider support for Antigravity, Codex, Pi, and Claude Code backends.
- Six self-describing MCP tools for listing, submitting, waiting, answering, cancelling, and retrying jobs.
- Isolated and read-only execution modes for sensitive tasks.
- Per-project, per-workflow context instructions injected into every backend.

## Architecture

```
[MCP Client / IDE]
        │
        ▼ (HTTP / SSE on 127.0.0.1:8765/mcp)
[Starlette / MCP Server]
        │
        ▼
[Runtime Facade] ──► [SQLite Database]
        │
        ▼
[Project Scheduler] (One-Job-Per-Project FIFO Admission)
        │
        ▼
[Job Runner & Target Executor]
        │
        ├──────────────┬──────────────┬──────────────┐
        ▼              ▼              ▼              ▼
  [AGY Adapter] [Codex Adapter] [Pi Adapter] [Claude Adapter]
        │              │              │              │
        └──────────────┴──────┬───────┴──────────────┘
                              ▼
                 [Host Provider CLI Process]
                              │
                              ▼
                   [Target Git Workspace]
```

Visual diagrams are available in `docs/diagrams/`:
- [System Architecture Diagram](../docs/diagrams/refract_system_architecture.svg)
- [C4 Model Diagrams](../docs/diagrams/refract_c4_model.svg)
- [Data Flow Diagram](../docs/diagrams/refract_data_flow_diagram.svg)

## Quick Start

### Prerequisites

- Python 3.12 or newer.
- `uv` package manager installed.
- At least one supported backend CLI on `PATH`: `agy`, `codex`, `pi`, or
  `claude`.

### Installation

```bash
uv sync --all-extras
```

### Configuration

Create `~/.refract/config.toml` before starting the daemon. Set `REFRACT_HOME` to use another state directory; when unset, Refract uses `~/.refract`. The database and default log are `refract.db` and `refract.log` in that directory.

[`config.v3.toml`](config.v3.toml) is a complete example that uses every key with all four backends. A test loads it, so it stays valid. Copy it and replace the placeholder targets and values.

The config has five sections. All keys are snake_case.

| Section | Keys |
|---|---|
| `[daemon]` | `host`, `port`, `max_jobs`, `default_profile`, `breaker_failure_threshold`, `breaker_base_cooldown_s`, `breaker_max_cooldown_s`, `ask_timeout_s` |
| `[logging]` | `level`, `file`, `max_bytes`, `backup_count` |
| `[notifications]` | `enabled` |
| `[[targets]]` | `id`, `backend`, `model`, `backend_profile`, `reasoning`, `system_prompt`, `isolated`, `read_only`, `args`, `max_concurrency`, `context_window`, `retry`, `env` |
| `[profiles.<name>]` | `extends` and one key per workflow |

`[daemon].default_profile`, `[[targets]]` and `[profiles]` are required. `backend` is one of `codex`, `pi`, `claude` or `agy`. An unknown key fails the load. A removed key fails the load with a message that names its replacement. See [Migrating config to v3](../README.md#migrating-config-to-v3).

A profile maps each workflow to a target id, a list of target ids in fallback order, or `{ targets = [...], timeout_s = N }`. A profile may name one parent with `extends`; it inherits the parent's workflows and overrides the ones it sets. Cycles fail the load. A profile may map only some workflows. A missing workflow fails when a job is planned, not when the config loads.

```toml
[profiles.base]
implement = "codex-high-code"
review = ["pi-high-review", "claude-opus-code"]
consult = { targets = ["agy-gemini-consult", "pi-high-review"], timeout_s = 1800 }

[profiles.claude_impl]
extends = "base"
implement = "claude-opus-code"
```

### Target retry

A target retries on itself with an inline `retry` table. Refract never switches targets during a retry.

```toml
[[targets]]
id = "codex-high-code"
backend = "codex"
retry = { attempts = 2, codes = ["rate_limit"], patterns = ["temporarily unavailable"] }
```

- `attempts` counts retries after the first attempt. It defaults to zero, which disables retries.
- Only transient failures retry. A failure matches when its code is in `codes` or its message contains one of `patterns`, compared without case. Empty `codes` and `patterns` match every transient failure.
- Fatal errors, cancellation, context overflow and replay-blocked failures never retry. Observed tool activity or unknown replay safety blocks a retry.
- Job token counts sum every attempt.
- A manual `retry` creates a new job with a fresh retry budget.

### Database compatibility

The v3 server creates a fresh database with one initial schema. It does not migrate v2 databases. On start, a pre-v3 `refract.db` and its `-wal` and `-shm` files are renamed to `*.v2.bak` and a new database is created. Old jobs, sessions and history stay in the backup and are never deleted. A v3 database is opened as is.

Stop the daemon before upgrading. Downgrade requires restoring the `*.v2.bak` files under their original names. Server and plugin must deploy together as a unit. Select another state directory with `REFRACT_HOME` to start fresh without touching existing state.

### Starting the Daemon

Verify configuration and start the daemon:

```bash
uv run refract doctor
uv run refract serve
```

The daemon listens at `http://127.0.0.1:8765/mcp`. `REFRACT_LOG_LEVEL`, `REFRACT_LOG_FILE`, `REFRACT_LOG_MAX_BYTES` and `REFRACT_LOG_BACKUP_COUNT` override logging settings. Relative log paths resolve under `REFRACT_HOME` or `~/.refract`.

Application logs are text in a private rotating file with mode 0600. Secrets in messages and tracebacks are redacted. When file logging is disabled or the file cannot be opened, logs go to stderr. Logging does not create crash files or manage the process fault handler.

## Target environments

Each target has one `env` table of literal string values:

```toml
[[targets]]
id = "worker"
backend = "codex"
env = { API_TOKEN = "replace-me", BASE_URL = "https://api.example.invalid" }
```

A worker process starts with a copy of the daemon environment, then applies the target `env`. Daemon-issued `REFRACT_ASK_*` values are applied last. Keys beginning `REFRACT_ASK_` are reserved and fail the load. Values are not templates; `${NAME}` fails the load, and the daemon environment is already inherited. No shell expansion or command execution occurs. Empty strings are valid values.

A project `.refract/config.toml` may add `[profiles.<name>]` entries and merge `env` into existing global targets. It may not add targets or any other section. A project profile may extend a global profile.

```toml
[profiles.project_review]
extends = "base"
review = "worker"

[[targets]]
id = "worker"
env = { BASE_URL = "https://project.example.invalid" }
```

A project `[[targets]]` entry must name an existing global target and may contain only `id` and `env`. Duplicate entries and unknown targets are invalid. Project keys replace matching global keys; other global keys stay.

Treat project configuration as trusted executable policy: it can change worker process environments and must be reviewed. Config files may hold plaintext secrets and must be protected. Env values are read from the current config when a target runs and are never stored in job records. Retries and queued-job restarts therefore use the current config. If a target with `env` has been removed, execution fails instead of running without its environment.

A configured target `PATH` applies to the launched worker process only. Backend discovery and structured-mode probes continue to use the daemon environment, so changing target `PATH` does not change CLI discovery.

## Workflows and Policy

Refract provides four built-in workflows:

- `implement`: Runs a coding prompt in the registered project directory. Worker changes remain in that directory; Refract does not auto-commit.
- `review`: Inspects codebase. Generates review output without committing.
- `consult`: Answers architectural questions without committing.
- `other`: Single execution task without automatic commits.

### Target Isolation

Targets using the `pi` backend support policy enforcement:
- `isolated = true`: Disables context files, extensions, and templates.
- `read_only = true`: Restricts tools to `read`, `grep`, `find`, and `ls`.

Targets using the `claude` backend support the same two fields:
- `isolated = true`: Disables CLAUDE.md, skills, plugins, hooks, MCP servers,
  and custom commands and agents.
- `read_only = true`: Restricts tools to `Read`, `Grep`, and `Glob`.

See [CLI_ARGUMENTS.md](CLI_ARGUMENTS.md) for the full per-backend flag
reference.

## MCP Tool Surface

Refract exposes six tools and no MCP resources:

| Tool | Purpose |
| --- | --- |
| `submit(path, workflow, prompt, profile="", session="", fresh=false)` | Queue a durable job for the Git project that contains `path`. |
| `wait(job_id, timeout_s=3600)` | Wait for a pending question or a terminal job. Timeouts are normal; repeat with the same job ID. |
| `answer(job_id, answer)` | Deliver an answer to a pending worker question. The answer is limited to 8192 characters. |
| `cancel(job_id)` | Cancel a queued or running job. |
| `retry(job_id, target="")` | Create a new job on the source job's `next_target`, or on `target` when set. |
| `list(path)` | List active and recent jobs, with the project's workflows, profiles, and guidance. |

`path` can be any directory inside a Git repository. Refract resolves the Git root, so a subdirectory never creates a second project. A path outside Git returns `invalid_path`.

The standard cycle is `list`, then `submit`, then `wait`. Prompts must be self-contained. Jobs in a project are admitted one at a time in FIFO order; jobs in different projects can run concurrently up to global `max_jobs`. Use `session` to resume a worker session. Use `fresh=true` to start a new one. Job summaries expose target names.

`wait` accepts `timeout_s` from 0 to 3600. `timeout_s=0` reads immediately. When a running job asks a question, `wait` returns early with `result.pending_question`, which contains `question_id` and `text`. Call `answer` with the job ID and answer to resume the job. Calling `answer` without a pending question, after the question expires, or on a terminal job returns `invalid_state`.

Every terminal job writes its full text to `result.result_path`. When `result.truncated` is true, `result.text` holds only the part that fits the response. Read the rest from `result_path`.

Errors are compact JSON with `code`, `message`, and `next_action`, delivered as MCP tool errors. `targets_unavailable` also carries `retry_after_s`. Follow `next_action`.

Responses stay below 30,000 characters and 9,000 UTF-8 bytes. If a mutation response overflows, it reports the actual outcome and keeps the job ID. Never blindly resubmit.

### Dashboard and Live Output

- **Pages:** Open `http://127.0.0.1:<port>/dashboard` for the job list, `/dashboard/jobs/<job_id>` for one job's prompt, result, metadata and output, and `/dashboard/targets` for targets, circuit state and config errors. Pages are server-rendered with the vendored Trulioo Design System CSS.
- **Polling:** `/dashboard/jobs/<job_id>/output?after=N` returns JSON with the stream events after line `N`, plus `next`, `state` and `terminal`. The job page polls it once per second while the job is active and stops when the job is terminal.
- **Access:** Every dashboard route and `/ask` answer only loopback clients that use a loopback `Host` header. Other requests get 403.
- **Provider support:** Claude, Codex, Pi, and Agy support streaming. Unsupported versions fall back to final-only execution safely.
- **Content exclusions:** Live output includes assistant text, tool status and token updates. Prompts, reasoning, and tool arguments remain excluded. Tool results, diagnostics, and environment variables remain excluded.
- **Storage:** Each job appends its events to `<state dir>/streams/<job_id>.jsonl`, mode 0600. The dashboard reads that file, so live output survives a daemon restart. Stream files have no size cap. Retention pruning deletes a job's stream and result files with the job.
- **Authoritative results:** The final text is written to `<state dir>/results/<job_id>.md`, mode 0600. A stream write failure is logged and never alters the final result.
- **Subagent streaming:** Subagent text streaming remains deferred.

### Worker Telemetry

Each job stores six token counters: `context_used`, `context_window`, `input`, `output`, `cache_read` and `cache_write`. `wait` returns them as `tokens`. A counter the backend did not report is `null`, never zero. A reported zero stays zero.

- **Consumption:** `input`, `output`, `cache_read` and `cache_write` sum across attempts. Within one backend run, a repeated response replaces its earlier counts, and backend-reported cumulative totals override the summed value.
- **Context:** `context_used` and `context_window` come from the latest attempt. When the backend reports no context use but both `input` and `output` are known, `context_used` is their sum. That estimate can overcount across turns, retries and compaction.
- **Configured target capacity:** Set an optional positive integer `context_window` on a global target. For example:

  ```toml
  [[targets]]
  id = "primary"
  backend = "codex"
  model = "gpt-4o"
  context_window = 200000
  ```

  The configured value overrides provider-reported capacity. If omitted, provider capacity may be used. Changing it does not change stored jobs.
- **Opt-in probe limitations:** Live model telemetry probes are strictly opt-in (`REFRACT_LIVE_TELEMETRY_OPT_IN=1`) and require execution authorization; missing prerequisites fail rather than report false passes.

### Recovery and Routing

- `retry(job_id)` creates a new job on the source job's `result.next_target`. It never changes the source job or its result file.
- `retry` accepts `succeeded`, `failed`, `cancelled`, and `interrupted` jobs.
- The new job keeps the source job's `session` and `fresh` values.
- `retry(job_id, target=X)` pins target `X`, including the same target. An unknown target returns `invalid_request` and lists the profile's targets.
- A successful job makes its target the session's preferred target. Later jobs in that session try it first.
- After `context_overflow`, submit again with `fresh=true`.
- After `replay_blocked`, the worker already changed files. Inspect the worktree before any retry.

## Development and Testing

```bash
uv run pytest
uv run pytest -m live
uv run refract doctor
uv build
```
