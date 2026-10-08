<!-- ccg-shared-version: 11.0.6 -->

# Phase 2 Decision Notes

## Task 1

### Decisions made
- Added schema migration 12 after schema 11. Fresh and migrated jobs default to `exclusive`; migration fabricates no dependency links.
- Added `job_dependencies` with both job foreign keys, a unique composite primary key, and a reverse-lookup index on `dependency_job_id`.
- Added `create_job_with_dependencies`, which validates unique existing same-project parents and inserts the job, links, and queued event in one transaction. Added forward and reverse lookup methods only; no update/mutation API.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED: `uv run --extra dev pytest tests/test_database.py -q -k 'v11_migrates_existing_jobs_as_exclusive or create_job_with_dependencies'` -> 2 failed, 23 deselected. Migration assertion failed with `assert 11 == 12`; dependency API regression failed with `AttributeError: 'Database' object has no attribute 'create_job_with_dependencies'`.
- GREEN: same focused command -> 2 passed, 23 deselected.
- GREEN module: `uv run --extra dev pytest tests/test_database.py -q` -> 25 passed. Coverage includes v11 migration defaults, invalid dependency rollback, successful link lookups, constraints, and injected link-insert rollback.

## Task 2

### Decisions made
- Added pure static `DriverRegistry.supports_verified_read_only`; it returns true only for isolated, read-only native Pi targets with no raw args. It performs no probing and does not alter invocation behavior.
- Added `derive_access_mode` over every selected target in the immutable plan snapshot. Empty, missing, mixed, unsafe, or unverified selection cases remain `exclusive`; workflow labels and `max_attempts` do not establish safety.
- Preserved valid custom target arguments and snapshot serialization unchanged.

### Spec deviations
- none

### Tradeoffs accepted
- The verified subset is intentionally conservative; no filesystem-wide sandbox guarantee is claimed.

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED: `uv run --extra dev pytest tests/test_planning.py -q -k 'verified_read_only or access_mode'` -> 6 failed, 11 deselected. Expected missing capability failed with `AttributeError: type object 'DriverRegistry' has no attribute 'supports_verified_read_only'`; classification regressions failed to import missing `derive_access_mode`.
- GREEN: `uv run --extra dev pytest tests/test_planning.py -q -k 'verified_read_only or access_mode or empty_programmatic_selection'` -> 7 passed, 10 deselected; the expanded classification cases also passed in the final 184-test phase suite.
- Final planning coverage includes safe and unsafe primary/fallback chains (including beyond `max_attempts`), all workflows, unsupported/advisory/unisolated targets, raw custom arguments, snapshot round trips, catalog replacement, and empty programmatic selection.

## Task 3

### Decisions made
- Added immutable `DaemonConfig.max_project_readers`, default 1, parsed through the existing `_positive_int` validator. Configuration mutation continues to validate candidate TOML through the same loader; the startup `config` object is not changed by a candidate publication.
- Did not add a live-resizing or per-project override API; scheduler/runtime consumption remains Phase 3.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED: `uv run --extra dev pytest tests/test_config.py tests/test_config_mutation.py -q -k 'max_project_readers'` -> 7 failed, 132 deselected. The valid setting was rejected as `Unsupported daemon settings`; default access failed with `AttributeError: 'DaemonConfig' object has no attribute 'max_project_readers'`; invalid-value cases did not reach positive-integer validation.
- GREEN: same focused command -> 7 passed, 132 deselected. Coverage includes default, positive value, zero, negative, bool, float, string, and global mutation acceptance/rejection without committing invalid content.
- Final config and mutation module checks passed as part of the 184-test phase suite.

## Review Fix Cycle 1

### Decisions made
- Explicitly execute `BEGIN IMMEDIATE` before dependency parent validation. The connection context then commits or rolls back validation, job row, all links, and queued event together.
- S2 was an evidence gap, not a behavior defect: the existing conservative classifier and snapshot parser already accept valid custom `args`, round-trip them unchanged, and classify any nonempty raw args as `exclusive`. Added the missing native argument regressions without changing production behavior.
- Confirmed exact Pi CLI spellings using installed `pi --help`: `--export <file>`, command `install <source> [-l]`, and `--tools, -t <tools>`. No new flags or parser behavior added.

### Test evidence
- S1 RED: `uv run --extra dev pytest tests/test_database.py -q -k 'create_job_with_dependencies_is_atomic_and_supports_reverse_lookup'` -> 1 failed, 24 deselected. The new trace assertion failed at `assert parent_read_transactions == [True, True]`; actual state was `[False, False]` for the parent SELECTs.
- S1 GREEN: same command -> 1 passed, 24 deselected. The test also verifies rollback after a valid first parent followed by a missing parent, and after an injected link insert failure.
- S2 initial characterization (no production change): `uv run --extra dev pytest tests/test_planning.py -q -k 'pi_eager_write_and_raw_tool_args'` -> 3 passed, 20 deselected. The accepted native arguments round-tripped and classified exclusive on the existing implementation; this confirmed the gap was missing coverage, not faulty behavior.
- Final phase suite: `uv run --extra dev pytest tests/test_database.py tests/test_planning.py tests/test_config.py tests/test_config_mutation.py -q` -> 187 passed in 2.31s.
- Full suite: `uv run --extra dev pytest -q` -> 503 passed, 3 deselected in 29.74s.
- `git diff --check` -> exit 0, no output.
