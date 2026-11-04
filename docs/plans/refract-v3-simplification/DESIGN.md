# Refract v3 Simplification Design

**Status:** Confirmed 2026-11-04
**Consultation:** Gemini consult job `fad3c73f-d12b-4534-a6de-dedc8f8b27fa` confirmed the direction; adopted keep-`list`, server-side Git root, retry-as-new-job, always-write result file, stream file, flat token counters; rejected the `"new:name"` session prefix.

## Purpose

Make Refract simple to use and simple to maintain. The coordinator flow shrinks to `list`, `submit`, `wait`. The server deletes subsystems that a single-user local tool does not need and fixes the defects found in the 2026-11-04 audit.

## Users and Success Criteria

User: the repository owner, as sole operator, through Claude Code acting as coordinator.

Success criteria:

1. The MCP surface is exactly 6 tools: `submit`, `wait`, `answer`, `cancel`, `retry`, `list`.
2. A normal job needs `submit` and `wait` only. No result paging exists.
3. `server/src/refract` is at most 9,000 lines of Python, down from 13,484. `server/web` no longer exists.
4. Each audit defect listed under Errors and Edge Cases is fixed or deleted with its code, and has a test.
5. The full `pytest` suite passes at every phase checkpoint.

## Constraints, Invariants, and Non-Goals

Constraints:

- Breaking changes to the MCP contract, config format, and database are accepted. The repository is not production.
- Simplicity first: delete before adding; no new runtime dependency.
- Work happens in worktree `/home/ngosi/.worktrees/refract/refract-v3-simplification` on branch `refract-v3-simplification`. The running daemon is a pipx editable install from `/home/ngosi/projects/refract/server` and must stay on v2 until cutover.
- Frontend uses the vendored TDS CSS, official `tds-*` classes, light theme.

Preserved invariants:

- Per-project FIFO admission with at most one running job per project, bounded by global `max_jobs`.
- Per-target `max_concurrency`.
- Circuit breaker with half-open probe in `target_health`.
- `replay_blocked`: no automatic replay after any tool activity.
- Process-group isolation and tree termination in `processes.py`.
- Startup reconciliation: running jobs become `interrupted`, queued jobs re-enqueue.
- Session identity includes a target key derived from target settings and environment, so changed flags never resume an incompatible CLI session.
- Worker ask flow: `refract ask` to loopback `POST /ask`, surfaced by `wait`, answered by `answer`.
- Dashboard and `/ask` are loopback-only.
- All four backends stay: `claude`, `codex`, `pi`, `agy`.

Non-goals:

- Automatic cross-target fallback.
- Migrating v2 job history or v2 config automatically.
- Multi-user, remote, or authenticated access.
- Langfuse or any external tracing.

## Chosen Approach

In-place, delete-first rework in seven phases on the existing package. Every phase leaves the suite green and is reviewed independently. The riskiest change, the transport rewrite, is isolated in its own phase.

Rejected: a parallel `refract3` package, because both versions would coexist and tests and fixes would be duplicated during the transition.

## Architecture and Data Flow

### MCP surface

| Tool | Parameters | Returns |
|---|---|---|
| `submit` | `path`, `workflow`, `prompt`, `profile=""`, `session=""`, `fresh=false` | `{job}` |
| `wait` | `job_id`, `timeout_s=3600` | `{job, result}` |
| `answer` | `job_id`, `answer` | `{job}` |
| `cancel` | `job_id` | `{job}` |
| `retry` | `job_id`, `target=""` | `{job}` for a new job with `retry_of` set |
| `list` | `path` | `{active, recent, workflows, profiles, guidance}` |

- `job`: `id, project, workflow, profile, target, session, state, retry_of, created_at, updated_at`.
- `result`: `text, truncated, result_path, pending_question, failure_kind, next_target, model, duration_ms, tokens`.
- `tokens`: `context_used, context_window, input, output, cache_read, cache_write`, each an integer or null.
- `failure_kind`: `cancelled, circuit_open, replay_blocked, context_overflow, request_fatal, target_fatal, transient`. Stored `retryable` maps to `transient` and stored `config_invalid` maps to `request_fatal` on read. A job whose config cannot load reports `request_fatal`.
- `next_target`: plain name of the next healthy target in profile order after the job's target, or null.
- Target names are public. The `_FORBIDDEN_OUTPUT_KEYS` redaction is removed.

