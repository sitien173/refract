## Original User Request
Complete the OpenMCP admin configuration dashboard. Implement Phase 1 configuration health and revision tracking without changing configuration files.

## Phase
Track configuration health and revisions.

## Tasks
- task-1: Model configuration source revisions and health snapshots.
- task-2: Track global load attempts and last-known-good state.
- task-3: Stamp new jobs with their resolved configuration revision.
- task-4: Migrate existing databases without changing old job or retry behavior.

## Context
OpenMCP currently loads global configuration through `src/openmcp/config.py`, resolves job execution plans through `src/openmcp/runtime.py`, models persisted values in `src/openmcp/models.py`, and stores jobs in SQLite through `src/openmcp/database.py`. Hash exact source file bytes using SHA-256. Failed reloads must preserve the last-known-good catalog while exposing invalid health. New jobs use the revision that produced their immutable execution plan. Retries retain that plan and revision. Existing jobs expose an empty revision.

## Files
- `src/openmcp/config.py`
- `src/openmcp/config_inspection.py`
- `src/openmcp/models.py`
- `src/openmcp/runtime.py`
- `src/openmcp/database.py`
- `tests/test_config.py`
- `tests/test_config_inspection.py`
- `tests/test_runtime.py`
- `tests/test_database.py`

## Done When
- A stable SHA-256 hash of exact global configuration bytes identifies revisions.
- Health reports attempted time, successful time, path, modification time, revision, validity, and latest error.
- Failed reloads preserve the last-known-good catalog and health evidence.
- Daemon availability remains distinct from configuration validity.
- New jobs persist the resolved configuration revision.
- Retries preserve their immutable execution plan and revision.
- Existing jobs expose an empty revision without migration failure.
- Database migration is transactional and idempotent.
- Errors exclude unnecessary configuration content.
- `uv run pytest tests/test_config.py tests/test_config_inspection.py tests/test_runtime.py tests/test_database.py`
- `uv run pytest`
- `uv build`
- `git diff --check`

## Consultation Findings
- Gate migrations by `PRAGMA user_version`; exact legacy column-set checks must not delete newly added columns on reopen.
- Add `config_revision TEXT NOT NULL DEFAULT ''` inside an explicit transaction with the `user_version` update. Avoid `executescript` inside that transaction.
- Read configuration bytes once. Hash those exact bytes, then decode and parse the same buffer. Normalize decode failures into the existing configuration-error contract.
- Missing sources use an empty revision. Store full lowercase SHA-256 values. Treat modification time as display evidence only.
- Failed reloads preserve the last-known-good catalog but still block new submissions. Do not silently route through stale configuration.
- Seed initial global configuration health. Keep project configuration failures separate from global health.
- Keep daemon status and configuration health structurally separate.
- The revision identifies the global configuration source only. The immutable execution-plan snapshot remains authoritative for project overrides.
- Bound stored error text. Store no traceback or configuration values.
- Test reopen preservation, migration rollback, exact CRLF byte hashing, failed reload preservation with blocked submission, and retry immutability after source changes.

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`. Do not add configuration writes, approvals,
rollback, or restart behavior.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
