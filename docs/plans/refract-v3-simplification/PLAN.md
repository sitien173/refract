# Refract v3 Simplification Plan

**Design:** [DESIGN.md](DESIGN.md)
**Context key:** `refract-v3-simplification`
**Base:** `refs/plans/refract-v3-simplification/base` (`232aab7cc9fe7e96cc41eb3175328f90c118b5bc`)
**Commit:** `feat!: simplify refract to a six-tool v3 surface`

## Outcome & Scope

Refract v3 as specified in DESIGN.md: six MCP tools, no result paging, one async process transport shared by four backends, a fresh SQLite schema, flat config, flat token counters, three server-rendered dashboard pages, and no Langfuse.

Preserved invariants, all phases:

- Per-project FIFO admission, at most one running job per project, global `max_jobs`.
- Per-target `max_concurrency`, circuit breaker with half-open probe.
- `replay_blocked` after any tool activity.
- Process-group isolation and tree termination in `processes.py`.
- Startup reconciliation of running and queued jobs.
- Target key in session identity.
- Worker ask flow through loopback `POST /ask`.
- Loopback-only dashboard and `/ask`.
- Backends `claude`, `codex`, `pi`, `agy`.

Out of scope, all phases:

- The v2 daemon and checkout at `/home/ngosi/projects/refract`. Never restart the daemon, never edit outside the worktree.
- `~/.refract/config.toml`, `~/.refract/refract.db`, and any file under `~/.refract`. Tests use temporary directories.
- Version bump, release, CHANGELOG release entry.
- Other `docs/plans/*` folders.
- Automatic cross-target fallback, v2 data or config migration, multi-user access.

All paths below are relative to the worktree root `/home/ngosi/.worktrees/refract/refract-v3-simplification`.

## Verification Commands

- **PYTEST**: `cd /home/ngosi/.worktrees/refract/refract-v3-simplification/server && PYTHONPATH=$PWD/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider`
- **PLUGIN**: `cd /home/ngosi/.worktrees/refract/refract-v3-simplification && bash plugin/tests/test-session-start.sh && bash plugin/tests/test-contracts.sh && bash plugin/tests/test-stats.sh`
- **LINES**: `cd /home/ngosi/.worktrees/refract/refract-v3-simplification && find server/src/refract -name '*.py' -exec cat {} + | wc -l`

`uv sync` fails on PyPI 404s for `iniconfig` and `cryptography`, so PYTEST uses the main checkout venv with `PYTHONPATH` pointing at the worktree source.

## Baseline Evidence

Recorded 2026-11-04 at `232aab7c`:

- PYTEST: 1201 passed, 23 skipped, 15 deselected.
- PLUGIN: `test-session-start.sh` passed. `test-contracts.sh` **failed**: `AssertionError` at file line 153, `assert "## Reported successful output recovery" in contract`; commit `38f97c55` removed that section from `tool-contract.md`. `test-stats.sh` not reached by the chained command; run alone it passed. Phase 1 repairs the failure.
- LINES: 13484.

### Phase 1: Repair baseline, delete Langfuse and the React dashboard

