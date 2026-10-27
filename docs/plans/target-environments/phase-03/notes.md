<!-- refract-shared-version: 2.0.0 -->

# Phase 3 Decision Notes

## Task 1

### Decisions made
- Added characterization coverage without changing mutation production code: existing TOMLKit document edits preserve environment-bearing target fields, ordered selections, inline local tables, shared tables, and comments; project profile edits preserve environment overlays.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- TOMLKit's existing surgical mutation behavior is the intended editor behavior; these tests cover both global and project mutation paths.

### Follow-ups for human
- none

### Test evidence
- Characterization GREEN: `cd server && uv run pytest tests/test_config_mutation.py -k 'target_edit_preserves_environment or project_profile_edit_preserves_target'` — 2 passed, 60 deselected.
- Existing stale revision and invalid-candidate atomicity tests remain in `tests/test_config_mutation.py`; no production fix was indicated.
- Root cause (bugfix only): none.

## Task 2

### Decisions made
- Tested the dashboard execution-plan allow-list against synthetic marked-snapshot environment target metadata and synthetic secret/template markers. No production allow-list change was needed.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing typed configuration responses and allow-listed job-detail model remain the desired public API; do not add environment fields.

### Follow-ups for human
- none

### Test evidence
- Characterization GREEN: `cd server && uv run pytest tests/test_dashboard.py -k 'marked_environment_metadata or job_detail_redacts_execution_plan'` — 2 passed, 59 deselected. Existing job-detail coverage exercises the historical execution-plan shape.
- Existing dashboard configuration/editor tests cover read/write and sanitized error pathways; the new marked-snapshot test confirms environment declarations and marker metadata are excluded from job detail.
- Root cause (bugfix only): none.

## Task 3

### Decisions made
- Documented the complete environment contract in `server/README.md`, including valid global/project snippets, precedence, interpolation escapes, protected ask names, project trust, plaintext configuration, memory-only binding lifetime, rebinding behavior, target removal, historical snapshots, session isolation, and target `PATH` discovery limitation.
- Added a test extracting the published examples and loading them through `load_config_bytes` and `load_project_config`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The README's target-environment section should be a standalone complete minimal configuration sample rather than modifying the existing operator-specific Quick Start example.

### Follow-ups for human
- none

### Test evidence
- Initial loader execution showed the example omitted required `[daemon].default_profile`; corrected the documentation example. This was a documentation test failure, not production RED evidence.
- GREEN: `cd server && uv run pytest tests/test_environment.py -k readme_environment_examples` — 1 passed, 44 deselected.
- Fresh required full gate: `cd server && uv run pytest` — exit 0; 900 passed, 15 deselected in 219.82s (background log `/tmp/phase3-full-pytest.log`; completion exit recorded in `/tmp/phase3-full-pytest.exit`).
- `git diff --check` passed for the worker-changed files.
- Root cause (bugfix only): none.

## Fix Batch 1

### Decisions made
- Added global and project editor characterization for ordinary `[targets.envs]` tables with comments and ordered selections, complementing existing inline-table coverage.
- Extended env-bearing transaction checks to prove stale-revision and invalid-candidate writes leave the original configuration bytes unchanged.
- Extended dashboard HTTP characterization using real global/project environment-bearing TOML, exact synthetic value/template markers, read endpoints, successful unrelated writes, stale and invalid write errors, and historical and marked job snapshots. Confirmed disk configuration retains its environment declarations after editor writes.
- No production fix was warranted: the HTTP and mutation tests confirmed existing public models and safe execution-plan allow-lists omit environment declarations.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing target/profile mutation routes are the intended editor write surfaces; raw TOML source is not returned by those APIs.

### Follow-ups for human
- none

### Test evidence
- Characterization GREEN: `cd server && uv run pytest tests/test_config_mutation.py -k 'ordinary_environment_tables_and_stale_candidate or preserves_ordinary_target_environment_table'` — 2 passed, 62 deselected.
- Characterization GREEN: `cd server && uv run pytest tests/test_dashboard.py -k environment_markers_stay_private_across_dashboard_http_surfaces` — 1 passed, 61 deselected. Exercises configuration overview/settings, target and profile editor reads, project detail/override reads, global target write success/stale/invalid errors, project override write success/stale error, and historical/marked job detail. Exact global/project values and templates were absent from responses; raw config retained marker declarations.
- Fresh full gate: `cd server && uv run pytest` — exit 0; 903 passed, 15 deselected in 190.58s (background log `/tmp/phase3-fix-batch1-pytest.log`; completion exit recorded in `/tmp/phase3-fix-batch1-pytest.exit`).
- `git diff --check` passed for the batch-changed files.
- Root cause (bugfix only): none; all changes are characterization coverage.
