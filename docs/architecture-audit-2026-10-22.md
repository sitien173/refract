# Refract Architecture Audit

Date: 2026-10-22

## Implementation status

Implemented changes have passed local regression checks on `main`.
The findings below preserve the original audit snapshot.

### Implemented

| Item | Working-tree implementation |
|---|---|
| QW1 | Streaming loops enforce cancellation and the shared deadline. |
| QW2 | Dashboard routes enforce loopback client and Host checks. Remote binding requires `--allow-remote`. |
| QW3 | Indexed, limited job listings avoid full-history materialization. |
| QW4 | Mutation errors retain actionable messages. Loader errors are sanitized once. |
| QW5 | Queries pause while hidden and resume on visibility. App owns the shared configuration query. |
| QW6 | Catalog reloads refresh executor configuration. |
| QW7 | The replacement commit protocol removes exchange rollback paths. |
| QW8 | Versions match `2.0.0`. CI checks dashboard builds and release prerequisites. |
| QW9 | Removed `max_attempts` from configuration, planning, APIs, and editors. |
| QW10 | Removed unused state, models, helpers, routes, extras, and frontend code. Compatibility source readers remain. |
| A1 | Startup, MCP, runner, streaming, and dashboard persistence run off-loop. Workers join through repeated cancellation before resources close. Startup warms executable capability probes. Committed submissions enqueue despite request cancellation. |
| A2 | Global and project catalogs reuse stat-keyed parses. Invalid edits remain retryable. |
| A3 | Scoped CRUD uses shared mutation and profile helpers. Query helpers, tolerant reference traversal, validation, publication, and rollback are consolidated. |
| A4 | Sibling file locks protect revision checks and atomic replacement. |
| A5 | Backend prompts use stdin instead of command arguments. |
| A6 | Periodic retention prunes streams and lifecycle history. Turns are capped per context and role. Browser streams retain at most 2,000 events with monotonic dedupe. |
| A7 | Backend execution shares subprocess handling and error mapping. |
| A8 | Execution uses one recovery loop. Target-ID capacity drains safely across updates. Cancellation awaits capacity without polling. |
| A9 | Application factories own independent runtime state and lifespans. Stream commits notify explicitly. Logging overrides do not mutate environment variables. |
| C1 | MCP argument guards derive from registered schemas. The tested SDK minor is pinned. SDK error-prefix behavior has regression coverage. |
| C2 | One dashboard mutation factory owns request handling. Tool completion logging uses one final block. |
| C3 | Lifecycle changes and events commit atomically. Shared session helpers and one stream metadata query remove duplicate paths. Stream writes accept dictionaries only. |
| C4 | `useConfigEditor` owns submit, revision, dirty/in-flight guards, conflict handling, and reload. `useProjectDetail` owns queries, state, effects, and controller handlers. Forms retain validation, payload construction, and distinct list operations. Confirmation dialogs, configuration queries, and polling intervals are shared. |
| C5 | Backend schemas derive workflows from the registry. Editors and fallback previews consume task-guide workflow identifiers. |
| C6 | Reusable CI publishes coverage for SonarQube without retesting. Release jobs reuse CI. Label events update AI review. Tool and consolidation rules have authoritative references. Endpoint defaults have contract checks. |
| O1 | Backend failures log diagnostics. Polling and stream hooks expose errors. |
| O2 | All editor close paths share dirty-draft and in-flight guards. Empty revisions block saves. Polling cannot replace an in-flight revision or conflict. Mutation dialogs reject dismissal during submission. |
| O3 | Removed agy auto-continuation and undocumented session-file access. |
| O4 | Inline target arrays work. tomlkit is pinned. Global-config project roots are rejected. Missing sources return `not_found`. |
| O5 | Scheduler admission tracks active projects. SSE closes after terminal commit and final cursor. The unused lifecycle-events route was removed under QW10. No replacement pagination API was added. |
| O6 | Removed crash-file wiring, fault-handler ownership, duplicate sink state, and manual fingerprint tuples. Stdlib rotating files use a private file-creation callback. Bounded queue/listener adapters retain drop telemetry and graceful shutdown. Redaction, exception reporting, warning restoration, and degraded-sink recovery remain. |
| O7 | Schema v15 is the minimum and current supported schema. Read-only compatibility checks reject unsupported databases before writable access. Only genuinely empty, unversioned databases bootstrap. Removed obsolete migrations, 316 tracked plan files, and five duplicate diagram PNGs. Kept `.drawio` sources, SVG exports, and build-required source/bundled logos. |

### Retained implementation boundaries

- A1: SQLite remains synchronous internally, with thread-local connections. Async callers offload persistence to workers. Scheduler and capacity state remain event-loop-owned.
- A3: Public scoped wrappers preserve response shapes and project fallback. Reference scans tolerate invalid declarations. Writes retain strict loader validation.