**Task Guide Input:** Repair the failing plugin contract test, then delete two subsystems without replacing them: Langfuse tracing and the React dashboard with its JSON API. Keep `POST /ask` working. Use cases: plugin tests pass; config containing `[langfuse]` fails load with a removal message; the server starts and serves `/ask` with no dashboard routes; no Langfuse import remains.
**Goal:** A green baseline with Langfuse and the React dashboard gone.
**Invariants & Boundaries:** `/ask` behavior, loopback guard, and token checks are unchanged. Job execution, MCP tools, and storage are unchanged. The SSR dashboard is Phase 7; do not build it here. Logging config is Phase 6.
**Files:**
- Modify: `plugin/tests/test-contracts.sh`
- Delete: `server/src/refract/observability.py`, `server/tests/test_observability.py`
- Modify: `server/src/refract/ask.py`, `server/src/refract/server.py`, `server/src/refract/runtime.py`, `server/src/refract/execution.py`, `server/src/refract/config.py`, `server/src/refract/config_inspection.py` (added in Phase 1 clarification: allow-list the removal message), `server/pyproject.toml`, `server/uv.lock`
- Modify: `server/tests/test_runtime.py`, `server/tests/test_server.py`, `server/tests/test_execution.py`, `server/tests/test_config.py`
- Delete: `server/web/` (whole directory), `server/src/refract/dashboard_static/index.html`, `server/src/refract/dashboard_static/assets/`
- Modify: `server/src/refract/dashboard.py` (reduce to the `/ask` route and loopback guard), `server/tests/test_dashboard.py`, `server/tests/test_ask.py`
- Delete: `server/tests/test_dashboard_consolidation.py`
- Modify: `README.md`, `server/README.md` (remove Langfuse and React dashboard sections only)
**Tasks:**
1. Remove the stale "Reported successful output recovery" assertions from `test-contracts.sh` so it checks the current `tool-contract.md`. Change no skill text.
2. Delete Langfuse: `observability.py`, every tracer call site, the `[langfuse]` config dataclass and parsing, the `langfuse` optional dependency. A config with `[langfuse]` raises the existing config error type with a message containing `langfuse` and `removed`. Regenerate `server/uv.lock` with `uv lock`; if the registry error blocks it, leave `uv.lock` unchanged and report that in the ERP.
3. Delete the React dashboard and the dashboard JSON routes. Keep `/ask` and `pyproject.toml` package artifacts consistent with what still exists. Delete or rewrite dashboard tests so only `/ask` and loopback coverage remain.
**Acceptance Criteria:**
- PLUGIN passes.
- PYTEST passes.
- `git grep -niE 'langfuse|observability' -- server/src server/tests server/pyproject.toml` prints nothing.
- `server/web` does not exist.
- A test proves `[langfuse]` in config fails load naming the removal.
- A test proves `POST /ask` from loopback still reaches the registry and a non-loopback client gets 403.
**Reviewer Checklist:**
- No skill or contract text changed in task 1; only test assertions.
- `/ask` loopback, token, and timeout behavior unchanged.
- No dashboard route remains other than `/ask`.
- `uv.lock` either regenerated or explicitly reported unchanged.
**Verification Checks:**
- PLUGIN
- PYTEST
- `cd /home/ngosi/.worktrees/refract/refract-v3-simplification && ! git grep -niE 'langfuse|observability' -- server/src server/tests server/pyproject.toml`

### Phase 2: Async process transport

**Task Guide Input:** Replace the thread-based subprocess transport with one asyncio transport used by all four backends. First establish how `pi` and `agy` can receive a prompt without argv, from their installed `--help` output. Use cases: grandchild holding stdout, non-UTF-8 output, 1 MiB prompt on stdin, timeout, cancel, process-group kill, stdin write failure, parser exception.
**Goal:** Every backend runs through one `async run_process` with no worker threads.
**Invariants & Boundaries:** Backend parsers, argv flags, session resume, classification, and result shapes are unchanged except for prompt delivery. `processes.py` group isolation is reused. Storage, MCP surface, and backend deduplication are out of scope.
**Files:**
- Create: `server/src/refract/backends/_process.py`, `server/tests/test_transport.py`, `server/tests/fixtures/fake_cli/` (small executable Python scripts)
- Delete: `server/src/refract/backends/_shell.py`
- Modify: `server/src/refract/backends/__init__.py`, `server/src/refract/backends/claude.py`, `server/src/refract/backends/codex.py`, `server/src/refract/backends/pi.py`, `server/src/refract/backends/agy.py`
- Modify: `server/src/refract/drivers.py` (delete `StreamBridge` and `asyncio.to_thread`), `server/src/refract/execution.py`, `server/src/refract/processes.py`
- Modify: `server/tests/test_processes.py`, `server/tests/test_smoke.py`, `server/tests/test_ask.py`, `server/tests/test_drivers.py`, `server/tests/test_execution.py`, `server/tests/test_async_workers.py`, `server/tests/test_streaming_backends.py`
**Tasks:**
1. Record `pi --help` and `agy --help` prompt-input options in the ERP. Choose per DESIGN.md: stdin, else mode-600 temp file path argument, else argv with a clear `request_fatal` above 100 KiB.
2. Write `run_process(argv, stdin, env, cwd, deadline, cancel)` on `asyncio.create_subprocess_exec`: new session, stderr merged, prompt written then stdin closed, `errors="replace"` decoding, 1 MiB line limit, 2 s post-exit EOF grace then group kill, immediate group kill on timeout or cancel, 64 KiB output tail plus error lines. Stdin write failure and parser or callback exceptions fail the attempt with the exception type and message. Test-first against fake CLI scripts.
3. Move all four backends onto `run_process` as async callables; delete `_shell.py`, `StreamBridge`, and `to_thread`. Event callbacks run on the loop and call the existing stream recorder and telemetry accumulator directly.
**Acceptance Criteria:**
- PYTEST passes, including `test_transport.py` cases for each use case above.
- `git grep -nE 'to_thread|StreamBridge|_shell|threading' -- server/src/refract/backends server/src/refract/drivers.py` prints nothing.
- A fake CLI that backgrounds a grandchild holding stdout and exits finishes within 5 s of exit.
- A 1 MiB prompt reaches a stdin-reading fake CLI intact.
**Reviewer Checklist:**
- Group kill happens on every exit path, including exceptions.
- No unbounded buffer of all lines or events remains.
- `pi` and `agy` prompt delivery matches the recorded `--help` evidence.
- Cancellation propagates; no `CancelledError` is swallowed.
**Verification Checks:**
- PYTEST
- `cd /home/ngosi/.worktrees/refract/refract-v3-simplification && ! git grep -nE 'to_thread|StreamBridge|_shell|threading' -- server/src/refract/backends server/src/refract/drivers.py`