Removed: `project_resolve`, `task_guide`, `job_list`, `job_report_error`, opaque `next_target` tokens, `result_offset` paging, `retryable`, measurement `source`, `quality`, `observed_at`.

### Flow

1. `list(path)` at session start returns active and recent jobs plus the project's workflows, profiles, and `guidance` from `task_guide.json`.
2. `submit` resolves the canonical Git root with `git rev-parse --show-toplevel`, so a subdirectory never creates a second project. Target selection: the session's `sticky_target` when it is in the profile and admitted, otherwise the first admitted target in profile order.
3. No in-run recovery: each attempt resumes the stored backend session, if any, with one backend call. A `context_overflow` failure is returned as `failure_kind` `context_overflow`; the coordinator resubmits with `fresh=true`. The `reconstruct` phase and `context_turns` reads and writes are deleted. Owner decision 2026-11-04.
4. `wait` returns early on a pending question. On terminal state the full text is already in `~/.refract/results/<job_id>.md`; `text` is cut to the response cap and `truncated` reports it.
5. `retry(job_id)` creates a new job on `next_target`. `retry(job_id, target=X)` pins a target, including the same one. Accepted source states: `succeeded`, `failed`, `cancelled`, `interrupted`. The source job is never mutated. A target without a stored session for the conversation starts fresh; coordinator prompts are self-contained.
6. On success, the session's `sticky_target` becomes the job's target and the backend session ID is stored for that `target_key`.

### Data model

Fresh SQLite schema with one initial migration:

| Table | Columns |
|---|---|
| `projects` | `id, root, created_at` |
| `jobs` | `id, project_id, workflow, profile, target, session, fresh, prompt, state, retry_of, failure_kind, error, model, duration_ms, pgid, tok_context_used, tok_context_window, tok_input, tok_output, tok_cache_read, tok_cache_write, created_at, started_at, finished_at, updated_at, execution_plan_json` |
| `sessions` | `project_id, session, workflow, sticky_target, updated_at`; primary key `project_id, session, workflow` |
| `target_sessions` | `project_id, session, workflow, target_key, backend_session_id, updated_at` |
| `target_health` | unchanged |

`jobs.execution_plan_json` holds the target plan fixed at submit time; owner decision 2026-11-04.

Deleted: `events`, `context_turns`, `job_stream_events`, `projects.alias`. Files: results in `~/.refract/results/<job_id>.md`, live output in `~/.refract/streams/<job_id>.jsonl`. History pruning deletes both files with the job.

### Config

- One naming style: snake_case. `contextWindow` becomes `context_window`.
- Retry inline per target: `retry = { attempts, codes, patterns }`. Named `retryPolicies` are removed.
- One `env` table per target. Shared env sets, `envs_vars`, and `${}` templating are removed.
- Profile `extends` is kept with its cycle check. Dashboard provenance is removed.
- Removed sections and keys: `[langfuse]`, `history_turns`, `history_bytes`, `task_routes.json`, `routes`, `routing_profile`, `profile` alias, `max_attempts`, logging `format`, `console`, `capture_warnings`.
- Logging keeps `level`, `file`, `max_bytes`, `backup_count` with the stdlib rotating handler, and keeps redaction and file permissions.
- Project overlay `.refract/config.toml` may add `profiles`, `targets`, `env`.
- A removed key fails load with an error naming its replacement, for example `retryPolicy -> targets[].retry`.

### Transport and backends

- One `async run_process(argv, stdin, env, cwd, deadline, cancel)` on `asyncio.create_subprocess_exec`, new session, stderr merged, prompt written to stdin then closed, lines decoded with `errors="replace"`, 1 MiB line limit.
- After process exit, wait 2 s for EOF, then kill the process group. On timeout or cancel, kill the group at once.
- No threads, no `StreamBridge`, no `asyncio.to_thread`. Events go straight to the stream file and token counters.
- Retain a 64 KiB output tail plus error lines; never every line.
- `Backend` protocol per backend: `argv(request)`, a per-run parser with `feed(line)`, `outcome()` returning text, session ID, structured error, tokens. Preflight, classification, telemetry guard, and error precedence are written once. Shared helpers live in one module. `_CodexRolloutCollector` moves to its own module.
- Langfuse, `observability.py`, `StreamRecorder`, `JobStreamHub`, and the telemetry measurement model are deleted.

### Dashboard

