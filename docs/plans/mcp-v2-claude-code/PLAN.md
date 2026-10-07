# OpenMCP v2 for Claude Code Implementation Plan

Design: [DESIGN.md](DESIGN.md)

Replace the v1 MCP surface with seven Claude Code-oriented tools, fold in job
dependencies and parallel readers, mirror the vocabulary in the dashboard, and
ship superpowers-ccg v12 in lockstep.

**Commit:** `feat!: ship OpenMCP v2 MCP surface for Claude Code with job dependencies`

superpowers-ccg consolidates separately in its own root:
`feat!: adopt OpenMCP v2 tool contract`

## Baseline

At plan base `refs/plans/mcp-v2-claude-code/base` (`491e043`):

| Root | Command | Result |
|---|---|---|
| `/home/ngosi/projects/openmcp` | `uv run --extra dev pytest -q` | 461 passed, 3 deselected |
| `/home/ngosi/projects/openmcp` | `npm --prefix web test` | 196 passed, 18 files |
| `/home/ngosi/projects/superpowers-ccg` at `8528355` | `bash tests/run.sh` | passed |

`uv run pytest -q` without `--extra dev` fails collection: the project `.venv`
lacks the `dev` extra, so a system pytest on Python 3.14 runs without `openmcp`.
Every command below uses `--extra dev`.

## Execution Constraints

- The live daemon is `openmcp.service`, a pipx editable install of this
  checkout. A restart loads the code on disk and interrupts running jobs.
  Restart only in Phase 1 and Phase 7, only with no active job:
  `systemctl --user restart openmcp.service`.
- An unplanned restart between Phase 2 and Phase 6 loads intermediate code.
  If it happens, stop and report before submitting another job.
- superpowers-ccg skills load from `/home/ngosi/projects/superpowers-ccg`.
  Phase 6 edits the Coordinator's own live instructions, so it runs after all
  OpenMCP phases and immediately before the Phase 7 restart.
- Phase 6 runs in a separate Git root with its own anchors under
  `refs/plans/mcp-v2-claude-code/` in that repository. It changes only Markdown,
  a Bash test, and version fields.
- `docs/plans/profile-config-fragments` is `ACTIVE` and may touch
  `src/openmcp/config.py` and the dashboard. Do not run both plans at once.
- Phases 2 to 5 add tests only to existing test files, so every command below
  exists at plan base.

---

### Phase 1: Heartbeat wait and progress-token probe

**Task Guide Input:** Change the existing v1 `job_wait` MCP tool in
`src/openmcp/server.py` so one call can block up to 3600 seconds while emitting
progress notifications every 30 seconds, and log whether each `job_wait`
request carried an MCP progress token. Two distinct use cases: (a) replace the
single pre-wait and post-wait progress report with a heartbeat loop driven by an
injectable interval, keeping v1 tool names and return shapes; (b) add
observability that records progress-token presence per request. Add tests in
`tests/test_server.py`.

**Profile:** `Resolve at execution`

**Goal:** Live evidence decides whether criterion a is achievable before any v2 work.

**Files:**
- Modify: `src/openmcp/server.py`
- Modify: `tests/test_server.py`
- Modify: `src/openmcp/logging_setup.py`
- Modify: `tests/test_logging.py`

The user approved the logging-file scope extension on 2026-10-07 after a
production-formatter reproduction showed the presence boolean was hidden.

**Tasks:**
1. Raise `_MCP_WAIT_TIMEOUT_S` to 3600. Add a module-level heartbeat interval of
   30 seconds that tests can override. In `job_wait`, report progress
   immediately, then every interval until the job is terminal or `timeout_s`
   elapses. Each message carries the job state.
2. Read the progress token from `ctx.request_context.meta` and log
   `progress_token_present` as a boolean on the `job_wait` request log. Never log
   the token value.
3. Tests: heartbeat count over a short injected interval with a job that
   finishes after several intervals; immediate return for a terminal job;
   timeout returns the current non-terminal job; token presence logged both ways.
4. Preserve only the exact boolean `progress_token_present` field in production
   JSON and text log output. Keep token values and non-boolean values redacted.
   Add formatter regression coverage for both boolean values and redaction.