### Verification

- Latest Python regression: **581 passed, 3 deselected**.
- Worker regressions cover repeated cancellation and failing workers. Callers retain ownership until workers finish. The first cancellation remains authoritative.
- Frontend regression: **223 passed across 21 files**.
- Logging regressions cover private rotation, redacted exceptions, process fault-handler noninterference, degraded-sink recovery, and warning restoration.
- Database regressions cover unchanged rejection, stranded WAL preservation, empty bootstrap, current-schema history, and initialization cleanup.
- Submit regressions cover duplicate submission, close guards, failure retry, conflict recovery, and reload exclusion.
- Existing editor and project regressions preserve validation, payloads, dirty drafts, revision safety, and stale-route protection.
- LSP diagnostics retain existing effect-dependency, accessibility, and Python typing findings. The Python LSP resolves a different environment; regression tests use `server/.venv`.
- Plugin session-start tests, contract tests, and manifest validation passed.
- GitHub Actions configuration passed `actionlint`.
- Live backend tests, hosted CI, and cross-platform execution were not run locally.

### Delivery boundaries

- Delivery includes the implementation changes in one requested commit.
- No branch changes or archive commits.
- FlowForge branding remains unchanged, as requested.
- This status does not claim the entire audit is implemented.

## Original audit findings

I audited `server/src/refract`, which is about 12.7k lines of Python, plus the React dashboard, the plugin, and the CI workflows. No code was changed. Most items I checked by reading the code. Items marked **Agent-reported** were checked by a subagent and not re-checked by me. Items marked **Unverified** have not been confirmed by reading or running the code.

The biggest risks:
- Cancel and timeout are ignored while a backend CLI is streaming output.
- Dashboard read routes are open to DNS rebinding.
- An idle project tab causes disk writes and full job loads every 5 s.
- Config editor errors are reduced to "Invalid configuration".

---

## 1. Quick Wins: High Impact, Low Effort

### QW1. Cancel and timeout ignored while a CLI streams
- **Location:** `server/src/refract/backends/_shell.py:227-241`, `stream_shell_command_lines`
- **Category:** Redesign
- **The Problem:** `cancel_event` and the deadline are checked only inside `except queue.Empty`, which runs after 0.5 s with no output. Backends that stream steadily, such as `claude --include-partial-messages` or `codex --json`, never reach that branch. So `job_cancel` and `timeout_s` do nothing until the CLI goes quiet.
- **The Solution:** Check both at the top of every loop iteration.
  ```python
  while True:
      if cancel_event.is_set() or time.monotonic() >= deadline:
          terminate_process_tree(process); break
      try:
          line = lines.get(timeout=0.5)
      except queue.Empty:
          continue
  ```
- **Impact vs. Effort:** Impact High. Effort Low.

### QW2. Dashboard read API open to DNS rebinding
- **Location:** `dashboard.py:466-505` and `dashboard.py:1200-1417`. The only checks are `_authorized_editor_read` at `:408` and `_authorized_mutation` at `:443`. Also `cli.py:94-151` and `config.py:635-651`.
- **Category:** Redesign
- **The Problem:**
  - These routes have no loopback-client or Host check: status, overview, projects, project jobs, job detail, job output, SSE, settings, targets and task-guide.
  - The MCP SDK turns on DNS-rebinding protection for `/mcp` on loopback hosts, at `.venv/.../mcp/server/mcpserver/server.py:1101`. The dashboard routes are separate Starlette routes and don't get it.
  - A page that rebinds its domain to 127.0.0.1 can list projects and then read every job prompt and output.
  - `--host` and `[daemon].host` accept any value, so `0.0.0.0` exposes all of this to the LAN.
- **The Solution:** Add one guard on `/dashboard/*` that requires `_is_loopback_client` and `_is_loopback_host`. Reject non-loopback hosts unless an explicit opt-in flag is set.
- **Impact vs. Effort:** Impact High. Effort Low.

### QW3. Job listings load every job to return ten
- **Location:** `dashboard.py:1274-1292` `project_jobs`, `server.py:783` `job_list`, `database.py:785` `jobs()`
- **Category:** Optimize
- **The Problem:**
  - `jobs()` runs `SELECT *` over all jobs in a project, including full prompt and result text.
  - `project_jobs` then calls `_dashboard_job` for each job, which queries `job()` and `job_record()` again and parses the plan. That is 2N+1 queries.
  - Only the active jobs plus 10 terminal jobs are returned. The dashboard polls this every 5 s.
  - No index covers `project_id`. The only jobs index is `jobs_state_idx` at `database.py:352`.
  - The dashboard takes terminal jobs in `created_at` order, while MCP `job_list` sorts by `updated_at`. The two "recent" lists can differ.
