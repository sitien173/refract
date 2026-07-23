<!-- ccg-shared-version: 7.3.0 -->

# Phase 1 — Decision Notes

<!--
Worker Notes template. Append one `## Task <M>` block per task. Keep the file;
never overwrite earlier task blocks. Empty sub-sections = `- none`. Every task
gets a block even if all `none`.
-->

## Task 1

### Decisions made
- Bare profile strings now name target ids directly.

### Spec deviations
- none

### Tradeoffs accepted
- Project overlay parameters remain for Phase 2 inheritance work.

### Assumptions
- Target declarations remain TOML array-of-table entries.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Removed-alias tests failed against legacy loading, then passed after route and factory removal.

## Task 2

### Decisions made
- Empty `DaemonConfig.default_profile` is non-meaningful.
- Unknown daemon settings are rejected explicitly.

### Spec deviations
- none

### Tradeoffs accepted
- Existing target field defaults remain unchanged.

### Assumptions
- Missing project config continues resolving to the global catalog.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Strict config tests first had 5 failures, then `tests/test_config.py` passed 14 tests.

## Task 3

### Decisions made
- Writer leaves removed profile sections untouched, so strict validation rejects them.

### Spec deviations
- none

### Tradeoffs accepted
- Legacy documents require manual migration before dashboard writes succeed.

### Assumptions
- Atomic writer validation remains the rejection boundary.

### Follow-ups for human
- none

### Test evidence
- GREEN: Writer regression coverage rejects a document containing a removed profile section; targeted dashboard tests pass.

## Task 4

### Decisions made
- Server loads configuration inside lifespan startup.
- Dashboard starts with an empty default profile.

### Spec deviations
- none

### Tradeoffs accepted
- FastMCP retains loopback host and port until startup configuration is loaded.

### Assumptions
- CLI transport overrides continue applying through FastMCP settings.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Clean-environment server import failed on import-time loading, then passed after startup deferral.
- GREEN: Targeted phase gates passed 78 tests; full suite passed 102 tests with 2 deselected.

## Task 5

### Decisions made
- The CLI owns pre-transport configuration loading.
- Server lifespan reuses preloaded configuration and loads it directly otherwise.
- Preloaded configuration is cleared after transport shutdown.

### Spec deviations
- none

### Tradeoffs accepted
- FastMCP keeps loopback defaults until `serve` applies strict configuration.

### Assumptions
- `cli.main` is the canonical daemon startup path.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Transport regression tests first observed hardcoded host and port, then targeted tests passed 48 tests and the full suite passed 106 tests with 2 deselected.

## Task 6

### Decisions made
- Installation now points to the existing explicit Configuration example.

### Spec deviations
- none

### Tradeoffs accepted
- The configuration example remains in its current README section.

### Assumptions
- Users read the referenced Configuration section before continuing.

### Follow-ups for human
- none

### Test evidence
- GREEN: README inspection shows configuration creation before doctor and serve; full suite passed 106 tests with 2 deselected.

## Task 7

### Decisions made
- Dict payloads accept only the four supported top-level sections.
- Unsupported keys fail before TOML document construction.

### Spec deviations
- none

### Tradeoffs accepted
- Unsupported payloads fail before backups or file replacement.

### Assumptions
- Partial updates continue using any subset of supported sections.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: New dict-payload tests first had 2 failures, then targeted tests passed 41 tests and the full suite passed 108 tests with 2 deselected.
- GREEN: Phase 1 absence scan passed with no matches.

## Task 8

### Decisions made
- Nested `finally` is used for the smallest shutdown correction.

### Spec deviations
- none

### Tradeoffs accepted
- The close exception remains the propagated shutdown error.

### Assumptions
- Clearing both globals is required after every lifespan shutdown attempt.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Focused regression failed with `_DAEMON_CONFIG` still set, then passed after the nested `finally` correction.
- GREEN: `uv run pytest tests/test_server.py` passed 5 tests; `uv run pytest` passed 131 tests with 2 deselected.
- Root cause (bugfix only): `_DAEMON_CONFIG = None` followed `await runtime.close()`, so close failure skipped the assignment.