> Scope change (2026-11-04, coordinator): Phase 2 delivered the transport only (`backends/_process.py`, `kill_process_tree`, transport tests). Migrating the four backends onto it, deleting `_shell.py`, `StreamBridge` and `to_thread`, and the Phase 2 grep acceptance moved to Phase 3, because a bounded output tail requires the per-run `feed`/`outcome` parser state that Phase 3 introduces. `run_process` must take an asyncio cancel signal, not `threading.Event`. agy keeps the prompt in argv with a clear failure above 100 KiB; its stream-json input schema is undocumented. pi reads the prompt from stdin.

### Phase 3: Backend protocol, deduplication, in-run recovery removed

**Task Guide Input:** Give the four backends one protocol and one shared execute path, fix the Codex output and session defects, and remove in-run recovery. Use cases: Codex exits 0 with only event lines; Codex has no exact rollout match; a resume fails with `context_overflow`; a resume fails after tool activity.
**Goal:** Backends differ only in argv, parser, and outcome; each attempt makes one backend call.
**Invariants & Boundaries:** Parsed token values and session IDs for existing fixtures are unchanged. `replay_blocked` is unchanged. Storage schema, MCP surface, and config format are out of scope; `context_turns` stays in the schema but is no longer read or written.
**Files:**
- Create: `server/src/refract/backends/_common.py`, `server/src/refract/backends/codex_rollout.py`
- Modify: `server/src/refract/backends/__init__.py`, `server/src/refract/backends/claude.py`, `server/src/refract/backends/codex.py`, `server/src/refract/backends/pi.py`, `server/src/refract/backends/agy.py`, `server/src/refract/drivers.py`
- Modify: `server/src/refract/execution.py`, `server/src/refract/database.py`, `server/src/refract/config.py`
- Modify: `server/tests/test_streaming_backends.py`, `server/tests/test_drivers.py`, `server/tests/test_execution.py`, `server/tests/test_database.py`, `server/tests/test_config.py`
**Tasks:**
1. Characterize current per-backend parse results on `server/tests/fixtures/usage/*` before refactoring. Then define the `Backend` protocol (`argv`, per-run parser with `feed(line)`, `outcome()`), move shared helpers to `_common.py`, write preflight, classification, telemetry guard, and error precedence once. Backends stop reading `TelemetryAccumulator` private fields.
2. Move `_CodexRolloutCollector` to `codex_rollout.py`. Codex without an agent message returns `request_fatal` with `no agent message`, never raw JSONL. Delete the cwd session heuristic; no exact match stores no session ID.
3. Delete the `reconstruct` attempt phase, history rebuilding, `context_turns` reads and writes, and config `history_turns` and `history_bytes`; loading either key fails with the config error type naming the removal. Owner decision 2026-11-04: in-run recovery is removed completely, with no fresh restart on the same target. A resumed `context_overflow` fails with `failure_kind` `context_overflow`, and the coordinator resubmits with `fresh_session=true`. Any other resume failure goes through the retry policy. A failure after tool activity is `replay_blocked`.
**Acceptance Criteria:**
- PYTEST passes; characterization tests from task 1 pass unchanged after the refactor.
- `git grep -nE 'reconstruct|history_turns|history_bytes|context_turns' -- server/src` prints only the `context_turns` table DDL in `database.py`.
- `git grep -nE 'accumulator\._' -- server/src/refract/backends` prints nothing.
- Tests cover both Codex defects, a resumed `context_overflow` failing without recovery, and a resume failure after tool activity being `replay_blocked`.
**Reviewer Checklist:**
- Characterization tests were written before the refactor and not weakened after.
- Error precedence per backend is preserved.
- `history_turns` and `history_bytes` fail load; they are not silently ignored.
**Verification Checks:**
- PYTEST
- LINES

