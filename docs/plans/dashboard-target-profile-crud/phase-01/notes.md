<!-- ccg-shared-version: 10.2.0 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Revisions are the SHA-256 digest of the exact source bytes read once through
  `config_inspection.read_config_source`, reusing existing revision semantics.
- Preservation assertions target `tomlkit` round-trip stability of untouched
  regions (comments, definition order, quoting, unrelated sections), plus
  localized shorthand expansion and legacy key retention, per "where `tomlkit`
  permits".
- Path-safety tests cover symlinks, directories, swapped-in symlinks, and
  service-level rejection of unsafe global sources.
- Atomicity tests assert temp writes stay in the source directory, file mode is
  preserved, the revision is rechecked immediately before replacement, and
  creation is exclusive (no-replace link publication).

### Spec deviations
- none

### Tradeoffs accepted
- Preservation is byte-guaranteed for untouched regions only; nodes that
  `tomlkit` must render carry that library's canonical spacing.

### Assumptions
- Filesystem tests run on the local platform with standard umask behavior.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Disabling the document-level stale-revision check and the
  pre-replace recheck in `commit_bytes` fails
  `test_commit_rechecks_revision_immediately_before_replace` (DID NOT RAISE);
  disabling the rollback proof in `_confirm_current` fails
  `test_rollback_refuses_to_overwrite_later_external_edit` (publication error
  escaped, external edit overwritten). Restoring the guards returns both to
  green.
- Root cause (mode probe): `NamedTemporaryFile` creates `0o600` under umask
  `0o077`; a source mode of `0o640` would degrade to `0o600` without
  `_FileMode.apply` before `os.replace`, proving the mode-preservation guard is
  load-bearing.

## Task 2

### Decisions made
- Candidate validation reuses `openmcp.config` semantics exactly: global
  candidates are written to a sibling validation copy and loaded with
  `load_config`; project candidates are loaded through `load_project_config`
  against the live runtime catalog. No second schema exists.
- A `ConfigurationMutationService` instance on `Runtime` owns all TOML document
  primitives and exposes a re-entrant `threading.RLock` shared with job
  planning and reload paths.
- String edits preserve the existing literal style and trailing trivia
  (indent/comment); workflow kinds are probed as string, array, inline table,
  or sub-table before mutation so inline policies are edited in place.

### Spec deviations
- none

### Tradeoffs accepted
- Validation writes a temporary candidate copy beside the source (same
  directory) so `load_config`'s home-relative and file-identity semantics match
  the real load.

### Assumptions
- TOML syntax-tree primitives are exercised through unit tests now; endpoint
  wiring arrives in later phases.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `tests/test_config_mutation.py` preservation, shorthand
  expansion, legacy-key, and reusable primitive tests pass (33 passed in the
  file). Full targeted suite 95 passed
  (`tests/test_config_mutation.py tests/test_runtime.py tests/test_execution.py`).
- `uv run pytest tests/test_config.py tests/test_planning.py -q` -> 63 passed.

## Task 3

### Decisions made
- `commit_document` / `create_project_document` run entirely under the service
  lock: revision read and recheck, candidate validation, atomic replacement,
  runtime publication, and rollback.
- Global commits reload and publish the catalog
  (`Runtime._publish_configuration_locked`), which refreshes the executor
  configuration and configuration health; project commits re-resolve the
  registered project against the committed file and live global catalog.
- Rollback restores the exact original bytes only after proving the current
  file still matches the committed candidate revision (`_confirm_current`);
  unprovable or raced state is reported as uncertain rather than overwritten.
- `TargetExecutor.refresh_configuration` adopts a published catalog without
  touching capacity semaphores or active counters keyed by submitted-plan
  execution identity, so running and queued jobs keep their snapshots.

### Spec deviations
- none

### Tradeoffs accepted
- Rollback republish failures are logged and reported, never fatal, because the
  original file bytes were already restored.

### Assumptions
- Platform directory fsync is bounded to POSIX and wrapped so unsupported
  platforms degrade to a warning rather than a failure.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Stale-revision, missing-revision, external-edit conflict,
  invalid-candidate rejection, valid-commit publication, registered-project
  compatibility, project create/edit, and publication-failure rollback tests
  pass. Rollback safety demonstrated by the `_confirm_current` weakening above.
- `uv run pytest tests/test_runtime.py tests/test_execution.py -q` passes
  within the 95-test targeted run.

## Task 4

### Decisions made
- Global and project reload/planning entry points now take the shared mutation
  lock (`Runtime.submit`, `catalog_for_project`, `_reload_catalog` wrappers),
  so planning never reads a disk-new catalog while the runtime still publishes
  an old one.
- No change was required to `src/openmcp/config.py`: candidate validation
  reuses its existing `load_config` / `load_project_config` entry points.

### Spec deviations
- none

