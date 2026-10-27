<!-- refract-shared-version: 2.0.0 -->

# Phase 2 Decision Notes

## Task 1

### Decisions made
- Added an `environment_targets` list to new execution snapshots only when non-empty; it contains target ids but no declaration values or templates. Historical snapshots default to an empty marker.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - Initial exploratory failure at round-trip equality was an invalid assertion because snapshots intentionally omit raw declarations; it is not counted as RED evidence.
  - Genuine RED: temporarily omitted marker serialization and ran `cd server && uv run pytest tests/test_planning.py -k environment_marker`; `test_plan_environment_marker_is_structural_and_legacy_absence_is_empty` failed with `KeyError: 'environment_targets'` (1 failed, 4 passed, 41 deselected).
  - GREEN: restored structural-only marker serialization; `cd server && uv run pytest tests/test_planning.py -k 'environment_marker or invalid_environment_marker'` passed 5 tests and asserts marker round-trip, invalid marker rejection, and template absence.
- Root cause (bugfix only): - none

## Task 2

### Decisions made
- Runtime resolves declarations from the current project catalog by stored target id in `run_sync`; only resolved environment overrides are returned to the executor. Stored target policy remains the execution plan's source of truth.
- Narrowing a plan with a `next_target` token also filters the environment marker to that target, preventing stale marker ids from invalidating the durable snapshot.
- Configuration failure returns a fixed structural error as `REQUEST_FATAL` with `config_invalid` metadata, before session preparation or process invocation, and releases any claimed probe without changing provider health.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Project/global catalog revisions from the existing runtime loader and project file identity are sufficient configuration revision context; secret values are never fingerprinted.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED (genuine behavior regression): temporarily removed Runtime's `environment_resolver` wiring and ran `cd server && uv run pytest tests/test_execution.py -k environment_binding_reaches_driver`; `test_environment_binding_reaches_driver_without_persisting_values` failed because job state was `failed`, expected `succeeded`.
  - GREEN: restored wiring; regression passed with inherited/shared/project/local values in a fake child process, ask token, persistence/log checks, and an unchanged `os.environ`.
  - Other GREEN checks: `cd server && uv run pytest tests/test_runtime.py -k 'resolves_current_project_environment or rejects_removed_marked_target'` passed 2 tests; configuration failure test passed and asserts no backend call, no secret in result, and no circuit-health failure.
  - RED: temporarily omitted `environment_targets` filtering when narrowing a `next_target` plan; `cd server && uv run pytest tests/test_runtime.py -k submit_pins_valid_token` failed at `assert "environment_targets" not in stored_plan` (1 failed, 32 deselected). Restored filtering; the same command passed (1 passed, 32 deselected).
  - Full suite after task 2: `cd server && uv run pytest`, exit 0; 883 passed, 15 deselected in 207.89s (background log `/tmp/phase2-task2-pytest.log`). This run preceded the final task-3/4 test additions.
- Root cause (bugfix only): - none

## Task 3

### Decisions made
- Bind once after selecting a marked target and before session preparation. Keep the returned mapping in the execution context, reuse it for automatic retry/recovery invocations, and merge per-attempt daemon ask credentials last.
- Bindings are local execution objects only; there is no job-secret cache or `os.environ` mutation. Explicit retries and queued restart naturally execute the resolver again.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing driver `env` transport carries the configured override map into backend parameters; no backend changes are needed.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: the Runtime resolver-wiring removal RED recorded under Task 2 also demonstrates the execution binding path is required; the job failed before driver invocation.
  - GREEN: `cd server && uv run pytest tests/test_execution.py -k environment_binding_reaches`, `... -k explicit_retry_rebinds`, and `... -k queued_restart_binds_current_project_environment` each passed (1 passed). Automatic retry retained identical bindings; explicit retry observed project rotation; queued restart observed current configuration. Daemon ask token was present in the driver environment.
  - Recovery GREEN: `cd server && uv run pytest tests/test_execution.py -k retry_recovery_to_transient_to_success` passed (1 passed); all initial/reconstruct/retry invocations observed the same binding.
- Root cause (bugfix only): - none

## Task 4

