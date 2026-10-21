# Client-Routed Failover, Result Metadata, and 3-State Circuit Breaker Plan

**Design:** `docs/plans/job-failover-metadata/DESIGN.md`
**Base:** `refs/plans/job-failover-metadata/base` (`bc5f3c4`)
**Commit:** `feat(server): client-routed failover, job result metadata, and 3-state circuit breaker`

Baseline at `base`:

- `cd /home/ngosi/projects/refract/server && uv run pytest -q`: 546 passed, 3 deselected.
- `cd /home/ngosi/projects/refract/server/web && npx vitest run`: fails. Across three runs, `src/screens/ProjectDetail.test.jsx > ProjectDetail screen > opens profile editor to create a project override and submits payload with project revision` failed every run; the first run also failed 2 more tests. Phase 1 repairs this baseline.

Out of scope for every phase: Git operations, secrets, `~/.refract` user config files, and any file under `docs/plans/` other than the current phase's `notes.md` and `journal.md`.

### Phase 1: Green baseline and backend usage capture

**Task Guide Input:** Repair one flaky web test at its root cause, capture real structured output from four installed CLIs as redacted test fixtures, and parse token usage and model data from each backend's stream into the backend and driver results. Use case: non-UI repository implementation with one web test fix.
**Goal:** Both suites pass, and every backend returns a `usage` dict parsed from real captured output.
**Files:**
- Modify: `server/web/src/screens/ProjectDetail.test.jsx`, or the component under test if the root cause is in product code
- Create: `server/tests/fixtures/usage/claude.jsonl`
- Create: `server/tests/fixtures/usage/codex.jsonl`
- Create: `server/tests/fixtures/usage/pi.jsonl`
- Create: `server/tests/fixtures/usage/agy.jsonl`
- Modify: `server/src/refract/backends/__init__.py`
- Modify: `server/src/refract/backends/claude.py`
- Modify: `server/src/refract/backends/codex.py`
- Modify: `server/src/refract/backends/pi.py`
- Modify: `server/src/refract/backends/agy.py`
- Modify: `server/src/refract/drivers.py`
- Modify: `server/tests/test_streaming_backends.py`
**Tasks:**
1. Find the root cause of the flaky `ProjectDetail.test.jsx` test and fix it, applying systematic debugging. Record the cause in `notes.md`.
2. Run each of `claude`, `codex`, `pi`, and `agy` once with a trivial prompt, such as `Reply with OK`, using the same structured-output flags the backend module passes today. Save the output as JSONL fixtures. Redact session IDs, account identifiers, paths under `$HOME`, and any token or key-like values. Record each command in `notes.md`.
3. Add `usage: dict[str, int | str | None]` with default empty to `BackendResult` and `DriverResult`, and pass it through `drivers._normalize`. Keys: `model_name`, `input_tokens`, `output_tokens`, `cached_input_tokens`, `context_window_max`, `context_window_used`.
4. In each backend, parse those keys from the event fields that actually appear in its fixture. A key absent from the fixture stays `None`. Record the field path, or absence, per backend and key in `notes.md`.
**Acceptance Criteria:**
- `npx vitest run` passes three consecutive runs.
- Four fixture files exist and contain no unredacted session ID, `$HOME` path, or credential.
- Each backend test parses its fixture into the expected `usage` values; a fixture with usage keys removed yields `None` for those keys without raising.
- `DriverResult.usage` carries the parsed dict for all four backends.
- `notes.md` holds a backend by key table of verified field paths.
**Reviewer Checklist:**
- The flaky test fix addresses a root cause, not a longer timeout or a retry.
- Fixtures are real captured output, not hand-written; redaction is complete.
- No parser reads a field name absent from its fixture.
- Missing or malformed usage never changes `outcome` or `error_class`.
**Verification Checks:**
- `cd /home/ngosi/projects/refract/server/web && npx vitest run && npx vitest run && npx vitest run`
- `cd /home/ngosi/projects/refract/server && uv run pytest -q tests/test_streaming_backends.py`
- `cd /home/ngosi/projects/refract/server && uv run pytest -q`