**Acceptance Criteria:**
- Tests prove progress is emitted at the injected interval until terminal.
- `job_wait` with `timeout_s` above 3600 is capped at 3600.
- Coordinator live evidence, after the restart:
  - daemon log shows `progress_token_present` for a Claude Code `job_wait`;
  - a `job_wait` on a job lasting at least 6 minutes returns a terminal result
    from the main conversation and from a subagent;
  - one invalid call, `job_wait` with an unknown job ID, shows the exact error
    text Claude Code receives; record it in the phase journal.
- If the token is absent or a 6-minute wait fails, set handover `BLOCKED` and
  ask the user to choose the design fallback before Phase 2.

**Reviewer Checklist:**
- No sleep-based timing in tests; the interval is injected.
- The heartbeat loop exits on terminal state, timeout, and cancellation.
- The token value is never logged.

**Verification Checks:**
- `uv run --extra dev pytest tests/test_server.py tests/test_logging.py -q`
- `uv run --extra dev pytest -q`

---

### Phase 2: Dependency persistence, access classes, and reader capacity

**Task Guide Input:** Implement the persistence and configuration layer of the
confirmed parallel-readers and job-dependencies design in
`docs/plans/parallel-readers-job-dependencies/DESIGN.md`, as overridden by
`docs/plans/mcp-v2-claude-code/DESIGN.md`. Distinct use cases: (a) a SQLite
schema migration adding a per-job `access_mode` and an immutable
`job_dependencies` table, with existing jobs migrated to `exclusive`;
(b) deriving `access_mode` from the immutable execution-plan snapshot and
adapter read-only enforcement; (c) a startup-bound `max_project_readers`
daemon setting, default 1, accepted by configuration mutation. No scheduler or
MCP surface change.

**Profile:** `Resolve at execution`

**Goal:** Jobs persist an access class and dependency links, and the reader limit is configurable.

**Files:**
- Modify: `src/openmcp/database.py`
- Modify: `src/openmcp/planning.py`
- Modify: `src/openmcp/drivers.py`
- Modify: `src/openmcp/config.py`
- Modify: `src/openmcp/config_mutation.py`
- Modify: `tests/test_database.py`
- Modify: `tests/test_planning.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_config_mutation.py`

**Tasks:**
1. Add the next schema version in `Database._migrate`: `access_mode` on jobs and
   `job_dependencies(job_id, dependency_job_id)` with a unique pair, foreign
   keys to jobs, and an index on `dependency_job_id`. Existing jobs become
   `exclusive`. Add atomic create-job-with-dependencies and reverse-lookup
   methods.
2. Derive `access_mode` in `planning.py`: `parallel_read` only when every
   possible target, fallbacks included, is configured read-only and its driver
   reports verified read-only enforcement in `drivers.py`. Otherwise `exclusive`.
3. Add `max_project_readers` to daemon configuration, positive integer,
   default 1, and accept it in configuration mutation.

**Acceptance Criteria:**
- Migrating a database at the base schema leaves every existing job `exclusive`
  with no dependency rows.
- Unknown, duplicate, and other-project dependency IDs reject creation with no
  job or link row persisted.
- Mixed or unverified target plans derive `exclusive`.
- `max_project_readers` of 0 or a non-integer is rejected.

**Reviewer Checklist:**
- Job and links insert in one transaction.
- Links are immutable; no update path exists.
- An advisory prompt never counts as read-only enforcement.

**Verification Checks:**
- `uv run --extra dev pytest tests/test_database.py tests/test_planning.py tests/test_config.py tests/test_config_mutation.py -q`
- `uv run --extra dev pytest -q`

---

### Phase 3: Reader/writer admission and dependency scheduling

**Task Guide Input:** Implement scheduler admission and dependency lifecycle
from the confirmed parallel-readers and job-dependencies design, as overridden by
`docs/plans/mcp-v2-claude-code/DESIGN.md`. Distinct use cases: (a)
reader/writer project admission with session-scope serialization and
exclusive-barrier fairness; (b) dependency readiness that reserves no capacity,
with transitive cascade cancellation; (c) retry and restart-recovery semantics
for dependent jobs. Runtime `submit` accepts `depends_on`. Completion waiters
are released for cascaded cancellations. No MCP surface change.

**Profile:** `Resolve at execution`

**Goal:** Independent readers overlap, writers stay exclusive, and dependents run only after every dependency succeeds.