### Decisions made
- Correction to the initial implementation: raw `catalog.config_revision` is a SHA-256 of secret-bearing config bytes and was not safe as an allegedly opaque revision input. Runtime now computes an HMAC of the global revision plus project-file identity using one random 256-bit per-runtime key. No raw config digest or resolved secret is exposed in the persisted session key; same revision reuses identity within a runtime, rotation changes it, and restart rotates the HMAC key to prevent unsafe reuse.
- Environment-free target identity and session keys remain unchanged.
- Capacity semaphores and target-active accounting remain keyed by target id, not environment revision.

### Spec deviations
- none

### Tradeoffs accepted
- Project-file identity (mtime, size, inode) is used as project revision context because Phase 1's project catalog does not define a separate project revision field. Environment-enabled sessions intentionally do not resume across daemon restart because the in-memory HMAC key rotates; queued jobs bind current configuration and start with a distinct session context.

### Assumptions
- Existing driver availability and structured-mode checks intentionally remain daemon-environment based; only per-invocation backend env is changed.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - Opaque-revision RED: with the former raw config-digest revision, `cd server && uv run pytest tests/test_runtime.py -k environment_session_revision_is_opaque` failed at `assert restarted != first`: both contexts were `'["",null]'` across Runtime instances (1 failed, 33 deselected).
  - Opaque-revision GREEN: HMAC-keyed per-runtime identity restored same-runtime stability and restart separation; the same command passed (1 passed, 33 deselected).
  - Transport RED: temporarily omitted env from TargetExecutor's driver call and ran `cd server && uv run pytest tests/test_execution.py -k real_driver_backend_shell_transport`; the fake Codex child had `SHARED_ONLY`, `PROJECT_ONLY`, `LOCAL_ONLY`, and `LAYERED` as `None` instead of configured values (1 failed, 150 deselected).
  - Transport GREEN: restored env forwarding; actual DriverRegistry -> BackendParams.env -> Codex backend -> fake subprocess test passed (1 passed), including inherited/project/shared/local precedence, ask URL/token, persistence/log checks, unchanged `os.environ`, and an isolated synthetic `CODEX_HOME`.
  - Snapshot policy: `cd server && uv run pytest tests/test_execution.py -k stored_target_policy_survives_current_policy_changes` passed; current backend/args/capacity/retry policy changed, while execution used the stored target policy and current rotated environment.
  - RED: temporarily removed the revision-qualified session target key and ran `cd server && uv run pytest tests/test_execution.py -k explicit_retry_rebinds`; `test_explicit_retry_rebinds_rotated_project_environment` failed at `assert len(session_keys) == 2 and session_keys[0] != session_keys[1]` with `AssertionError: assert (2 == 2 and 'primary:fcb7f648a676a587' != 'primary:fcb7f648a676a587')` (1 failed, 147 deselected).
  - Cancellation RED: temporarily removed the configuration-resolution `CancelledError` cleanup and ran `cd server && uv run pytest tests/test_execution.py -k cancellation_during_environment_resolution_releases_probe`; it failed because the half-open probe remained `cancel-env-resolution`. Restored cleanup; same command passed (1 passed, 149 deselected).
  - GREEN: restored revision-qualified target/session context; `cd server && uv run pytest tests/test_execution.py -k 'explicit_retry_rebinds or queued_restart_binds_current_project_environment or retry_recovery_to_transient_to_success or legacy_snapshot_ignores_current_target_environment or environment_configuration_failure or environment_binding_reaches'` passed 6 tests.
  - Project isolation/rotation: `cd server && uv run pytest tests/test_runtime.py -k 'resolves_current_project_environment or rejects_removed_marked_target'` passed 2 tests; concurrent two-project execution regression passed (`cd server && uv run pytest tests/test_execution.py -k concurrent_projects_keep_environment_bindings_isolated`), with distinct values and active backend count held at the single configured capacity. Existing `test_target_execution_key_matches_literal_pre_change_fixture` covers legacy target identity.
  - Prior phase-completion gate before this specification-fix batch: `cd server && uv run pytest`, exit 0; 889 passed, 15 deselected in 227.98s (background log `/tmp/phase2-final-final.log`).
  - Fix-batch gate before isolating the fake Codex home: `cd server && uv run pytest`, exit 0; 892 passed, 15 deselected in 212.47s (background log `/tmp/phase2-fix-batch1-final.log`).
  - Final fresh fix-batch gate after isolating fake `CODEX_HOME`: `cd server && uv run pytest`, exit 0; 892 passed, 15 deselected in 269.60s (background log `/tmp/phase2-fix-batch1-final-fresh.log`).
