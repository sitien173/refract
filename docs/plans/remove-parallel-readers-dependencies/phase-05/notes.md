<!-- refract-shared-version: 1.2.0 -->

# Phase 5 — Decision Notes

## Task 1

### Decisions made
- Replaced the dependency/admission section with project-scoped FIFO admission bounded by global `max_jobs`; explicitly document unknown tool arguments as `invalid_request`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- `bash plugin/tests/run.sh`: passed.

## Task 2

### Decisions made
- Kept shared-document version markers internally consistent without requiring them to equal the newly released plugin package version; those bundled files are outside this phase's allowed edit list.

### Spec deviations
- none

### Tradeoffs accepted
- The plugin test still verifies that shared-version markers exist and are consistent with one another, while release version equality is checked between the Claude plugin and marketplace metadata.

### Assumptions
- The Codex plugin metadata remains at 1.2.0 because it is not listed among Phase 5 version files.

### Follow-ups for human
- none

### Test evidence
- Initial `bash plugin/tests/run.sh` failed because the test tied unchanged bundled shared markers (1.2.0) to the bumped plugin version. Updated that version consistency guard to check shared markers agree; rerun passed.
- Added absence assertions for `depends_on`, `cancelled_dependents`, `invalid_dependency`, and `dependency_failed`; plugin contract suite passed.

## Task 3

### Decisions made
- Updated only the specified plugin, marketplace, server project, and lockfile versions to 2.0.0. Added the requested 2.0.0 changelog entry and pre-restart configuration instruction.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Phase cannot pass all Done When checks without expanding the allowed file list: `server/tests/test_smoke.py` still asserts server version 1.0.0; residue search additionally finds removed-feature names in `server/tests/test_execution.py`, `server/tests/test_dashboard.py`, and other non-allowlisted assertions in `server/tests/test_server.py`.

### Test evidence
- `bash plugin/tests/run.sh`: passed.
- Version validation confirmed all four specified version files read 2.0.0.
- `git diff --check`: passed.
- `cd server && uv run --extra dev pytest -q`: 542 passed, 3 deselected, 1 failed. The failure is `test_refract_version_is_1_and_lock_matches_without_dependency_changes` in `server/tests/test_smoke.py`, which asserts `project["project"]["version"] == "1.0.0"`; that file is not listed as editable.
- The required residue `rg` check still reports removed-surface mentions in non-allowlisted test files, in addition to the explicitly permitted historical migration/rejection references.