### Phase 2: 3-state circuit breaker, config keys, and schema v13

**Task Guide Input:** Add three `[daemon]` breaker config keys, deprecate `max_attempts`, add a v12 to v13 SQLite migration, and implement the closed/open/half-open breaker with an atomic single-probe claim. Use case: non-UI repository implementation covering database, config, and server tests.
**Goal:** The breaker follows the DESIGN.md counting table, with exactly one probe at a time and correct behavior across restart.
**Files:**
- Modify: `server/src/refract/config.py`
- Modify: `server/src/refract/planning.py`
- Modify: `server/src/refract/database.py`
- Modify: `server/src/refract/execution.py`, limited to `_select_target`, `_record_failure`, `_is_open`, and breaker calls
- Modify: `server/src/refract/runtime.py`, limited to `start()` recovery
- Modify: `server/tests/test_config.py`
- Modify: `server/tests/test_database.py`
- Modify: `server/tests/test_execution.py`
**Tasks:**
1. In `config.py`, add `DaemonConfig.breaker_failure_threshold = 3`, `breaker_base_cooldown_s = 60`, and `breaker_max_cooldown_s = 900`. Parse them from `[daemon]` with `_positive_int` and require `max >= base`. Keep parsing `max_attempts`, but log one `config.deprecated_key` warning per profile workflow that sets it.
2. In `database.py`, add `_migrate_v12_to_v13` with the three `ALTER TABLE` statements from DESIGN.md Migration. Add methods for: atomic probe claim, returning a bool from `rowcount == 1`; probe release; failure with threshold and exponential reopen; immediate open; success close resetting `cooldown_s`; and a startup reset of orphaned probes.
3. In `execution.py`, rewrite `_record_failure` and `_select_target` to use the derived 3-state rules and the counting table: `RETRYABLE` counts, `TARGET_FATAL` opens at once, and the other outcomes are not counted and release the probe. Thresholds come from `self.config`.
4. In `runtime.start()`, call the orphaned-probe reset before the scheduler starts.
**Acceptance Criteria:**
- The threshold opens the breaker; `TARGET_FATAL` opens it on the first failure; success closes it and resets `cooldown_s`.
- 20 concurrent claim calls on one half-open target yield exactly one `True`.
- A failed probe doubles `cooldown_s`, capped at `breaker_max_cooldown_s`.
- `context_overflow`, `CANCELLED`, and `REQUEST_FATAL` leave `consecutive_failures` unchanged and release a held probe.
- After restart, an orphaned probe target is half-open.
- A v12 database migrates to v13 with existing rows intact.
- A config with `max_attempts` loads and logs `config.deprecated_key`; `breaker_max_cooldown_s < breaker_base_cooldown_s` raises a config error.
**Reviewer Checklist:**
- The probe claim is a single SQL statement, never read then write.
- The breaker state is derived from the columns, never stored.
- Migration follows the existing `_migrate_vN_to_vM` pattern and bumps `user_version` to 13.
- The attempt loop itself is untouched in this phase.
**Verification Checks:**
- `cd /home/ngosi/projects/refract/server && uv run pytest -q tests/test_config.py tests/test_database.py tests/test_execution.py`
- `cd /home/ngosi/projects/refract/server && uv run pytest -q`

### Phase 3: Single-selection execution and stored result metadata

