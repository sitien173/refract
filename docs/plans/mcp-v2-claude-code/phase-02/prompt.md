# Phase 2: Dependency persistence, access classes, and reader capacity

## User Request

Complete the confirmed OpenMCP v2 plan. Add the persistence and configuration layer for parallel readers and immutable job dependencies. Keep the current scheduler and v1 MCP surface unchanged in this phase.

## Phase

Persist access classes and dependency links atomically, derive admission from verified enforcement, and accept a startup-bound reader limit.

## Tasks

- task-1: Add the next database migration with a per-job access_mode and immutable job_dependencies links. Migrate every existing job to exclusive with no links. Add atomic job creation with dependency validation and reverse lookup.
- task-2: Derive access_mode from the immutable execution-plan snapshot. Every possible target, including fallbacks, must be configured read-only and use a driver with verified read-only enforcement for parallel_read; all other plans are exclusive.
- task-3: Add daemon.max_project_readers, default 1, as a strictly positive integer. Accept it through configuration mutation and keep it startup-bound.

## Context

- Confirmed requirements: ../DESIGN.md and ../PLAN.md Phase 2.
- Adopted dependency design: /home/ngosi/projects/openmcp/docs/plans/parallel-readers-job-dependencies/DESIGN.md. The v2 design overrides its eventual resource and notification interface, not its persistence or admission rules.
- Reuse Database._migrate, existing create-job and database transaction patterns, the driver registry/enforcement mechanisms, and existing daemon configuration mutation validation. Choose the next schema version from the code, not from this prompt.
- Access mode derives from the saved execution plan, never from the workflow label or current configuration after submission. Admission classes are parallel_read and exclusive.
- Dependency IDs must pre-exist in the same project. Unique immutable backward-only links prevent cycles; do not add a graph-cycle traversal or dependency update API.
- Phase 3 will consume the new persistence/classification APIs. Do not wire scheduler admission, Runtime.submit depends_on, cancellation cascades, or MCP changes now.
- Phase 1 is complete, including verified native waits beyond six minutes. Its behavior must remain intact.
- Live daemon is an editable install running Phase 1 code. No restart is allowed until Phase 7. Do not open or mutate the live database, runtime configuration, session stores, or global daemon home.

## Files

Production and tests, relative to /home/ngosi/projects/openmcp:
- src/openmcp/database.py
- src/openmcp/planning.py
- src/openmcp/drivers.py
- src/openmcp/config.py
- src/openmcp/config_mutation.py
- tests/test_database.py
- tests/test_planning.py
- tests/test_config.py
- tests/test_config_mutation.py

Worker-owned phase artifacts:
- docs/plans/mcp-v2-claude-code/phase-02/notes.md
- docs/plans/mcp-v2-claude-code/phase-02/journal.md

No other edits are allowed. The coordinator owns prompt.md, PLAN.md, DESIGN.md, .handover.md, and all Git operations.

## Done When

- Every pre-existing row migrates to exclusive and no dependency links are fabricated.
- New jobs and all links insert in one transaction. Unknown, duplicate, and other-project dependencies reject creation without leaving a job or link row.
- Both dependency IDs have job foreign keys, each pair is unique, and reverse lookup is indexed.
- No dependency mutation path is introduced.
- Mixed, unverified, unsupported, or otherwise unsafe target plans remain exclusive, including unsafe fallback targets. Advisory prompts never establish enforcement.
- Native capability evidence, not a workflow label, justifies any driver classified as verified. Preserve existing invocation restrictions and do not claim unverified adapters are safe.
- max_project_readers accepts positive integers only and rejects zero, negatives, booleans, floats, and strings. Default is 1; no live resizing or per-project override is added.
- New regression tests fail before the production change and pass afterward. Tests use isolated database/config fixtures and deterministic assertions.
- uv run --extra dev pytest tests/test_database.py tests/test_planning.py tests/test_config.py tests/test_config_mutation.py -q
- uv run --extra dev pytest -q
- git diff --check

## Consultation Findings

The resumed read-only consultation is PASS after the user's approved unchanged retry. No source or test files changed. Verified recommendations:

- Use migration 8 after version 7 and the existing database migration/transaction patterns. Validate every parent and insert the job and links atomically. Keep default migration mode exclusive, both job foreign keys, unique pairs, and indexed reverse lookup. Do not add a dependency mutation API or graph traversal.
- Add the pure static `DriverRegistry.supports_verified_read_only(target: TargetConfig) -> bool`. The verified subset is the existing adapter branch constructing `PiParams`, with `isolated=True`, `read_only=True`, and empty raw `args`. Every other adapter or custom argument case returns false. Do not probe executables, reuse the streaming-capability cache, or modify `_target_args()`.
- Add `derive_access_mode(plan: ExecutionPlan) -> Literal["parallel_read", "exclusive"]` in planning.py. Require a nonempty selection and evaluate every identifier in `plan.selection.targets` via `plan.target()`. Do not truncate fallbacks by attempt count, use workflow labels, or read a later catalog. Existing frozen targets and snapshot serialization already carry the needed fields; no snapshot-format change is necessary.
- Persist the provided derived mode through the new creation API. Phase 3 owns runtime consumer wiring. Keep this phase inside its declared database/planning/configuration APIs and tests.
- Reuse `_positive_int` and the existing mutation validation and pending-restart mechanism for max_project_readers.
- Deterministic classification regressions cover a qualifying target and fallback chain, writable/unisolated/unverified/advisory-only targets, unsafe primary or fallback including beyond attempt count, every nonempty raw-argument case, snapshot round trips/catalog replacement, workflow independence, unknown adapter capability, and an empty programmatic selection. Otherwise-valid custom args stay valid and round-trip unchanged. Keep existing explicit-extension rejection intact.

Read `consult-evidence.md` for exact source/test citations and current documentation. `tests/test_smoke.py` is read-only evidence, not an additional allowed edit. Verified native tool restrictions are not a kernel sandbox claim. Do not add an argument parser, safety-flag matrix, new native flags, or a configuration switch.

## SKILLS

- test-driven-development: /home/ngosi/projects/superpowers-ccg/skills/test-driven-development/SKILL.md
- verifying-before-completion: /home/ngosi/projects/superpowers-ccg/skills/verifying-before-completion/SKILL.md

## Rules

Follow the supplied worker contract, project conventions, and ERP format. This is repository implementation again; prior timer-only instructions applied only to completed Phase 1 probes. Use the minimum code needed and reuse existing patterns. Read existing files before changes. Do not refactor adjacent code or edit outside the file set.

For semantic source questions use mcp__auggie__codebase_retrieval; for exact searches use tgrep; use Read for known paths. Do not use native grep/find/ls/Glob/Grep or generic shell commands to investigate code. If the custom search tools are unavailable, read the explicitly named files directly and report any unresolved search need rather than using another search tool. Fetch current library/CLI API documentation through ctx7 when needed; public web only tvly. Never include credentials in queries.

Do not run OpenMCP, perform any Git write, restart the daemon, alter global configuration, or access secret-bearing files such as global daemon configuration, provider credentials, authentication/session stores, or environment files. Unit and in-process test fixtures only. Maintain this phase's notes and journal, including exact RED failure lines and GREEN counts per task. Stop and return BLOCKED for any genuinely unresolved requirement or necessary out-of-scope edit.

## Response Format

Return the ERP # EXTERNAL RESPONSE block and matching NEXT status. List every changed file and every test command with its actual output. Keep execution identities private.
