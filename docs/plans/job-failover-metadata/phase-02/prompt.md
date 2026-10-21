## User Request
Implement plan `job-failover-metadata` (client-routed failover, job result metadata, 3-state circuit breaker). This is Phase 2 of 5. Phase 1 (backend usage parsing) is complete.

## Phase
The target breaker follows the DESIGN.md counting table with closed/open/half-open states, exactly one probe at a time, and correct behavior across daemon restart.

## Tasks
- task-1: In `config.py`, add `DaemonConfig.breaker_failure_threshold = 3`, `breaker_base_cooldown_s = 60`, and `breaker_max_cooldown_s = 900`. Parse them from `[daemon]` with the existing `_positive_int` and raise a config error unless `max >= base`. Keep parsing and validating `max_attempts`, but log one `config.deprecated_key` warning per profile workflow that sets it. `TargetSelection.max_attempts` stays so stored `execution_plan_json` keeps loading.
- task-2: In `database.py`, bump `_SCHEMA_VERSION` to 13 and add `_migrate_v12_to_v13` following the existing `_migrate_vN_to_vM` pattern, with exactly these statements:
  `ALTER TABLE target_health ADD COLUMN cooldown_s INTEGER NOT NULL DEFAULT 0;` (0 means base)
  `ALTER TABLE target_health ADD COLUMN probe_job_id TEXT NOT NULL DEFAULT '';`
  `ALTER TABLE jobs ADD COLUMN result_metadata_json TEXT NOT NULL DEFAULT '{}';`
  Fresh-database DDL must produce the same columns. Add methods for: atomic probe claim returning `rowcount == 1` (single statement: `UPDATE target_health SET probe_job_id=:job WHERE target_id=:key AND circuit_open_until<>'' AND circuit_open_until<=:now AND probe_job_id=''`); probe release (set `probe_job_id=''`, leave half-open); counted failure with threshold and exponential reopen (`cooldown_s = min(max, cooldown_s * 2)` for a failed probe, 0 treated as base); immediate open at current cooldown; success that resets failures, closes, clears probe, and resets `cooldown_s`; and a startup reset of orphaned probes (`probe_job_id=''`, `circuit_open_until=now`).
- task-3: In `execution.py`, rewrite `_record_failure`, `_select_target`, `_is_open`, and their breaker calls to use the derived 3-state rules and the counting table. Thresholds and cooldowns come from `self.config`. Do not change the attempt loop itself.
- task-4: In `runtime.start()`, call the orphaned-probe reset before the scheduler starts.

## Context
- Design: `docs/plans/job-failover-metadata/DESIGN.md`, sections "Dispatch", "Breaker state", "Breaker counting", "Migration".
- Derived state, never stored:
  - closed: `circuit_open_until = ''`
  - open: `circuit_open_until > now`, or `probe_job_id <> ''`
  - half-open: `circuit_open_until <= now` and `probe_job_id = ''`
- Counting table:
  | Outcome | Effect |
  |---|---|
  | `RETRYABLE` | +1 consecutive failure; opens at `breaker_failure_threshold`. A failed probe reopens with `cooldown_s = min(max, cooldown_s * 2)`. |
  | `TARGET_FATAL` | Opens immediately at current cooldown. |
  | `SUCCESS` | Resets failures, closes, resets `cooldown_s` to base. |
  | `context_overflow`, `CANCELLED`, `REQUEST_FATAL`, replay-blocked, `circuit_open` | Not counted. A held probe is released and left half-open. |
- Today: `database.py` has `_SCHEMA_VERSION = 12`, `target_health(target_id)`, `record_target_failure(target_id, circuit_open_until)`, and a success recorder. `execution.py` has `_select_target(target_ids, plan, attempted)` at ~line 402, `_record_failure(target_key)` hardcoding threshold 3 and 60 s, `_is_open(value, now)`, and `views()` reading `circuit_open_until`. `runtime.start()` at ~line 161 interrupts active jobs, then starts the scheduler.
- Half-open selection: a half-open target is usable only when the probe claim succeeds for this job; if the claim fails, treat it as open.

## Files
- `server/src/refract/config.py`
- `server/src/refract/planning.py` (only if needed for `max_attempts` deprecation)
- `server/src/refract/database.py`
- `server/src/refract/execution.py`, limited to `_select_target`, `_record_failure`, `_is_open`, and breaker calls
- `server/src/refract/runtime.py`, limited to `start()` recovery
- `server/tests/test_config.py`
- `server/tests/test_database.py`
- `server/tests/test_execution.py`
- `docs/plans/job-failover-metadata/phase-02/notes.md` and `journal.md`

## Done When
- The threshold opens the breaker; `TARGET_FATAL` opens it on the first failure; success closes it and resets `cooldown_s`.
- 20 concurrent claim calls on one half-open target yield exactly one `True`.
- A failed probe doubles `cooldown_s`, capped at `breaker_max_cooldown_s`.
- `context_overflow`, `CANCELLED`, and `REQUEST_FATAL` leave `consecutive_failures` unchanged and release a held probe.
- After restart, an orphaned probe target is half-open.
- A v12 database migrates to v13 with existing rows intact.
- A config with `max_attempts` loads and logs `config.deprecated_key`; `breaker_max_cooldown_s < breaker_base_cooldown_s` raises a config error.
- `cd /home/ngosi/projects/refract/server && uv run pytest -q tests/test_config.py tests/test_database.py tests/test_execution.py`
- `cd /home/ngosi/projects/refract/server && uv run pytest -q`

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md

- Edit only the files listed above. Do not touch any other file under `docs/plans/`.
- No Git operations: no commit, reset, restore, stash, or clean.
- Do not read or modify `~/.refract` or any secret-bearing file.
- The probe claim is one SQL statement, never read-then-write.
- Breaker state is derived from columns, never stored as a state column.
- Leave the attempt loop, backoff, and `random` usage in `execute()` unchanged; Phase 3 removes them.
- Test first. Append Task blocks to notes.md; append the ERP block under `## Implementation Response` in journal.md without overwriting its META.
- Run test suites serially, not in parallel.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
