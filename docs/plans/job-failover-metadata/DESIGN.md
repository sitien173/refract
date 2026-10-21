# Client-Routed Failover, Result Metadata, and 3-State Circuit Breaker Design

**Status:** Confirmed 2026-10-21
**Consultation:** consult job `5fc71b72-c654-4aae-b149-178a7a50ddc1` agreed with all decisions; added atomic SQLite probe claim, immediate open on `TARGET_FATAL`, and flagged `depends_on` cancellation on transient failure. Its backend telemetry paths are UNVERIFIED; Step 0 resolves them.

## Purpose

Make job execution fast and transparent for the MCP client (Coordinator):

1. Remove the silent cross-target attempt loop. A failed job returns at once with a routing hint so the client decides whether to submit a follow-up job.
2. Return per-job metadata: model, context window, and token usage.
3. Replace the 2-state target breaker with a 3-state circuit breaker and fail fast when no target is usable.

## Users and Success Criteria

Users: MCP clients acting as Coordinator; daemon operators through config and dashboard.

Success criteria:

- A failed job runs exactly one target selection. No backoff sleep, no second target.
- Terminal `job_wait` responses carry `result.metadata` on every page, within the 9,000-byte response limit.
- On failure, `result.metadata.next_target` is an opaque token or `null`; `job_submit(next_target=...)` pins the job to that target.
- With every candidate target open, `job_submit` and `job_retry` return `targets_unavailable` with `retry_after_s`, and no job row is created by `job_submit`.
- Half-open admits exactly one probe across concurrent dispatches and survives daemon restart without wedging.
- `target_id`, `backend`, and `model` keys remain stripped from all MCP payloads.
- Existing configs containing `max_attempts` still load.
- `cd server && uv run pytest -q` passes. The exact runner is confirmed from `pyproject.toml` during planning.

## Constraints and Non-Goals

Constraints:

- Target and backend identity stay private. Only the public model string is exposed, as `model_name`.
- Wire changes are additive. `JobSummary` field set is unchanged.
- Same-target `context_overflow` session repair in `execution.py` is retained.
- Usage parsers are written only against captured real CLI output, never guessed field names.

Non-goals:

- `cost_usd`, `num_turns`, or other metadata beyond the lean set.
- Listing targets or their health through `task_guide`.
- Changing `job_retry` semantics or reviving cancelled dependents.
- New dashboard UI for breaker config keys unless the editor already renders `[daemon]` keys generically.

## Chosen Approach

Server-computed hint plus submit parameter. A failed job's `job_wait` result carries `metadata.next_target`, an opaque token bound to config revision, profile, workflow, and target execution key. `job_submit` accepts an optional `next_target`.

Rejected alternatives:

- Target list in `task_guide`: larger public target surface and more privacy exposure.
- `job_retry` auto-advance: changes `job_retry` meaning and does not restore dependents cancelled by the failure.
- Full identity exposure: breaks the documented privacy contract.

## Architecture and Data Flow

### Submit (`runtime.py`, `server.py`)

1. `job_submit` gains optional `next_target: str = ""`.
2. When set, resolve the profile's candidate targets for the workflow at the current config revision and look up the token. A match pins the stored execution plan to that one target. No match returns `invalid_request` with next action "Resubmit without next_target."
3. Breaker pre-check over the candidates, or the single pinned target. If all are open, return `targets_unavailable`, `retryable=true`, `retry_after_s` = seconds until the earliest half-open time. No job row is written.

### Token

`next_target` = `nt_` + first 16 hex characters of `sha256(config_revision, project_id, profile, workflow, target_execution_key)`. Validation recomputes tokens for current candidates; no secret, no table.

### Dispatch (`execution.py`)

4. `TargetExecutor.execute` removes the `for attempt in range(max_attempts)` loop and the `min(8, 2**n)` backoff. It selects one target: the first non-open target with free capacity, else the first non-open target.
5. Half-open admission uses one atomic statement:
   `UPDATE target_health SET probe_job_id=:job WHERE target_id=:key AND circuit_open_until<>'' AND circuit_open_until<=:now AND probe_job_id=''`. Only `rowcount == 1` runs the probe.
6. If every candidate opened between submit and dispatch, the job fails with `failure_kind="circuit_open"` without spawning the CLI. This does not count toward the breaker.
7. Same-target context-overflow repair runs unchanged.

### Result (`backends/*`, `drivers.py`, `database.py`, `server.py`)

8. `BackendResult` (`backends/__init__.py`) and `DriverResult` (`drivers.py`) gain an optional `usage` dict filled by each backend from its stream.
9. `execution.py` adds `duration_ms` and sets `model_name` from the stream, else the target's configured `model`.
10. New column `jobs.result_metadata_json` stores metadata. `job_wait` returns `result.metadata` on every terminal page.
11. On failure, `next_target` is computed at `job_wait` time from live breaker state: the next non-open target in profile order after the failed one, else `null`.
12. `_FORBIDDEN_OUTPUT_KEYS` is unchanged. Metadata keys are `model_name` and `next_target`, so the recursive strip does not remove them.

### `result.metadata` schema

| Key | Type | Notes |
|---|---|---|
| `model_name` | string or null | Public model string |
| `context_window_max` | int or null | Backend-reported |
| `context_window_used` | int or null | Backend-reported or derived from final-turn usage |
| `input_tokens` | int or null | |
| `output_tokens` | int or null | |
| `cached_input_tokens` | int or null | |
| `duration_ms` | int or null | Wall clock of the target run, including overflow repair |
| `failure_kind` | string or null | Null on success |
| `retryable` | bool or null | Null on success |
| `next_target` | string or null | Failure only |

### Breaker state (`database.py`)