### Phase 4: Six-tool MCP surface and plugin contract

**Task Guide Input:** Replace the nine MCP tools with `submit`, `wait`, `answer`, `cancel`, `retry`, `list` exactly as DESIGN.md specifies, fix the ask defects, and rewrite the plugin contract and skills for v3. Use cases: submit from a subdirectory resolves the Git root; submit outside Git fails `invalid_path`; long result truncated with `result_path`; retry from each of `succeeded`, `failed`, `cancelled`, `interrupted`; retry with unknown target; sticky target reused, removed, or circuit-open; pending question; answer after ask timeout; `refract ask` against an unresponsive server.
**Goal:** A coordinator completes a job with `list`, `submit`, `wait` and recovers with `retry`.
**Invariants & Boundaries:** Admission, circuit breaker, and `replay_blocked` unchanged. The v2 `jobs` columns stay; add only the columns this phase needs through one additive migration. The fresh schema is Phase 5. Do not edit `/home/ngosi/projects/refract/plugin`; edit only the worktree copy.
**Files:**
- Modify: `server/src/refract/server.py`, `server/src/refract/runtime.py`, `server/src/refract/database.py`, `server/src/refract/models.py`, `server/src/refract/scheduler.py`, `server/src/refract/planning.py`, `server/src/refract/execution.py`
- Modify: `server/src/refract/ask.py`, `server/src/refract/cli.py`
- Modify: `server/tests/test_server.py`, `server/tests/test_mcp_schema_contract.py`, `server/tests/test_runtime.py`, `server/tests/test_database.py`, `server/tests/test_scheduler.py`, `server/tests/test_ask.py`, `server/tests/test_planning.py`, `server/tests/test_result_metadata.py`, `server/tests/test_retention.py`, `server/tests/orchestration_helpers.py`
- Modify: `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`, `plugin/skills/coordinating-multi-model-work/SKILL.md`, `plugin/skills/coordinating-multi-model-work/references/review.md`, `plugin/skills/coordinating-multi-model-work/references/handover.md`, `plugin/skills/executing-plans/SKILL.md`, `plugin/skills/executing-plans/implementer-prompt.md`, `plugin/skills/writing-plans/SKILL.md`, `plugin/skills/setting-up-refract/SKILL.md`, `plugin/hooks/refract-session-start.sh`, `plugin/pi/extensions/refract.ts`, `plugin/tests/test-contracts.sh`, `plugin/tests/test-session-start.sh`
- Modify: `README.md`, `server/README.md`, `server/CLI_ARGUMENTS.md` (tool sections only)
**Tasks:**
1. Runtime: resolve the Git root with `git rev-parse --show-toplevel`; `sessions.sticky_target`; target selection sticky-first then profile order; `retry` creates a new job with `retry_of`, never mutating the source; `next_target` as a plain target name; result text always written to `~/.refract/results/<job_id>.md` under the configured state directory. One additive schema migration.
2. MCP: the six tools with the exact parameters and response fields in DESIGN.md; delete `project_resolve`, `task_guide`, `job_list`, `job_report_error`, opaque tokens, `result_offset`, `retryable`, and `_FORBIDDEN_OUTPUT_KEYS`; MCP server instructions rewritten for the six tools. Contract test asserts exact tool schemas and absence of every removed field.
3. Ask: deliver the answer under the registry lock and return `invalid_state` for an expired question; store only active tokens with deadlines and delete the revoked set; `refract ask` client timeout `ask_timeout_s + 10` s.
4. Plugin and docs: rewrite `tool-contract.md` and every listed skill, hook, and extension reference for the six tools, `session`, and `fresh`; update plugin tests to assert the new contract.
**Acceptance Criteria:**
- PYTEST and PLUGIN pass.
- The MCP contract test lists exactly six tools.
- `git grep -nE 'project_resolve|task_guide|job_report_error|job_list|result_offset|retryable\b|next_offset|fresh_session|context_key' -- server/src plugin README.md server/README.md` prints nothing, except the `task_guide.json` file name.
- Tests cover every use case in the Task Guide Input.
**Reviewer Checklist:**
- Retry never mutates the source job's row or result file.
- Git root resolution has no shell injection and handles a non-Git path.
- Result file permissions are 0600 and the directory is under the configured state directory.
- Skill text stays consistent across all edited plugin files.
**Verification Checks:**
- PYTEST
- PLUGIN
- `cd /home/ngosi/.worktrees/refract/refract-v3-simplification && ! git grep -nE 'project_resolve|job_report_error|job_list|result_offset|next_offset|fresh_session|context_key' -- server/src plugin README.md server/README.md`