**Files:**
- Modify: `src/openmcp/scheduler.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `src/openmcp/execution.py`
- Modify: `src/openmcp/models.py`, only `ActionResult.cancelled_dependents`, approved by the user on 2026-10-07
- Modify: `tests/test_scheduler.py`
- Modify: `tests/test_runtime.py`
- Modify: `tests/test_execution.py`

**Tasks:**
1. Replace per-project FIFO admission with reader/writer admission bounded by
   `max_project_readers`, serialize identical `project_id + workflow +
   context_key` scopes, and make the earliest dependency-ready exclusive job a
   barrier for later readers.
2. Add `depends_on` to `Runtime.submit`. Dependency-blocked jobs stay queued
   without reserving workers or admission. Unsuccessful dependencies cancel
   queued descendants transitively, recording the causal dependency; submitting
   against one creates an already-cancelled job. Reevaluate through reverse
   links, never by polling.
3. Retry keeps job ID and links, queues with waiting when a dependency is
   unfinished, and raises a dependency-specific error when one is terminally
   unsuccessful. Parent retry never revives descendants. Restart recovery marks
   running jobs `interrupted` and propagates cancellation before admitting
   queued dependents.
4. Expose derived `waiting_on` and `waiting_reason` for queued jobs, and return
   cascaded dependent IDs from `Runtime.cancel`.

**Acceptance Criteria:**
- Every row of the dependency design's Testing table has a passing test.
- With default `max_project_readers = 1`, existing FIFO and cross-project
  regression tests pass unchanged.
- Cancellation cascades across at least three dependency levels.

**Reviewer Checklist:**
- Readiness checks and reservations share one synchronization boundary.
- Every reservation is released on completion, cancellation, exception, and shutdown.
- Tests use deterministic events, not sleeps.

**Verification Checks:**
- `uv run --extra dev pytest tests/test_scheduler.py tests/test_runtime.py tests/test_execution.py -q`
- `uv run --extra dev pytest -q`

---

### Phase 4: MCP v2 tool surface

**Task Guide Input:** Replace the v1 MCP surface in `src/openmcp/server.py` with
the seven v2 tools specified in `docs/plans/mcp-v2-claude-code/DESIGN.md`.
Distinct use cases: (a) a structured error class whose message is one JSON line
with code, message, next_action, and retryable, plus internal-error conversion
in the request logging wrapper; (b) the seven tools with titles, annotations,
parameter descriptions, enum and range limits, server instructions, and server
title; (c) idempotent path-keyed project resolution, bounded job listing, and
paged results; (d) removal of every v1 tool, resource, subscription, legacy
direct-run facade, and resource-URI field, with job notifications keyed by job
ID so desktop notifications keep working.

**Profile:** `Resolve at execution`

**Goal:** Claude Code sees exactly seven self-describing tools and no provider identity.

**Files:**
- Modify: `src/openmcp/server.py`
- Modify: `src/openmcp/models.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `src/openmcp/execution.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`, only the editable OpenMCP package version metadata from 1.2.0 to 2.0.0, approved in the Phase 4 approval question
- Modify: `README.md`
- Modify: `tests/test_server.py`
- Modify: `tests/test_runtime.py`
- Modify: `tests/test_execution.py`
- Modify: `tests/test_smoke.py`
- Delete: `src/openmcp/backend_runner.py`, only if no remaining import after `run()` is removed

**Tasks:**
1. Add `OpenMCPError(code, message, next_action, retryable)` and the design's
   error codes. Map existing `OrchestrationError` sites to codes. Convert
   unexpected exceptions in `_logged_request` to `internal_error` with the
   request ID, after logging.
2. Implement `project_resolve`, `task_guide`, `job_submit`, `job_wait`,
   `job_list`, `job_cancel`, and `job_retry` with the design's parameters,
   return shapes, titles, and annotations. Set `instructions` from the design
   and server title `OpenMCP job queue`. `job_wait` keeps the Phase 1
   heartbeat, adds `result_offset` paging up to 24,000 Unicode code points,
   shrunk to the complete serialized response budget, and returns
   `next_action` on timeout. `job_cancel` on a terminal job returns its summary.
   The approved `invalid_request` and `response_too_large` codes cover schema
   validation and unpageable metadata. Emit one compact JSON text content
   without structured duplication, under 30,000 characters and 9,000 UTF-8 bytes.
   Never silently truncate. An overflow after an applied mutation must name
   that outcome and retain the root ID rather than encouraging resubmission.