### Tradeoffs accepted
- The planning lock is acquired synchronously inside `Runtime.submit` before
  the async enqueue, matching the phase's single-boundary requirement without
  an awaitable lock.

### Assumptions
- Dashboard read endpoints already observe `runtime.catalog` /
  `catalog_for_project_cached`; mutation wiring that guards editor reads lands
  in Phase 2+.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  `tests/test_execution.py::test_new_submissions_use_refreshed_catalog_while_existing_plan_stable`
  writes a refreshed catalog, publishes it, submits a second job, and asserts
  the new plan carries the new model while the earlier submitted plan still
  carries the old model and a distinct `config_revision`.
- Full suite: 349 passed, 3 deselected in 7.22s.
- `git diff --check` clean.

## Review Fixes

### Decisions made
- `_FileMode.apply` raises `ConfigurationMutationError` with code `configuration_commit_failed` when `os.chmod` fails, preventing replacement.
- `commit_bytes` and `restore_bytes` re-read `path` and verify expected revision immediately before `os.replace`, preventing TOCTOU external edits injected after temporary file creation.
- `restore_bytes` accepts `expected_revision` to ensure rollback never clobbers external edits occurring after publication failure.
- `_rollback_failed_creation` rechecks `_confirm_current` immediately before `path.unlink()` so external edits after rollback proof are never deleted.
- Global `commit_document` unconditionally validates all registered project overlays against candidate global configuration.
- `_validate_registered_projects` provides a thread-safe connection fallback when called from worker threads.
- `resolve_project_catalog` uses `shutil.rmtree(temporary_root, ignore_errors=True)` to ensure complete removal of temporary directories.

### Spec deviations
- none

### Tradeoffs accepted
- SQLite thread isolation requires opening a per-thread read connection during cross-thread candidate overlay validation.

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - `test_commit_rejects_external_edit_injected_after_temp_write`: RED (overwrote external edit injected after temp write) -> GREEN (raises `configuration_conflict`, retains edit).
  - `test_rollback_refuses_to_overwrite_edit_injected_after_temp_write`: RED (overwrote external edit during rollback restore) -> GREEN (raises `configuration_commit_failed`, retains edit).
  - `test_rollback_creation_refuses_deletion_on_external_edit`: RED (deleted externally edited file) -> GREEN (raises `configuration_commit_failed`, preserves file).
  - `test_commit_fails_if_mode_preservation_fails`: RED (DID NOT RAISE, replaced file despite chmod failure) -> GREEN (raises `configuration_commit_failed`, aborts replacement).
  - `test_project_validation_temp_directory_cleaned_up`: RED (leaked temporary directory in `/tmp`) -> GREEN (directory removed).
  - `test_global_commit_always_validates_registered_projects`: RED (DID NOT RAISE, allowed invalidating registered project) -> GREEN (raises `configuration_invalid`).

## Second Review Fixes

### Decisions made
- Use `renameat2` with `RENAME_EXCHANGE` for atomic exchange.
- Swap temporary candidate and target path atomically on commit.
- Inspect exchanged file revision immediately after atomic exchange.
- Restore exchanged state only when target remains unchanged.
- Swap temporary tombstone and target on rollback deletion.
- Fail closed when atomic exchange primitive is unavailable.
- Fail closed when platform is not Linux.
- Re-raise `shutil.rmtree` errors in `resolve_project_catalog`.

### Spec deviations
- none

### Tradeoffs accepted
- Atomic exchange requires Linux kernel `renameat2` support.
- Non-Linux platforms fail closed for safe mutations.

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED to GREEN:
  - `test_commit_rejects_external_atomic_replacement_at_publication`: RED to GREEN. Conflict raised. Replacement preserved.
  - `test_commit_rejects_external_edit_injected_before_atomic_exchange`: RED to GREEN. Conflict raised. Edit preserved.
  - `test_commit_restoration_does_not_overwrite_newer_edit`: RED to GREEN. Conflict raised. Newer edit preserved.
  - `test_rollback_refuses_to_overwrite_external_atomic_replacement`: RED to GREEN. Rollback failed raised. Replacement preserved.
  - `test_rollback_restore_does_not_overwrite_newer_edit`: RED to GREEN. Rollback failed raised. Newer edit preserved.
  - `test_rollback_creation_refuses_deletion_on_external_atomic_replacement`: RED to GREEN. Rollback failed raised. Replacement preserved.
  - `test_atomic_exchange_fails_closed_when_primitive_unavailable`: RED to GREEN. Fail closed verified.
  - `test_rollback_restore_fails_closed_when_primitive_unavailable`: RED to GREEN. Fail closed verified.
  - `test_rollback_creation_fails_closed_when_primitive_unavailable`: RED to GREEN. Fail closed verified.
  - `test_project_validation_cleanup_failure_not_ignored`: RED to GREEN. Disk cleanup error raised.