**Task Guide Input:** Remove the silent cross-target attempt loop and backoff from `TargetExecutor.execute`, fail jobs with `circuit_open` before spawning the CLI when no target is admissible, classify `failure_kind` and `retryable`, and persist per-job result metadata. Use case: non-UI repository implementation.
**Goal:** Each job makes one target selection and stores `result_metadata_json` matching the DESIGN.md schema.
**Files:**
- Modify: `server/src/refract/execution.py`
- Modify: `server/src/refract/database.py`
- Modify: `server/src/refract/models.py`
- Modify: `server/tests/test_execution.py`
- Modify: `server/tests/test_runtime.py`
- Modify: `server/tests/test_scheduler.py`, only where it asserts fallback
- Modify: `server/tests/test_smoke.py`, only where it asserts fallback
**Tasks:**
1. Remove the `for attempt in range(plan.selection.max_attempts)` loop, the `attempted` set, and the `random`/backoff code. Keep context-overflow repair, the recorder, semaphores, session handling, and events. Emit `target.attempt_started` and `target.attempt_finished` once.
2. When no target is admissible at dispatch, return a `circuit_open` failure without calling the driver.
3. Build metadata in `execute()`: the `usage` fields from Phase 1, `duration_ms`, and `model_name` falling back to `target.model`. Set `failure_kind` and `retryable` per the DESIGN.md table, leaving `next_target` unset because it is computed at wait time. Return it on `TargetExecutionResult`.
4. Persist metadata through `finish_job` and `finish_fresh_job_success` into `jobs.result_metadata_json`. Add `metadata: dict[str, Any]` to `JobResult` and populate it in `JobView`.
**Acceptance Criteria:**
- With two targets and the first returning `RETRYABLE`, the driver is called once and the job fails with `failure_kind="retryable"`.
- Context-overflow repair still succeeds on the same target.
- With every target open at dispatch, the driver is never called and `failure_kind="circuit_open"`.
- `job.result.metadata` holds every schema key; unreported keys are `None`.
- No test still asserts cross-target fallback; each rewritten test is listed in `journal.md`.
- `grep -n "random\|retry_scheduled" server/src/refract/execution.py` prints nothing.
**Reviewer Checklist:**
- Semaphore and `_target_active` accounting stay balanced on every exit path, including cancellation.
- `failure_kind` mapping matches the DESIGN.md table exactly.
- `JobSummary` fields are unchanged.
**Verification Checks:**
- `cd /home/ngosi/projects/refract/server && uv run pytest -q tests/test_execution.py tests/test_runtime.py tests/test_scheduler.py tests/test_smoke.py`
- `cd /home/ngosi/projects/refract/server && ! grep -n "random\|retry_scheduled" src/refract/execution.py`
- `cd /home/ngosi/projects/refract/server && uv run pytest -q`

### Phase 4: MCP surface for next_target, metadata, and targets_unavailable

**Task Guide Input:** Expose result metadata and a live opaque `next_target` token in `job_wait`, accept `next_target` on `job_submit`, and fail `job_submit` and `job_retry` fast with a new `targets_unavailable` error carrying `retry_after_s`. Use case: non-UI repository implementation of the MCP API.
**Goal:** The MCP client can read job metadata and route a follow-up job to the next healthy target without seeing target identity.
**Files:**
- Modify: `server/src/refract/planning.py`
- Modify: `server/src/refract/runtime.py`
- Modify: `server/src/refract/server.py`
- Modify: `server/src/refract/models.py`
- Modify: `server/tests/test_runtime.py`
- Modify: `server/tests/test_server.py`
**Tasks:**
1. In `planning.py`, add token functions: `nt_` + the first 16 hex characters of `sha256(config_revision, project_id, profile, workflow, target_execution_key)`. Add a resolver that maps a token back to a candidate target or `None`.
2. `Runtime.submit` and the `job_submit` tool gain optional `next_target`. A match pins the stored plan to one target; no match raises `invalid_request`. Add the all-open pre-check that raises `targets_unavailable` with `retry_after_s` before any insert. Apply the same pre-check in `Runtime.retry`.
3. Register `targets_unavailable` in `_ERROR_CODES`. Allow `retry_after_s` in public error payloads without weakening `_ERROR_FIELDS` validation for other codes.
4. `job_wait` adds `result.metadata` to every terminal page. For failed jobs it computes `next_target` live: the next non-open target after the failed one in profile order. Update `_JOB_SUBMIT_DESCRIPTION`, `_JOB_WAIT_DESCRIPTION`, and the server instructions text.
**Acceptance Criteria:**
- A failed job's `job_wait` returns a non-null `next_target` when a second healthy target exists, and `null` when none does.
- Submitting with that token runs the job on the second target.
- A token from another profile, or from before a config reload, returns `invalid_request`.
- With all targets open, `job_submit` returns `targets_unavailable`, `retryable=true`, and an integer `retry_after_s`, and the job table row count is unchanged.
- `job_retry` returns `targets_unavailable` under the same condition.
- Every terminal page includes `result.metadata`, and each serialized response stays under 9,000 UTF-8 bytes.
- Serialized MCP payloads contain no `target_id`, `backend`, or `model` key.
**Reviewer Checklist:**
- The token reveals nothing about target identity and validates against the current config revision.
- `next_target` is computed at wait time, never stored.
- The pre-check runs before any database insert.
- `_public_data` stripping is unchanged.
**Verification Checks:**
- `cd /home/ngosi/projects/refract/server && uv run pytest -q tests/test_runtime.py tests/test_server.py`
- `cd /home/ngosi/projects/refract/server && uv run pytest -q`