- **The Solution:** Use limited SQL and load full rows only for jobs that are returned.
  ```sql
  CREATE INDEX jobs_project_idx ON jobs(project_id, updated_at);
  SELECT <cols> FROM jobs WHERE project_id=? AND state NOT IN (<terminal>);
  SELECT <cols> FROM jobs WHERE project_id=? AND state IN (<terminal>) ORDER BY updated_at DESC LIMIT 10;
  SELECT COUNT(*) FROM jobs WHERE project_id=? AND state IN (<terminal>);
  ```
- **Impact vs. Effort:** Impact High. Effort Low.

### QW4. Every config editor error becomes "Invalid configuration"
- **Location:**
  - `dashboard.py:421-441` `_handle_mutation_error`
  - `config_inspection.py` `sanitize_config_error`
  - Sanitized twice via `config.py:573,584,680` and `config_inspection.py:185`
- **Category:** Redesign
- **The Problem:** I ran the sanitizer directly.
  - `"Target 'prod' already exists."` and `"Unknown target: prod"` both come back as `"Invalid configuration"`.
  - Loader messages reach the same string after the second pass.
  - Users can't see why a save failed.
- **The Solution:** Pass `ConfigurationMutationError` messages through unchanged, since the service writes them itself. Sanitize loader messages once, only in `ConfigurationLoadError.__init__`.
- **Impact vs. Effort:** Impact High. Effort Low.

### QW5. Hidden tabs keep polling heavy endpoints
- **Location:** `web/src/hooks/useDashboardQuery.js:58-63`, `screens/ProjectDetail.jsx:43-64,166`, `config_mutation.py:1007-1066`
- **Category:** Optimize
- **The Problem:**
  - `useDashboardQuery` re-arms a 5 s timer without checking `document.hidden`. `usePolling.js` does check it.
  - `ProjectDetail` runs five separate 5 s pollers. Five screens each poll `/dashboard/api/configuration` on their own timer.
  - The profile-overrides poll reaches `resolve_project_catalog`. On every GET that creates a temp directory, writes and fsyncs a copy of the config, and parses the TOML again.
  - Result: one idle project tab causes, every 5 s and indefinitely, a temp-file write with fsync, a full load of every job, and repeated config reloads.
- **The Solution:**
  - Add the `usePolling` visibility guard to `useDashboardQuery`, and refetch on `visibilitychange`.
  - Run one shared configuration query at App level.
  - Remove the temp-file reads using item A3.
- **Impact vs. Effort:** Impact High. Effort Low.

### QW6. Manual config edits split planning from execution
- **Location:** `runtime.py:599-625` `_reload_catalog_locked`, called from `:323`, `:547` and `:597`. `execution.py:43` `refresh_configuration` is called only at `runtime.py:517`.
- **Category:** Redesign
- **The Problem:** Job submits and catalog lookups reload the config and replace `self._catalog`. The executor keeps its old `DaemonConfig`. After a manual edit of breaker or history settings, planning uses the new values and execution uses the old ones until a dashboard save publishes the change.
- **The Solution:** Call `self.target_executor.refresh_configuration(catalog)` inside `_reload_catalog_locked` after a successful load.
- **Impact vs. Effort:** Impact Medium. Effort Low.

### QW7. Commit rollback can delete a concurrent external edit
- **Location:** `config_mutation.py:509-540` `commit_bytes`. Agent-reported: the same pattern at `:2476-2518`.
- **Category:** Redesign
- **The Problem:** When `_restore_exchanged_state` returns False, the code raises "state is uncertain" while `retain_temporary` is still False. The `except` at `:535` then deletes `temporary`, which at that point holds the external edit that was swapped out. Triggering it needs two writers inside one short window.
- **The Solution:** Set `retain_temporary = True` before that raise. In the rollback `except OSError`, set `retain_delete_target = True` and re-raise. Item A4 removes this code path entirely.
- **Impact vs. Effort:** Impact Medium. Effort Low.

### QW8. Version drift and an unchecked build output
- **Location:**
  - `1.0.0` appears at `README.md:1`, `server/CLI_ARGUMENTS.md:3`, `server/web/package.json:4`, `sonar-project.properties:3` and `server.py:476` `MCPServer(version="1.0.0")`.
  - `2.0.0` appears at `pyproject.toml:7` and in the plugin manifests.
  - CI: `.github/workflows/server.yml:36-49` and `release.yml:17-29`.
- **Category:** Consolidate
- **The Problem:**
  - MCP clients see version 1.0.0 from a 2.0.0 build.
  - CI never runs `npm run build`, so the committed `dashboard_static/` can drift from `web/src`.
  - The release job runs only pytest. It skips the web tests, the plugin tests and a tag-versus-version check.