13. `target_health` gains `cooldown_s` and `probe_job_id`. State is derived, never stored:
    - closed: `circuit_open_until = ''`
    - open: `circuit_open_until > now`, or `probe_job_id <> ''`
    - half-open: `circuit_open_until <= now` and `probe_job_id = ''`
14. Startup recovery clears orphaned probes by setting `probe_job_id=''` and `circuit_open_until=now`. Cancelling a probe job releases its probe the same way.

## Errors and Edge Cases

### Breaker counting

| Outcome | Effect |
|---|---|
| `RETRYABLE` | +1 consecutive failure; opens at `breaker_failure_threshold`. A failed probe reopens with `cooldown_s = min(max, cooldown_s * 2)`. |
| `TARGET_FATAL` | Opens immediately at current cooldown. |
| `SUCCESS` | Resets failures, closes, resets `cooldown_s` to base. |
| `context_overflow`, `CANCELLED`, `REQUEST_FATAL`, replay-blocked, `circuit_open` | Not counted. A held probe is released and left half-open. |

### `failure_kind` and `retryable`

| `failure_kind` | `retryable` |
|---|---|
| `retryable` | true when `next_target` is non-null |
| `target_fatal` | true when `next_target` is non-null |
| `circuit_open` | true when `next_target` is non-null |
| `context_overflow` | true; hint: resubmit with `fresh_session=true` |
| `cancelled` | true when `next_target` is non-null |
| `request_fatal` | false |
| `replay_blocked` | false; tools ran, Coordinator must inspect the tree first |

### Public errors

- New code `targets_unavailable`, `retryable=true`, with `retry_after_s`. With a probe in flight, `retry_after_s` defaults to `breaker_base_cooldown_s`.
- Stale or foreign `next_target` returns `invalid_request`.

### `job_retry`

Keeps current meaning: re-run the same `job_id`, re-select from the job's plan. A pinned plan stays pinned. All candidates open returns `targets_unavailable`.

### Behavior change

A transient failure now ends the job and cancels queued `depends_on` dependents; previously a silent fallback could hide it. The Coordinator resubmits the chain.

## Migration

### Config (`config.py`, `[daemon]`)

```toml
[daemon]
breaker_failure_threshold = 3
breaker_base_cooldown_s   = 60
breaker_max_cooldown_s    = 900   # must be >= breaker_base_cooldown_s
```

Validated with the existing `_positive_int`.

### `max_attempts`

- Still parsed and validated, then ignored.
- Each load logs one `config.deprecated_key` warning per profile workflow that sets it.
- `TargetSelection.max_attempts` remains so stored `execution_plan_json` keeps loading.
- `config_mutation.py` stops writing it.

### Database v12 to v13 (`database.py`)

```sql
ALTER TABLE target_health ADD COLUMN cooldown_s INTEGER NOT NULL DEFAULT 0;   -- 0 means base
ALTER TABLE target_health ADD COLUMN probe_job_id TEXT NOT NULL DEFAULT '';
ALTER TABLE jobs ADD COLUMN result_metadata_json TEXT NOT NULL DEFAULT '{}';
```

Existing jobs return metadata with all fields null.

### Wire and docs

- Additive: `result.metadata`, optional `next_target` on `job_submit`, error `targets_unavailable`.
- `JobSummary.attempts` now counts runs of the job across `job_retry`.
- `models.TargetView` and `dashboard.py` show `closed | open | half_open`, cooldown, and probe status.
- Update `plugin/skills/coordinating-multi-model-work/references/tool-contract.md` for the new signature, metadata, and error code.
- Update `coordinating-multi-model-work` so the Coordinator acts on `failure_kind` and `next_target`.
- Update the MCP tool descriptions and server instructions in `server.py`.

## Testing

### Step 0: capture real CLI output

Run each of `claude`, `codex`, `pi`, and `agy` once with a trivial prompt in its structured mode. Save redacted output under `server/tests/fixtures/usage/`. Write parsers against these fixtures. A backend whose output lacks a field reports null, recorded in the plan.

### Tests, RED first

- `test_execution.py`: single selection, no second target; overflow repair still runs; pre-dispatch `circuit_open` spawns no CLI; `duration_ms`; `model_name` config fallback.
- Breaker table: threshold opens; fatal opens immediately; exactly one probe across N concurrent claims; probe success closes; probe failure doubles cooldown to cap; restart clears an orphaned probe; cancelling a probe releases it.
- `test_runtime.py`: `targets_unavailable` with `retry_after_s` and no job row; valid `next_target` pins; stale token returns `invalid_request`; `job_retry` returns `targets_unavailable` when all are open.
- `test_config.py`: three new keys and validation; `max_attempts` deprecation warning.
- `test_database.py`: v12 to v13 migration on a v12 database.
- `test_server.py`: `result.metadata` on every terminal page within byte limits; live `next_target`; privacy filter still strips `target_id`, `backend`, `model`.
- `test_streaming_backends.py`: per-backend usage parsing from fixtures; missing keys give null.

Existing tests asserting cross-target fallback or `attempts == 2` are rewritten; each rewrite is listed in the phase journal.

## Risks and Open Questions

Risks:

- `depends_on` chains break on transient failures that the loop previously hid.
- A long-running probe blocks a single-target profile for the probe's duration; `retry_after_s` is an estimate in that case.
- CLI JSON schemas drift across versions; parsers must tolerate missing keys.
- The coordinator plugin docs and server tool descriptions must change in lockstep with the wire change.

Open questions:

- Which of `context_window_max` and `context_window_used` each backend reports. Resolved by Step 0.
- Whether the dashboard config editor renders `[daemon]` keys generically. Resolved during planning.