- Root cause (bugfix only): - none

## Fix Batch 2

### Decisions made
- Replaced the independent post-resolution filesystem observation (`_file_identity`) in `_resolve_target_environment` with an atomic catalog snapshot returning `(catalog, revision)`.
- Derived revision context directly from the exact catalog snapshot used for resolution, ensuring identical catalog configurations produce identical revision contexts and intervening external edits cannot label old bindings with new identity contexts.
- Retained per-runtime HMAC-keyed revision tokens and bounded project-catalog caching (`_project_catalogs` keyed by project root).

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - Genuine behavior regression 1 (real filesystem edit between catalog acquisition and revision generation): `cd server && uv run pytest tests/test_runtime.py -k test_resolve_target_environment_derives_revision_from_catalog_snapshot_not_subsequent_stat` failed at `assert first_revision != second_revision`:
    `AssertionError: assert '76c80c063a28e800aca713e094ac8817b95fa73294c82bf6bcb75da1125dc377' != '76c80c063a28e800aca713e094ac8817b95fa73294c82bf6bcb75da1125dc377'`
  - Genuine behavior regression 2 (reviewer mocked reproduction sequence `[old,new,new,new]` and `[old_catalog,new_catalog]`): `cd server && uv run pytest tests/test_runtime.py -k test_resolve_target_environment_mocked_sequence_does_not_label_old_binding_with_new_identity` failed at `assert first_revision != second_revision`:
    `AssertionError: assert '64ba10fef631d8c79a57255a2ce18f85fb680fe359d1508199897eacd99d096a' != '64ba10fef631d8c79a57255a2ce18f85fb680fe359d1508199897eacd99d096a'`
  - Targeted GREEN: `cd server && uv run pytest tests/test_runtime.py -k "test_resolve_target_environment_derives_revision or test_resolve_target_environment_mocked_sequence"` passed 2 tests in 0.37s.
  - Runtime suite GREEN: `cd server && uv run pytest tests/test_runtime.py` passed 36 tests in 1.68s.
  - Fresh full gate run: `cd server && uv run pytest`, exit 0; 894 passed, 15 deselected in 236.40s.
- Root cause (bugfix only):
  - In `_resolve_target_environment`, after obtaining the project catalog, `_file_identity` was queried independently against the filesystem to produce the revision context. An external file edit occurring between catalog loading and this secondary stat labeled the old environment binding with the new file identity's revision context, allowing subsequent executions under the new configuration to share the same revision context and improperly reuse the old session. Resolving `(catalog, revision)` together from `_project_catalog_snapshot` pairs the revision context strictly with the catalog snapshot used for resolution.

## Additional bounded review fix (authorized)

### Decisions made
- `_project_catalog_snapshot` now compares project config identity before and after each cache-miss load, retries at most three times, and caches/revisions only a catalog whose surrounding identities match. Continuous change raises a fixed structural `ValueError`; the existing execution boundary sanitizes it.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Filesystem identity is the existing `(mtime, size, inode)` snapshot contract; stability across a bounded load is the best available validation without hashing secret-bearing file contents.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - Genuine RED before production edit: `cd server && uv run pytest tests/test_runtime.py -k project_catalog_snapshot_retries_when_file_changes_during_load -q` failed at `assert len(loaded) == 2`; actual load count was 1, proving the pre-load identity race was accepted without retry.
  - GREEN: `cd server && uv run pytest tests/test_runtime.py -q` passed: 38 passed in 2.05s. Includes cache-miss/change/retry, continuous-churn bounded failure with no secret in error, and prior snapshot/revision tests.
  - Fresh full gate: `cd server && uv run pytest`, exit 0; 896 passed, 15 deselected in 190.67s (background log `/tmp/target-env-phase2-extra-fix-pytest.log`).
- Root cause (bugfix only):
  - A cache miss captured identity only before `load_project_config`; a change during the load meant the returned catalog could be cached and tagged with an identity belonging to different file contents. A global reload creates a new base object, bypasses the cached project catalog, and makes this pre-load race reachable even when the project identity was observed in an earlier execution.