- **The Solution:**
  - In `server.py`, use `importlib.metadata.version("refract")`.
  - Assert all version strings in `plugin/tests/test-contracts.sh`.
  - Add `npm run build && git diff --exit-code -- ../src/refract/dashboard_static`.
  - Make the release job depend on the test jobs and compare `$GITHUB_REF_NAME` with `pyproject.toml`.
- **Impact vs. Effort:** Impact Medium. Effort Low.

### QW9. `max_attempts` can be set but is never used
- **Location:** It is parsed, stored and edited at `config.py:208-242`, `planning.py:43-56`, `models.py:239-245`, `dashboard.py:131` and `config_mutation.py:848-868`. Execution hardcodes `"attempt": 1`.
- **Category:** Remove
- **The Problem:** Users can set `max_attempts` in TOML and in the dashboard editor, and nothing reads it.
- **The Solution:** Remove the field everywhere, or implement it in `TargetExecutor`. Removing it is the smaller change.
- **Impact vs. Effort:** Impact Medium. Effort Low.

### QW10. Dead code and unused dependency extras
- **Location:**
  - **scheduler.py:**
    - These attributes are written but never read: `_queues` `:38`, `_scheduled_projects` `:40`, `_active_projects` `:41` and `_cancel_events` `:43`.
    - `_completion_events` `:42` is used only by tests.
    - `signal()` `:154` and the `start(queued=)` parameter are unused.
  - **runtime.py:**
    - `register_project` `:278`, `reload_configuration` `:493` and `publish_project_configuration` `:561` are used only by tests.
    - `_reload_catalog` `:590` is unused.
    - `configuration_health()` `:523` duplicates `config_health`.
  - **database.py and models.py:**
    - `database.py:684` `set_job_state` is unused.
    - `utc_now` exists in both `database.py:27` and `config_inspection.py:15`.
    - `models.py`: `ConfigRevision` `:29`, `TaskGuideResult` `:159` and `ResourcePayload` `:367` are never referenced.
  - **server.py:**
    - `:28` imports `ActionResult`, `ProjectView` and `SubmissionResult` without using them.
    - `_tool_error` `:449` is a trivial wrapper.
    - `_summary` has an unused `runtime` parameter.
    - In `job_cancel`, `result` is never used.
  - **dashboard.py:**
    - These alias routes are never called by `web/src/api.js`: `:1463` `/config/health`, `:1484-1485`, `:1487` and `:1490` `/jobs/{id}/events`.
    - `:299` returns an empty `"effective": {}`.
    - `:345` keeps a legacy fallback to `task_routes.json`.
  - **config modules, Agent-reported:**
    - `config_inspection.py:25` `hash_config_bytes`.
    - `config_mutation.py`: `_FileMode.value` `:126`, `load_source` `:149`, `source_read` `:962`, `remove_target_key` `:1095`, `set_target_argument` `:1102` and `workflow_targets` `:1507`.
    - The parameter `validate_registered_projects` `:2241` is never read.
  - **Frontend, Agent-reported:**
    - `api.js:48` `clearCsrfToken` has no importer.
    - `api.js:110` sets the CSRF header a second time.
    - `ProfileEditor.jsx:29` `isDirty` is never read.
    - The `'reloading'` status at `ProfileEditor.jsx:319-322` and `TargetEditor.jsx:165-169` is overwritten immediately.
  - **Dependencies:** `pyproject.toml:16` uses `mcp[cli]`, which installs `typer` and `python-dotenv`. Nothing in `src` imports them.
- **Category:** Remove
- **The Problem:** State that is written but never read makes the scheduler and runtime look as if they have features they don't have. Reviewers have to reason about values that never affect any decision.
- **The Solution:** Delete them. Move test-only helpers into the tests. Change the dependency to `mcp>=2,<3`.
- **Impact vs. Effort:** Impact Medium. Effort Low.

---

## 2. Critical Architectural Flaws

### A1. Blocking I/O on the single event loop
- **Location:**
  - The single `sqlite3` connection in `database.py` is called directly from async handlers in `server.py` and `dashboard.py`.
  - The config mutation handlers at `dashboard.py:604,673,711` do fsync-heavy work inline.
  - `drivers.py:197-215` `supports_structured_streaming` runs `<cli> --help` synchronously, with a 5 s timeout, the first time each binary is used.
- **Category:** Redesign
- **The Problem:**
  - One thread serves MCP, the dashboard, SSE and scheduling. Every query, TOML parse, fsync and `--help` probe stalls all of them.
  - Each state change uses two transactions: an update, then a separate `event()` insert, as in `finish_job` `:702-713`. WAL runs without `synchronous=NORMAL`.
  - Agent-reported: `config_mutation.py:1188-1198`, `:1657-1667` and `:2367-2378` work around `sqlite3.ProgrammingError` by opening raw connections. The root cause is Unverified.