3. `Runtime.resolve_project`: canonical path match returns the stored project;
   otherwise create it. Default alias is the directory name; when that alias is
   taken, append `-2`, `-3`, and so on. An explicit alias that is taken raises
   `alias_taken`. A concurrent root insert re-reads the existing row.
4. Remove `project_register`, `status`, `run()`, all resource templates,
   `subscription_bus`, `publish_job_resource`, `SubmissionResult.resource_uri`,
   `JOB_RESOURCE_URI_TEMPLATE`, and `job_resource_uri`. Key the runtime notifier
   by job ID. Bump `pyproject.toml` to `2.0.0`. Rewrite the README MCP section.

**Acceptance Criteria:**
- `mcp.list_tools()` returns exactly the seven tools with the design's annotations.
- `mcp.list_resource_templates()` and `mcp.list_resources()` are empty.
- Instructions and every tool description are at most 2048 characters;
  instructions name every tool; no description contains `openmcp://`.
- An in-process client completes resolve, guide, submit, wait in 4 calls.
- A recursive scan of every tool output finds no `target_id`, `backend`,
  `model`, `resource_uri`, or `config_revision` key.
- Each error code arrives with `isError` and parseable JSON containing `next_action`.
- Paged offsets reassemble the full result; every response is under 30,000 characters.
- Desktop notification tests still pass.

**Reviewer Checklist:**
- No v1 name remains in `src/` or `README.md` outside `docs/plans/`.
- `job_wait` is read-only and never mutates job state.
- Internal errors carry no stack trace or provider detail.

**Verification Checks:**
- `uv run --extra dev pytest tests/test_server.py tests/test_runtime.py tests/test_execution.py tests/test_smoke.py tests/test_notifications.py -q`
- `uv run --extra dev pytest -q`

---

### Phase 5: Dashboard v2 vocabulary

**Task Guide Input:** Align the OpenMCP dashboard HTTP API in
`src/openmcp/dashboard.py` and the React client in `web/src` with the v2
vocabulary in `docs/plans/mcp-v2-claude-code/DESIGN.md`. Distinct use cases:
(a) job payloads gain dependency and access fields, and the project job list
uses the active and recent shape; (b) runtime settings expose
`max_project_readers`; (c) duplicate route aliases collapse to one canonical
route per resource after confirming each pair against `web/src` usage, with
the client updated; (d) rebuild the bundled dashboard assets. The dashboard
keeps target and provider detail.

**Profile:** `Resolve at execution`

**Goal:** The dashboard shows dependencies and reader capacity under one route name per resource.

**Files:**
- Modify: `src/openmcp/dashboard.py`
- Modify: `src/openmcp/models.py`
- Modify: `web/src/api.js`
- Modify: `web/src/screens/Jobs.jsx`
- Modify: `web/src/screens/JobDetail.jsx`
- Modify: `web/src/screens/ProjectDetail.jsx`
- Modify: `web/src/screens/Projects.jsx` and its matching test, approved in the Phase 4 approval question because it also consumes the changed job-list shape
- Modify: `web/src/screens/RuntimeSettings.jsx`
- Modify: `web/src/screens/Overview.jsx`
- Modify: `web/src/screens/ConfigHealth.jsx`
- Modify: `web/src/components/JobDetails.jsx`
- Modify: matching `*.test.jsx` and `web/src/api.test.js`
- Modify: `tests/test_dashboard.py`
- Modify: `src/openmcp/dashboard_static/**`, regenerated by the build

**Tasks:**
1. Add `access_mode`, `depends_on`, `waiting_on`, and `waiting_reason` to
   `DashboardJob` and render them in job detail and lists. Return project jobs
   as `active`, `recent`, and `more_recent`.
2. Show `max_project_readers` in runtime settings, with effective and pending
   values reported separately.
3. For each candidate pair in the design, keep the route `web/src` uses, delete
   the other, and update the client. Record each decision in the phase journal.
4. Run `npm --prefix web run build` and commit the regenerated assets.

**Acceptance Criteria:**
- Each removed route returns 404; each kept route passes its existing test.
- Job detail shows dependencies and waiting reason for a dependency-blocked job.
- Bundled assets match a fresh build.