### Phase 5: Fresh storage and flat telemetry

**Task Guide Input:** Replace the migration chain with one fresh v3 schema, move live output and results to files, flatten telemetry into integer counters, and clean up orphaned worker groups after a daemon crash. Use cases: first start with a v2 `refract.db` present; live output while a job runs; history pruning; token counters on success and failure; daemon restart with a job that was running.
**Goal:** Storage holds the DESIGN.md tables only, and the telemetry measurement model is gone.
**Invariants & Boundaries:** MCP response shapes from Phase 4 are unchanged. Startup reconciliation semantics are unchanged apart from the added group kill. Config format is Phase 6; dashboard is Phase 7.
**Files:**
- Modify: `server/src/refract/database.py`, `server/src/refract/runtime.py`, `server/src/refract/execution.py`, `server/src/refract/models.py`, `server/src/refract/server.py`, `server/src/refract/scheduler.py`, `server/src/refract/processes.py`, `server/src/refract/backends/__init__.py`, `server/src/refract/backends/_common.py`, `server/src/refract/notifications.py`, `server/src/refract/config_inspection.py`
- Delete: `server/src/refract/streaming.py`, `server/src/refract/result_metadata.py`, `server/tests/test_streaming.py`, `server/tests/test_result_metadata.py`
- Rewrite: `server/src/refract/telemetry.py` (flat counters only), `server/tests/test_telemetry.py`
- Modify: `server/tests/test_database.py`, `server/tests/test_database_atomicity.py`, `server/tests/test_database_workers.py`, `server/tests/test_retention.py`, `server/tests/test_runtime.py`, `server/tests/test_execution.py`, `server/tests/test_server.py`, `server/tests/test_notifications.py`, `server/tests/test_processes.py`, `server/tests/orchestration_helpers.py`
**Tasks:**
1. One initial schema with `projects`, `jobs`, `sessions`, `target_sessions`, `target_health` exactly as DESIGN.md. On open, an existing pre-v3 database and its `-wal` and `-shm` files are renamed to `*.v2.bak`. Delete all v2 migrations.
2. Live output appended to `streams/<job_id>.jsonl` with an in-memory tail; results in `results/<job_id>.md`; pruning deletes both files with the job. Delete `StreamRecorder`, `JobStreamHub`, `job_stream_events`, and `events`.
3. Telemetry: six nullable integer `tok_*` columns updated from backend outcomes; delete the measurement model (`value`, `source`, `quality`, `observed_at`) and `result_metadata.py`.
4. Record `jobs.pgid` at launch; at startup, kill the group of each job marked `interrupted`.
**Acceptance Criteria:**
- PYTEST passes.
- A test opens a v2 fixture database and finds `*.v2.bak` files plus a v3 schema.
- `git grep -nE 'job_stream_events|StreamRecorder|JobStreamHub|observed_at|context_turns|result_metadata' -- server/src` prints nothing.
- A test starts a fake long-running worker group, simulates restart, and proves the group is killed.
**Reviewer Checklist:**
- The rename never deletes data and never touches a v3 database.
- Stream and result files are 0600 and pruned with their job.
- Token counters are null when unknown, never zero-filled.
- Startup group kill cannot target a reused PID group of an unrelated process; check the guard used.
**Verification Checks:**
- PYTEST
- LINES
- `cd /home/ngosi/.worktrees/refract/refract-v3-simplification && ! git grep -nE 'job_stream_events|StreamRecorder|JobStreamHub|observed_at|context_turns|result_metadata' -- server/src`

### Phase 6: Flat config and logging

