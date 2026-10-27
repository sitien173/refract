## User Request

Completely remove legacy job-result metadata semantics. Use a strict grouped schema and migrate historical records before removing compatibility. The user approved DESIGN.md and PLAN.md. Execute Phase 1 only.

## Phase

Define the canonical contract and conversion boundary. Do not wire it into live APIs or storage yet.

## Tasks

- task-1: Add strict execution, failure, retry, telemetry, and metadata types with exact serialized key sets from DESIGN.md. Test first.
- task-2: Add explicit projection between existing internal telemetry state and public measurements without changing the accumulator or exposing bookkeeping.
- task-3: Add a pure schema-15 migration converter. Preserve valid normalized telemetry and operational facts, remove obsolete counters and stored tokens, reject invalid recognized data, and never fabricate historical observation times.

## Context

Repository: /home/ngosi/.worktrees/refract/remove-legacy-metadata. Branch: remove-legacy-metadata. Existing isolated worktree. Plan base: refs/plans/remove-legacy-metadata/base. Read docs/plans/remove-legacy-metadata/DESIGN.md and Phase 1 in PLAN.md completely before edits.

JobResult.metadata remains an unrestricted dictionary today. Existing TelemetryData includes version, attribution, and completed_attempts needed for accounting. Its Measurement pre-validator reconstructs dictionaries and may drop extra fields or generate missing timestamps. Canonical types must reject invalid fields before that can bypass strict validation. Reuse current measurement rules without duplicating accounting logic. Preserve all current runtime behavior and schema 15 in this phase. No existing caller should switch to the new contract until Phase 2.

Public metadata roots: execution, failure, retry, telemetry. execution has model and duration_ms. failure is null or has existing failure kind. retry has retryable and next_target, retaining current behavior for context overflow. Public telemetry has completeness and the seven existing normalized measurements only. No version, attribution, completed_attempts, legacy aliases, or duplicate counters appear publicly. A Measurement keeps value, source, quality, observed_at. Null values have unavailable quality. Valued historical measurements without observation time are invalid; migration must not use the current clock.

Migration helper must distinguish historical normalization from canonical runtime validation. Legacy-only records yield unavailable normalized metrics. Existing normalized telemetry wins over conflicting raw counters. Validate recognized historical operational and telemetry fields; do not silently discard invalid values. Known obsolete counters and unknown extension fields are removed deliberately. Return the canonical public representation and separate bounded internal state needed for Phase 2. No database access, no real state-directory access, and no runtime fallback.

## Files

Product and test changes allowed only:
- server/src/refract/result_metadata.py, create
- server/tests/test_result_metadata.py, create
- server/src/refract/telemetry.py, modify only if required
- server/tests/test_telemetry.py, modify only if required

Worker evidence files:
- docs/plans/remove-legacy-metadata/phase-01/notes.md, append task evidence
- docs/plans/remove-legacy-metadata/phase-01/journal.md, append implementation response

Do not edit PLAN.md, DESIGN.md, .handover.md, phase prompt, other code, dependencies, generated assets, Git history, or refs. Secrets and all operator state directories are out of scope.

## Done When

- Exact key sets and strict nested types match DESIGN.md.
- Tests reject aliases, extra fields, booleans-as-counts, negative values, non-finite percentages, invalid quality combinations, invalid enums, and unsupported historical telemetry versions.
- Historical normalized values and provenance remain unchanged. No timestamp is fabricated.
- Internal state is excluded from public projection and preserved separately.
- Existing APIs, result types, persistence, and schema 15 remain unchanged.
- RED evidence names the intended missing behavior, not a mere import failure. Record RED and GREEN commands and outcomes for every task.
- Run from repository root: (cd server && uv run --extra dev python -m pytest -m 'not live')
- Run from repository root: bash plugin/tests/test-session-start.sh
- Run from repository root: bash plugin/tests/test-contracts.sh

## Rules

Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
- TDD: /home/ngosi/projects/refract/plugin/skills/test-driven-development/SKILL.md

No Git commits, staging, resets, restores, or ref writes. Work only in the named worktree. Tests are offline, exclude live probes, and use temporary synthetic data. Keep changes minimal and report every touched path. For ambiguity not answered by design, use refract ask; if unavailable return BLOCKED. Do not implement Phase 2 or later.

## Response Format

Return the ERP # EXTERNAL RESPONSE block with all required sections and one matching status line. Append it under Implementation Response in the phase journal. Coordinator owns Git, handover, review, and final acceptance.
