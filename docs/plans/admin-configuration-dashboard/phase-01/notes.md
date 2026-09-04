<!-- ccg-shared-version: 10.2.0 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Configuration source metadata is attached to the loaded `DaemonConfig`; health snapshots are public Pydantic models.
- The full lowercase SHA-256 digest is computed from the one byte buffer used for UTF-8 decoding and TOML parsing.

### Spec deviations
- none

### Tradeoffs accepted
- Modification time is retained as ISO display evidence and is never used as revision identity.

### Assumptions
- A catalog constructed directly by tests or embedding callers is an initially valid catalog even when it has no source path.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Initial inspection tests failed during collection because `config_inspection` did not exist; after implementing source reading, hashing, and normalized decode errors, 3 focused tests passed.

## Task 2

### Decisions made
- Runtime health keeps the last successful timestamp and revision when a reload fails, while recording the failed attempt separately.
- Configuration errors are bounded before health exposure and do not include complete invalid target declarations.

### Spec deviations
- none

### Tradeoffs accepted
- Health is runtime state rather than persisted database state; the catalog remains the authoritative last-known-good object for the daemon lifetime.

### Assumptions
- A reload failure is surfaced to the caller, so stale configuration is never used for a new submission.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Failed-reload and initial-health tests passed after adding health seeding and failure recording; focused configuration/runtime suite passed.

## Task 3

### Decisions made
- The global revision is stamped at job creation, while the serialized immutable execution plan remains authoritative for project overrides and retries.

### Spec deviations
- none

### Tradeoffs accepted
- Direct database callers retain a default empty revision for compatibility.

### Assumptions
- Existing retry transitions do not need to re-resolve configuration because they already retain their plan snapshot.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: New runtime submission and database retry tests passed, including revision preservation and unchanged execution-plan JSON.

## Task 4

### Decisions made
- Database schema version 8 adds `config_revision TEXT NOT NULL DEFAULT ''`.
- Version gates replace exact legacy column-set detection for reopen behavior; the new column migration uses `BEGIN IMMEDIATE` and an explicit commit/rollback.

### Spec deviations
- none

### Tradeoffs accepted
- Older v5/v6/legacy migrations complete their existing normalization first, then apply the small v8 column migration.

### Assumptions
- Databases with a current version are trusted to have the current schema, as in prior migrations.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Existing schema assertions initially reported the expected v8 mismatch; updated migration coverage passed with preserved rows/support data, and the full suite completed at 290 passed, 3 deselected.

## Review Fix — High confidentiality defect

### Decisions made
- Configuration-load errors now use an allow-list sanitizer that preserves safe section and structural diagnostics plus TOML line/column evidence, while removing arbitrary values.
- Runtime health applies the storage bound after sanitization; project configuration errors are sanitized before direct exposure as well.

### Spec deviations
- none

### Tradeoffs accepted
- Detailed validator values are replaced by stable structural messages; profile and workflow identifiers remain only where they are structural diagnostics.

### Assumptions
- File paths and section names are operational metadata and may remain visible; secrets are configuration values and are never retained in health errors.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: A regression test with `SUPER_SECRET_CONFIGURATION_VALUE` initially found the secret in the raised error; after central sanitization, focused tests passed with 67 passed, the full suite passed with 291 passed and 3 deselected, `uv build` succeeded, and `git diff --check` passed.

## Review Fix — Cycle 2 identifier leakage

### Decisions made
- Removed all passthrough of workflow names, profile names, inheritance paths, and parent references from sanitized diagnostics.
- Sanitizer output now permits only fixed structural messages, trusted source paths, and parser line/column numbers.

### Spec deviations
- none

### Tradeoffs accepted
- Detailed profile and workflow diagnostics are intentionally generalized to prevent secret configuration keys from being exposed.

### Assumptions
- Fixed schema labels in generic diagnostics are not configuration-derived values.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Identifier sanitizer tests initially observed workflow, cycle, and parent passthrough; after removal, focused tests passed with 59 tests, runtime regressions covered secret profile/workflow identifiers, full pytest passed with 291 passed and 3 deselected, `uv build` succeeded, and `git diff --check` passed.