**Task Guide Input:** Flatten the config to the DESIGN.md v3 format, trim logging, and give every removed key an error naming its replacement. Write the v3 example config and README migration section. Use cases: each removed key; project overlay adding a profile, target, and env; `extends` with a cycle; inline `retry` on a target.
**Goal:** One snake_case config format with inline retry and one env table per target.
**Invariants & Boundaries:** Profile `extends` and its cycle check stay. Target key derivation still covers settings and env. Do not read or edit `~/.refract/config.toml`.
**Files:**
- Modify: `server/src/refract/config.py`, `server/src/refract/config_inspection.py`, `server/src/refract/planning.py`, `server/src/refract/logging_setup.py`, `server/src/refract/cli.py`, `server/src/refract/runtime.py`, `server/src/refract/execution.py`, `server/src/refract/server.py`
- Modify: `server/tests/test_config.py`, `server/tests/test_config_inspection.py`, `server/tests/test_planning.py`, `server/tests/test_environment.py`, `server/tests/test_logging.py`, `server/tests/test_target_capacity.py`
- Create: `server/config.v3.toml`
- Modify: `README.md`, `server/README.md`, `server/CLI_ARGUMENTS.md`
**Tasks:**
1. Config: snake_case keys, inline `retry = { attempts, codes, patterns }`, one `env` table per target, project overlay limited to `profiles`, `targets`, `env`. Delete named retry policies, shared env sets, `envs_vars`, `${}` templating, legacy routing shims, `max_attempts`, and dashboard provenance. A removed-key table produces load errors naming each replacement; fold Phase 1's `[langfuse]` error into it.
2. Logging: keep `level`, `file`, `max_bytes`, `backup_count`, redaction, and file permissions on the stdlib rotating handler; delete the JSON formatter, console handler, queue machinery, and warning capture, and reject their keys through the removed-key table.
3. Docs: `server/config.v3.toml` exercising every v3 key with all four backends; README migration section listing each removed key and its replacement.
**Acceptance Criteria:**
- PYTEST passes.
- `server/config.v3.toml` loads without error in a test.
- One parametrized test covers every removed key's error message.
- `git grep -nE 'retryPolicies|retryPolicy|envs_vars|contextWindow|task_routes|routing_profile' -- server/src` prints only removed-key table entries.
**Reviewer Checklist:**
- No removed key is silently ignored.
- Env values containing secrets stay redacted in logs and errors.
- `config.v3.toml` contains no real credentials.
**Verification Checks:**
- PYTEST
- LINES

### Phase 7: Server-rendered dashboard and final success check

**Task Guide Input:** Build the three server-rendered dashboard pages and the output polling endpoint from DESIGN.md using vendored TDS CSS, then verify the plan's success criteria. Use cases: job list; job detail for a running and a finished job; targets page with an open circuit and a config error; output polling with `after=N`; HTML-special characters in prompt and output; non-loopback request.
**Goal:** A minimal live dashboard and a verified v3 that meets every DESIGN.md success criterion.
**Invariants & Boundaries:** No JavaScript build step, no template engine, no new dependency. Light theme and official `tds-*` classes only; run `tds rules` and `tds search` before writing markup. Loopback only.
**Files:**
- Modify: `server/src/refract/dashboard.py`, `server/src/refract/server.py`, `server/pyproject.toml`
- Create: `server/src/refract/dashboard_static/tds/` (`tokens.css`, `fonts.css`, and only the component CSS the pages use, copied from the TDS source recorded in the ERP)
- Modify: `server/tests/test_dashboard.py`
- Modify: `README.md`, `server/README.md`
**Tasks:**
1. Pages `/dashboard`, `/dashboard/jobs/{id}`, `/dashboard/targets`, and JSON `/dashboard/jobs/{id}/output?after=N`, built with `html.escape`; about 30 lines of inline JS poll output while the job is active.
2. Tests for each use case, including escaping and the loopback guard.
3. Success check: record LINES, PYTEST, PLUGIN, and the six-tool contract test in the ERP; LINES must be at most 9000.
**Acceptance Criteria:**
- PYTEST and PLUGIN pass.
- LINES prints a value at most 9000.
- A test proves `<script>` in a prompt renders escaped.
- `server/web` does not exist and no route other than the four dashboard routes and `/ask` is mounted on the HTTP app besides the MCP endpoint.
**Reviewer Checklist:**
- Every interpolated value passes through `html.escape`.
- CSS classes exist in the vendored TDS files; no invented colors.
- Poll stops when the job is terminal.
**Verification Checks:**
- PYTEST
- PLUGIN
- `cd /home/ngosi/.worktrees/refract/refract-v3-simplification && test "$(find server/src/refract -name '*.py' -exec cat {} + | wc -l)" -le 9000`

## After Consolidation (owner)

1. Run one manual job per real CLI: `claude`, `codex`, `pi`, `agy`.
2. Write `~/.refract/config.toml` from `server/config.v3.toml`, confirm no active v2 jobs, merge the branch, restart the daemon.