- **The Solution:**
  - Move DB and config work behind `asyncio.to_thread` with one connection per worker thread, or use a single writer thread fed by a queue.
  - Merge each update and its event insert into one transaction, and set `PRAGMA synchronous=NORMAL`.
  - Run the `--help` probes once at startup, in a thread.
- **Impact vs. Effort:** Impact High. Effort Medium.

### A2. Config re-read from disk on hot paths
- **Location:** `runtime.py:322-323` for submit, `:546-557` for catalog lookups and `:367-395` `live_result_metadata`, which `server.py:772` calls on every terminal `job_wait` page.
- **Category:** Optimize
- **The Problem:** Each call reads, hashes and parses the TOML and rebuilds `DaemonConfig`. `live_result_metadata` also resolves a plan and runs one target-health query per target. Paging through one large result repeats all of this on every page.
- **The Solution:** Cache `DaemonConfig` by `(path, st_mtime_ns, st_size)` and parse again only when that key changes. `config_revision` already exists for the editor's ETag checks.
- **Impact vs. Effort:** Impact High. Effort Medium.

### A3. `config_mutation.py` is 2,582 lines wrapped around a loader
- **Location:** The whole module. The service class runs from `:931` to `:2569`. Agent-reported details:
  - Five near-duplicate global and project method pairs: `read_profiles` `:1557` and `read_project_overrides` `:1879`, `get_*` at `:1576` and `:1923`, `create_*` at `:1703` and `:1968`, `update_*` at `:1761` and `:2057`, `delete_*` at `:1823` and `:2131`.
  - The `expected_revision is None` block is repeated 10 times.
  - `restore_bytes` `:608-717` duplicates `commit_bytes` `:434-556`.
  - The reference scanners at `:1152-1243` and `:1609-1701` swallow errors and apply different self-reference rules.
- **Category:** Redesign
- **The Problem:**
  - Every rule change has to be made twice.
  - The pre-checks repeat rules the loader already enforces.
  - Validation goes through temp files because `config.py` can only parse from disk.
  - Bugs QW4 and QW7 live in this layer.
- **The Solution:** Add `load_config_bytes(data, path)` to `config.py` and route every edit through one helper.
  ```python
  def _mutate(self, scope, expected_revision, edit):
      original = read_config_source(scope.path)
      require_revision(original, expected_revision)
      doc = tomlkit.parse(original.data)
      result = edit(doc)
      candidate = tomlkit.dumps(doc).encode()
      catalog = scope.load_bytes(candidate)      # in memory, no temp file
      commit_bytes(scope.path, candidate, expected_revision)
      self.runtime.publish(scope, catalog)
      return result
  ```
  Each CRUD method becomes an `edit` callback. The scanners become a query over the validated catalog. Inference: this removes well over half the module. The exact reduction is Unverified.
- **Impact vs. Effort:** Impact High. Effort High.

### A4. Config writes fail outside Linux
- **Location:** `config_mutation.py:263-298` `_load_renameat2` and `_atomic_exchange`. `pyproject.toml:12` claims "OS Independent". `processes.py:77-120` contains Windows code paths.
- **Category:** Redesign
- **The Problem:** Outside Linux, `_renameat2` is None, so every dashboard save returns `configuration_commit_failed`. Concurrent writers are guarded only by an in-process `RLock` and a SHA-256 check, so there is no protection across processes.
- **The Solution:** Write the temp file, fsync it, then `os.replace`. Hold `fcntl.flock`, or `msvcrt.locking` on Windows, on a sibling lock file across the check and the replace. This also removes the exchange and compensation logic, along with the QW7 bugs.
- **Impact vs. Effort:** Impact High. Effort Medium.

### A5. Prompt passed as a single argv element
- **Location:** `backends/pi.py:160`, `agy.py:190`, `codex.py:230`, `claude.py:145`. The history budget is `config.py:82` `history_bytes = 65536`.
- **Category:** Redesign
- **The Problem:** Linux caps a single argument at 128 KiB, and Windows caps the whole command line near 32K characters. A prompt plus replayed history can exceed these limits, and the launch then fails with an OS error. The prompt is also visible to other local users through `ps`.
- **The Solution:** Send the prompt on stdin. Whether each of the four CLIs accepts a prompt on stdin is Unverified, so confirm per CLI before switching.
- **Impact vs. Effort:** Impact High. Effort Medium.

### A6. Unbounded data growth
- **Location:**
  - In `database.py`, the `events` and `context_turns` tables are never pruned.
  - `job_stream_events` is pruned only at startup, at `runtime.py:149-161`.
  - `web/src/hooks/useJobStream.js:207-211`.