Three server-rendered pages built with `html.escape`, no template engine:

- `/dashboard`: job list with state, project, workflow, target, age.
- `/dashboard/jobs/{id}`: prompt, result, metadata, live output.
- `/dashboard/targets`: targets, circuit state, config errors.

One JSON endpoint `/dashboard/jobs/{id}/output?after=N` is polled by about 30 lines of inline JS while the job is active. TDS `tokens.css`, `fonts.css`, and needed component CSS move to `src/refract/dashboard_static/tds`. `server/web`, the committed bundle, and the 13 API routes are deleted.

## Errors and Edge Cases

| Case | Behavior |
|---|---|
| Codex exits 0 without an agent message | `request_fatal: no agent message`; never the raw JSONL. |
| No exact Codex session match | Store no session ID. The cwd heuristic is deleted. |
| Resumed session fails with `context_overflow` | The job fails with `failure_kind` `context_overflow`. No restart on the same target; the coordinator resubmits with `fresh=true`. |
| Resume fails after tool activity | `replay_blocked`; no retry or restart. |
| Daemon crash leaves worker groups | `jobs.pgid` is recorded; startup kills the group of each interrupted job. |
| Answer races the ask timeout | Delivery happens under the registry lock; an expired question makes `answer` return `invalid_state`. |
| `refract ask` client hang | Client timeout of `ask_timeout_s` plus 10 s. |
| Revoked ask tokens accumulate | Only active tokens with deadlines are stored; the revoked set is deleted. |
| Grandchild holds stdout | Covered by the 2 s post-exit grace and group kill. |
| Non-UTF-8 output | Decoded with replacement characters; never silently truncated. |
| Stdin write failure | Fails the attempt with `request_fatal` and the error text. |
| Parser or emitter exception | Fails the attempt with the exception type and message in `error`. |
| Sticky target removed or circuit open | Profile order applies; success updates `sticky_target`. |
| `retry(target=X)` with unknown target | `invalid_request` listing the profile's targets. |
| Tool activity then failure | `replay_blocked`; no fresh restart. |
| Result over the response cap | `text` truncated, `truncated=true`, full text at `result_path`. |
| `submit` path not in a Git repository | `invalid_path`. |

## Migration

- On first v3 start, `refract.db`, `refract.db-wal`, and `refract.db-shm` are renamed to `*.v2.bak` and a fresh schema is created.
- Old config keys fail load with replacement hints. The README gains a migration section and a v3 example config.
- Plugin updates in the same plan: `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`, Gate 2 failure handling in `coordinating-multi-model-work`, `executing-plans` and its implementer prompt, MCP server instructions, README.
- Cutover, done by the owner after consolidation: prepare `~/.refract/config.toml` from a `config.v3.toml` draft, confirm no active jobs, merge, restart the daemon.

## Testing

- Characterization tests before each behavior-preserving refactor. Tests of deleted features are deleted with them.
- Transport tests against fake CLI scripts: grandchild holding the pipe, non-UTF-8 output, 1 MiB stdin prompt, timeout, cancel, group kill, crash cleanup.
- MCP contract test: exact schemas of the 6 tools; no removed field in any response.
- Tests for the database rename, each removed config key error, the ask race, sticky target selection, `retry` from each accepted state, and HTML escaping on dashboard pages.
- Phase validation command, because `uv sync` currently fails on PyPI 404s for `iniconfig` and `cryptography` wheels:

```bash
cd /home/ngosi/.worktrees/refract/refract-v3-simplification/server && PYTHONPATH=$PWD/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider
```

- Baseline at plan base `232aab7c`: 1201 passed, 23 skipped, 15 deselected.
- One manual smoke run per real CLI at the end.

## Risks and Open Questions

- Open: whether `pi` and `agy` accept the prompt on stdin. Phase 3 verifies first. Fallback order: mode-600 temp file path argument if supported, otherwise argv with a clear failure above 100 KiB.
- Risk: six open worktree branches, including `remove-legacy-metadata`, `telemetry-investigate`, and `improve-diagnostic`, will conflict with this rework. The owner decides whether to merge or abandon them first.
- Risk: the coordinator uses Refract v2 to build v3. Mitigation: worktree isolation and no daemon restart until cutover.
- Risk: the 9,000-line target is an estimate from two audits, not a measurement.
- Risk: the `uv sync` failure blocks a clean environment rebuild; the validation command depends on the main checkout venv.