**Reviewer Checklist:**
- No route is removed that `web/src` still calls.
- CSRF and loopback protections are unchanged.

**Verification Checks:**
- `uv run --extra dev pytest tests/test_dashboard.py -q`
- `npm --prefix web test`
- `npm --prefix web run build`
- `uv run --extra dev pytest -q`

---

### Phase 6: superpowers-ccg v12 contract

**Task Guide Input:** In the separate repository
`/home/ngosi/projects/superpowers-ccg`, update the coordinator skills to the
OpenMCP v2 tool contract in
`/home/ngosi/projects/openmcp/docs/plans/mcp-v2-claude-code/DESIGN.md`.
Distinct use cases: (a) rewrite the tool contract reference for seven tools and
no resources; (b) replace every v1 call, resource read, and 300-second wait
instruction in skill steps; (c) update contract tests and bump the plugin and
shared contract versions to 12.0.0. Documentation, Bash test, and JSON version
fields only.

**Profile:** `Resolve at execution`

**Goal:** The coordinator skills call only v2 tools.

**Files:**
- Modify: `skills/coordinating-multi-model-work/references/tool-contract.md`
- Modify: `skills/coordinating-multi-model-work/SKILL.md`
- Modify: `skills/coordinating-multi-model-work/references/handover.md`
- Modify: `skills/executing-plans/SKILL.md`
- Modify: `skills/executing-plans/implementer-prompt.md`
- Modify: `skills/writing-plans/SKILL.md`
- Modify: `tests/test-contracts.sh`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `.codex-plugin/plugin.json`
- Modify: `shared/erp.md`, `shared/journal-template.md`, `shared/notes-template.md`, `shared/worker-contract.md`

**Tasks:**
1. Rewrite `tool-contract.md` for the seven tools, error JSON, paging, and
   `depends_on`.
2. In `SKILL.md`: `status` and `openmcp://projects` plus registration become
   `project_resolve`; reconciliation reads `job_list`; profile and workflow
   validation reads `task_guide`; the waiting rule uses one `job_wait` without
   a 300-second timeout and repeats only on a non-terminal result. Apply the
   same changes in the other listed skill files.
3. Update `tests/test-contracts.sh` assertions and bump every `11.0.6` to `12.0.0`.

**Acceptance Criteria:**
- No file under `skills/` or `shared/` contains `project_register`, `openmcp://`,
  `resource_uri`, or `timeout_s: 300`.
- The provider-identity guard in `tests/test-contracts.sh` still passes.

**Reviewer Checklist:**
- Coordinator behavior is unchanged apart from the tool contract.
- No backend, model, or provider name is introduced.

**Verification Checks:**
- `bash tests/run.sh`

---

### Phase 7: Live cutover and acceptance

**Task Guide Input:** Coordinator-only phase. Restart the OpenMCP daemon on v2,
then verify every success criterion from Claude Code itself. No implementation job.

**Profile:** `n/a`

**Goal:** Claude Code runs the full v2 cycle against the live daemon.

**Files:**
- Modify: `docs/plans/mcp-v2-claude-code/.handover.md`
- Modify: `docs/plans/mcp-v2-claude-code/phase-07/journal.md`

**Tasks:**
1. With no active job, run `systemctl --user restart openmcp.service` and start
   a new Claude Code session so the v12 skills and v2 tools load.
2. Live checks: resolve, guide, submit, wait in 4 calls; a wait of at least
   6 minutes from the main conversation and from a subagent; a dependent pair
   where a failed parent cancels the child; one invalid call per error family
   shows full JSON with `next_action`; no response shows provider identity.

**Acceptance Criteria:**
- Each success criterion a to g has recorded live or test evidence in the journal.
- `systemctl --user is-active openmcp.service` prints `active`.

**Reviewer Checklist:**
- Evidence comes from the restarted daemon, not from tests alone.

**Verification Checks:**
- `systemctl --user is-active openmcp.service`
- `uv run --extra dev pytest -q`
- `npm --prefix web test`

## Open Items

- `docs/diagrams/openmcp_c4_model.drawio` and `.svg` name v1 tools. Out of
  scope; the user decides whether to redraw them.
- Whether the task-guide line "submit dependent jobs sequentially" ships in this
  repository. Phase 4 checks; update only if it does.