- **Category:** Redesign
- **The Problem:** The database grows for as long as the daemon runs, and every unbounded query gets slower. In the browser, each output page rebuilds a `Set` over all previous events. That is O(n²) work in total, and the array has no cap.
- **The Solution:**
  - Run a periodic retention task in the runtime.
  - Cap `context_turns` per context key at `history_turns`.
  - In the frontend, cursors are monotonic, so the dedupe can be `e.id > lastId` with a capped window. Rendering is already virtualized with `@tanstack/react-virtual`.
- **Impact vs. Effort:** Impact High. Effort Medium.

### A7. Four copies of the backend pipeline
- **Location:**
  - `drivers.py:244-321` `DriverRegistry.execute` has four identical branches.
  - Each backend defines an identical `*Params` dataclass and a `run_shell_command` wrapper: `agy.py:48`, `codex.py:36`, `pi.py:35`, `claude.py:35`.
  - The same exception mapping appears at `pi.py:251-266`, `claude.py:217-232`, `codex.py:326-340` and `agy.py:360-374`.
- **Category:** Consolidate
- **The Problem:** Any fix to process handling, such as QW1, has to be checked four times. Each backend keeps all stdout in memory and parses each JSON line up to three times.
- **The Solution:** Define one `BackendSpec` per backend with `build_argv`, `parse_line`, `extract_result` and `classify_error`. One shared runner owns the subprocess, the deadline, cancellation and error mapping, and parses each line once.
- **Impact vs. Effort:** Impact Medium. Effort Medium.

### A8. `TargetExecutor.execute` is a 300-line function
- **Location:**
  - `execution.py:52-348`. The recovery phases at `:116-261` repeat the same block three times.
  - `_acquire_target` `:466-476` polls a semaphore every 0.1 s.
  - `_target_semaphores` `:71` is keyed by a hash that includes `max_concurrency`, so entries pile up with each config change.
  - `JobRunner.run` raises `RuntimeError` for control flow at `:662-664`.
  - `hasattr(...)` at `:88-92` exists only to accommodate tests.
- **Category:** Redesign
- **The Problem:** Fixing a phase means editing all three copies. The semaphore polling burns CPU and adds latency.
- **The Solution:**
  ```python
  for phase in (Phase.INITIAL, Phase.RECONSTRUCT, Phase.FRESH):
      outcome = await self._run_phase(phase, ctx)
      if not outcome.advance:
          return outcome.result
  ```
  Await `semaphore.acquire()` against the cancel event instead of polling. Key semaphores by target id and rebuild them on publish.
- **Impact vs. Effort:** Impact Medium. Effort Medium.

### A9. Module-level globals wire the server together
- **Location:**
  - `server.py:34-35` and `:61` hold globals. `cli.py:94-105` writes CLI flags into `os.environ`, and `cli.py` also sets `server._DAEMON_CONFIG`.
  - `runtime.py:68-76` monkeypatches `database.append_stream_events`, while the `StreamRecorder` `on_commit` hook at `streaming.py:65,292-303` sits unused.
  - The runtime reaches into `database._connection` at `:228,348` and into `target_executor._is_open` at `:388,445`.
- **Category:** Redesign
- **The Problem:** These create hidden ordering rules and allow only one app per process. Tests have to reset globals. The stream publish path is hidden behind a monkeypatch.
- **The Solution:**
  - `create_application(config)` builds the Runtime and `DashboardState` and puts them on `app.state`.
  - Pass logging overrides as arguments rather than through `os.environ`.
  - Use `StreamRecorder(on_commit=stream_hub.publish)` and delete the monkeypatch.
- **Impact vs. Effort:** Impact Medium. Effort Medium.

---

## 3. Consolidation

### C1. MCP arguments validated three times, and SDK errors parsed by string prefix
- **Location:**
  - The hand-written tool schema in `server.py:290-320` `_raw_argument_error`.
  - Repeated checks at `:723-726`, alongside pydantic `Field(ge=, le=)`.
  - Prefix parsing of "Error executing tool ..." at `:238-254` and `:375-394`.
- **Category:** Consolidate
- **The Problem:** Adding a tool parameter without updating `_raw_argument_error` makes every call fail with `invalid_request`. The prefix parsing breaks silently if the SDK changes its wording, and `pyproject` allows `mcp>=2,<3`.
- **The Solution:** Build the allowed-argument map from the registered tool input schemas at startup. Drop the repeated `isinstance` checks. Pin `mcp` to a tested minor version and add a test that asserts the SDK prefix.
- **Impact vs. Effort:** Impact Medium. Effort Low.