### Phase 5: Dashboard, profile editor, and coordinator docs

**Task Guide Input:** Show the 3-state breaker in the dashboard targets view, stop the profile editor and config mutation from writing deprecated `max_attempts`, and update the coordinator plugin docs for the new MCP contract. Use cases: UI implementation in `server/web` and documentation in `plugin/`.
**Goal:** Operators see breaker state, editors no longer write `max_attempts`, and coordinator docs describe `next_target`, `result.metadata`, and `targets_unavailable`.
**Files:**
- Modify: `server/src/refract/models.py` (`TargetView`)
- Modify: `server/src/refract/execution.py` (`views`)
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/src/refract/config_mutation.py`
- Modify: `server/web/src/screens/Targets.jsx`
- Modify: `server/web/src/screens/Targets.test.jsx`
- Modify: `server/web/src/components/ProfileEditor.jsx`
- Modify: `server/web/src/screens/Profiles.test.jsx`
- Modify: `server/tests/test_dashboard.py`
- Modify: `server/tests/test_config_mutation.py`
- Modify: `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`
- Modify: `plugin/skills/coordinating-multi-model-work/SKILL.md`
**Tasks:**
1. Add `breaker_state: Literal["closed", "open", "half_open"]`, `cooldown_s`, and `probing: bool` to `TargetView`, computed in `TargetExecutor.views`. Render them in `Targets.jsx`, keeping the existing `circuit_open_until` handling.
2. Remove the `max_attempts` input and its payload field from `ProfileEditor.jsx`. Stop `config_mutation.py` from writing `max_attempts`, while preserving an existing value on round-trip.
3. Update `tool-contract.md`: the `job_submit` signature with `next_target`, the `job_wait` return with `result.metadata`, and the error table row for `targets_unavailable`. Update `SKILL.md` Gate 2 with one rule: on a failed job, read `result.metadata.failure_kind`, then resubmit with `next_target`, resubmit with `fresh_session=true` for `context_overflow`, or report.
**Acceptance Criteria:**
- The dashboard shows half-open and probing targets distinctly from open and closed ones.
- Profile editor save payloads contain no `max_attempts`; a config file with `max_attempts` round-trips without loss.
- `tool-contract.md` and `SKILL.md` match the Phase 4 wire contract.
- Both suites pass.
**Reviewer Checklist:**
- UI changes follow existing `Targets.jsx` patterns.
- Doc text matches implemented names and codes exactly.
- No new `[daemon]` settings UI was added; the breaker keys appear through the existing unclassified-key rows.
**Verification Checks:**
- `cd /home/ngosi/projects/refract/server/web && npx vitest run`
- `cd /home/ngosi/projects/refract/server && uv run pytest -q`