### C2. Nine copies of the dashboard mutation handler
- **Location:** `dashboard.py:553-1190`
- **Category:** Consolidate
- **The Problem:** Each of the nine handlers repeats about 60 lines: auth, runtime lookup, If-Match, JSON parse, model validation, the call, ETag headers and error mapping. `_logged_request` at `server.py:519-594` similarly repeats one log block five times.
- **The Solution:** A `mutation_route(model, call)` factory that runs the call in `to_thread`. Log once from `finally`, with the outcome set in each `except`.
- **Impact vs. Effort:** Impact Medium. Effort Low.

### C3. Duplicated database write and read paths
- **Location:**
  - `database.py:715-760` `finish_fresh_job_success` repeats the SQL from `append_turn` `:806-821` and from `finish_job`.
  - `append_stream_events` accepts two input shapes, and `StreamRecorder.record` accepts three.
  - Each `job_output` call makes four metadata queries at `dashboard.py:1338-1345` and loads every lifecycle event.
- **Category:** Consolidate
- **The Problem:** The duplicated SQL has to be kept in sync by hand. Every output poll runs extra queries and loads events it doesn't need.
- **The Solution:**
  - Add `_upsert_session` and `_finish` helpers and compose them inside one transaction.
  - Accept one input type.
  - Add one `stream_metadata(job_id)` query that returns high-water, retained-from, truncated and failed, using `EXISTS`.
- **Impact vs. Effort:** Impact Medium. Effort Low.

### C4. Frontend editor duplication
- **Location:** Agent-reported.
  - `ProfileEditor.jsx`, 702 lines, and `TargetEditor.jsx`, 550 lines, share error extraction at `:333-344` and `:178-189`, the reload handler at `:352-413` and `:197-264`, and the list handlers at `:131-228` and `:94-134`.
  - The confirm dialog is implemented twice: `ProjectDetail.jsx:1130-1288` and `ConfigurationMutationDialog.jsx`.
  - The literal `5000` appears in six places.
  - `ProjectDetail.jsx` is 1,291 lines.
- **Category:** Consolidate
- **The Problem:** Fixes to save, reload or conflict handling have to be made in both editors. The two copies already behave differently.
- **The Solution:**
  - A `useConfigEditor({load, save, toPayload})` hook that owns revision, dirty state, submit, conflict and reload.
  - One confirm dialog and a `POLL_INTERVAL_MS` constant.
  - Extract a `useProjectDetail` hook.
- **Impact vs. Effort:** Impact Medium. Effort Medium.

### C5. Workflow list defined three times
- **Location:**
  - `workflows.py:5` `BUILTIN_WORKFLOWS`.
  - `server.py:677` `Literal["consult","implement","review","other"]`.
  - `ProjectDetail.jsx:1227`, Agent-reported.
  - `workflows.py:16` `validate_request` ignores its `workflow` argument.
- **Category:** Consolidate
- **The Problem:** Adding or renaming a workflow means editing three places in two languages.
- **The Solution:** Derive the `Literal` from `BUILTIN_WORKFLOWS`. Have the UI read the list from the task-guide API.
- **Impact vs. Effort:** Impact Low. Effort Low.

### C6. CI and plugin documentation duplication
- **Location:** Agent-reported.
  - pytest runs in `server.yml:32-34`, `sonarqube.yml:33-34` and `release.yml`.
  - `sonarqube.yml` has no paths filter.
  - `ai-pr-review.yml:4-5` ignores `labeled` events.
  - Port 8765 is hard-coded in five places.
  - `plugin/.../SKILL.md` repeats rules from `tool-contract.md`.
  - The final-consolidation steps appear in five files with different step counts.
  - `SKILL.md:80` still says "dependent jobs", although dependencies were removed in 2.0.0.
- **Category:** Consolidate
- **The Problem:** The duplicated skill text is loaded into agent context every session. The conflicting step counts give agents contradictory instructions.
- **The Solution:** Use a reusable workflow with a single test job that produces coverage. Make the reference file own the rules and have the skills link to it.
- **Impact vs. Effort:** Impact Low. Effort Low.

---

## 4. Optimize and Harden

### O1. Silent failure points
- **Location:**
  - `server.py:755` `except Exception: pass`.
  - `drivers.py:38-48` `StreamBridge.emit` swallows all exceptions.
  - `config_mutation.py:279-280` `except Exception: pass`.
  - Agent-reported: the scanner swallows at `config_mutation.py:1165`, `:1222`, `:1622` and `:1699`, and empty `catch` blocks in `usePolling.js:17` and `useJobStream.js:348`.
- **Category:** Optimize
- **The Problem:** These failures leave no trace. The dashboard keeps showing stale data with no error state.
- **The Solution:** Log at warning level with `exc_info`. Expose a last-error value from the hooks.
- **Impact vs. Effort:** Impact Medium. Effort Low.

### O2. Editor data-safety bugs
- **Location:** Agent-reported and spot-checked. `ProfileEditor.jsx:424`, `TargetEditor.jsx:272-280`, `:532`, `ProfileEditor.jsx:680` and `Profiles.jsx:131`.
- **Category:** Redesign
- **The Problem:**
  - Escape, scrim click and the X button close the dialog during a save. A late 409 is then lost, because the close effect clears the error and conflict state.
  - Cancel skips the dirty-draft confirmation.
  - The create path sends `If-Match: ""`. Whether this always returns 409 is Unverified.
- **The Solution:** One guarded close handler, an in-flight ref, and a submit that is blocked while the revision is empty.
- **Impact vs. Effort:** Impact Medium. Effort Low.

### O3. Agy auto-continuation
- **Location:** `backends/agy.py:442-497`. It reads `~/.gemini/antigravity-cli/brain` at `:27-29` and `:68-108`. Test-only code is at `:111-123` and `:445-454`.
- **Category:** Redesign
- **The Problem:** It depends on another tool's undocumented file layout. Each continuation gets a fresh `timeout_s`, so total time can reach 4x the configured timeout.
- **The Solution:** Share one deadline across continuations. Put continuation behind a target option, or remove it.
- **Impact vs. Effort:** Impact Medium. Effort Low.

### O4. Config edge cases
- **Location:** Agent-reported. `config_mutation.py:1289-1312`, `:725-737`, `:176-184` and `:462-468`.
- **Category:** Redesign
- **The Problem:**
  - `create_target` writes invalid TOML when `targets` is an inline array. The agent reproduced this with tomlkit 0.15.0.
  - The code uses private tomlkit attributes, while `pyproject` allows `tomlkit>=0.12.0`.
  - Registering `$HOME` as a project would load the global config as a project file and block every global write. This is Unverified at runtime.
  - A missing global config file returns 409 from one path and 404 from another.
- **The Solution:**
  - Append an inline table when `targets` is an inline array.
  - Pin tomlkit to a tested range.
  - Reject project roots whose `.refract/config.toml` is the global config.
  - Use one absence check that returns 404.
- **Impact vs. Effort:** Impact Medium. Effort Low.

### O5. Scheduler, SSE and event endpoints
- **Location:** `scheduler.py:159-186`, `dashboard.py:1369-1416` and `dashboard.py:1306`.
- **Category:** Optimize
- **The Problem:**
  - `_schedule` does `any(...)` over `_active` for each pending job, plus `deque.remove`. That is O(pending × active).
  - The SSE stream never ends when the job finishes.
  - `job_events` is unpaged.
- **The Solution:** Keep a dict of active-job counts per project. Close the SSE stream after the terminal state and final cursor. Page `job_events` the way `job_output` is paged.
- **Impact vs. Effort:** Impact Low. Effort Low.

### O6. Logging subsystem size
- **Location:** `logging_setup.py`, 601 lines. Settings come from three channels: environment variables, `cli.py:94-105` rewriting `os.environ`, and `[logging]` in TOML.
- **Category:** Redesign
- **The Problem:** It implements a bounded queue with drop notices, a custom listener, a secure rotating handler and faulthandler wiring, for a local single-user daemon.
- **The Solution:** Inference: stdlib `QueueHandler`, `QueueListener` and `RotatingFileHandler` plus a redaction filter would likely cover the need. Which current features are actually required is Unverified.
- **Impact vs. Effort:** Impact Low. Effort Medium.

### O7. Migration chain and repo weight
- **Location:** `database.py:48-605`. `docs/plans` holds 316 tracked files, 2.7 MB. `docs/diagrams` is 2.4 MB.
- **Category:** Remove
- **The Problem:**
  - Migrations v0 through v14 take about 450 lines, including full table rebuilds.
  - `docs/plans` is not referenced by code or CI.
  - Diagrams are committed in three formats, and the 764 KB logo is committed twice.
- **The Solution:**
  - Set a minimum supported schema version and fail with an upgrade message below it.
  - Move `docs/plans` to an archive branch.
  - Keep the `.drawio` sources plus one export format.
- **Impact vs. Effort:** Impact Low. Effort Low.

---

## Open questions
1. Is non-Linux supported for config editing? If yes, A4 is a bug, not a cleanup.
2. Do all four backend CLIs accept a prompt on stdin? A5 depends on the answer.
3. Is agy auto-continuation a required feature, or a workaround for one CLI version?
4. Is the "FlowForge" name in `Topbar.jsx:10` and `colors_and_type.css:2` intentional branding?

**Suggested order:** QW1 to QW4 first, since they are security, correctness and data-loss fixes that each take a few lines. Then A3 and A4 together, because the new write path removes the code where QW4 and QW7 live.
