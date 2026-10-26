## User Request
Implement the approved worker-job-telemetry plan. Expose live worker context snapshots and final per-job token totals for Agy, Codex, Claude Code, and Pi, without replacing transports.

## Phase
Phase 2: Correct usage collection across existing backend streams. Each adapter emits trustworthy live observations and final normalized job consumption.

## Read First
- Design: /home/ngosi/projects/refract/docs/plans/worker-job-telemetry/DESIGN.md
- Plan: /home/ngosi/projects/refract/docs/plans/worker-job-telemetry/PLAN.md (read "Shared Contract and Boundaries" and "Phase 2" fully)
- Phase 1 telemetry contract: server/src/refract/telemetry.py

## Tasks
- task-1: Add sanitized multi-response regression fixtures and failing cache-accounting tests. Extend backend result propagation only as required for normalized telemetry. Use one authoritative usage observation per response or step.
- task-2: Integrate Claude and Pi collectors. Claude reconciles assistant observations with final aggregate usage and observed model capacity. Pi aggregates authoritative completed assistant messages, not repeated `turn_end.message` or streaming snapshots. Include separately reported summary usage where available without counting it twice.
- task-3: Integrate Codex and Agy collectors. Codex reconciles `turn.completed.usage`; Agy reconciles completed step usage with terminal counters. Establish counter scope from fixtures or documented evidence before subtracting baselines.
- task-4: Add live context derivation only where response-local retained components are established. Handle compaction, model changes, unavailable capacities, malformed data, and missing final events. Ensure no-emitter execution still returns normalized final telemetry.

## Context
- Phase 1 built the shared telemetry contract in `server/src/refract/telemetry.py`: `TelemetryMeasurement`, `TelemetryData`, `TelemetryAccumulator`, `merge_telemetry`, `prepare_telemetry_for_retry`.
- The accumulator validates observations, reconciles duplicates, tracks per-measurement availability and provenance, and enforces ordering.
- Backend adapters must emit `telemetry.updated` observations through the accumulator. Execution routes these before transcript recording.
- Legacy metadata keys keep backend-native meaning. New consumers use `telemetry`.
- Cache normalization rules per backend are in the design: Claude and Pi expose separate cache components; Codex cached input is already included in input; Agy follows sanitized evidence.

## Files
- Modify: `server/src/refract/backends/__init__.py`
- Modify: `server/src/refract/backends/_shell.py`
- Modify: `server/src/refract/backends/agy.py`
- Modify: `server/src/refract/backends/claude.py`
- Modify: `server/src/refract/backends/codex.py`
- Modify: `server/src/refract/backends/pi.py`
- Modify: `server/src/refract/telemetry.py`
- Modify: `server/tests/test_telemetry.py`
- Modify: `server/tests/test_streaming_backends.py`
- Modify: `server/tests/test_execution.py`
- Modify: `server/tests/test_processes.py`
- Modify: `server/tests/fixtures/usage/agy.jsonl`
- Modify: `server/tests/fixtures/usage/claude.jsonl`
- Modify: `server/tests/fixtures/usage/codex.jsonl`
- Modify: `server/tests/fixtures/usage/pi.jsonl`
- Write: `docs/plans/worker-job-telemetry/phase-02/notes.md`

## Done When
- Multi-response Pi consumption exceeds the final message alone.
- Pi lifecycle duplicates do not double-count response usage.
- Claude cache reads and writes enter normalized input once.
- Claude capacity is not selected arbitrarily from unrelated model usage.
- Codex cached input is not added twice.
- Agy final totals do not duplicate prior step consumption.
- Repeated cumulative snapshots are replacements, not additions.
- Resumed history is not counted as prior job consumption.
- Missing baselines produce explicit incomplete totals.
- At least one observation is persisted before completion for a synthetic multi-response stream.
- Context snapshots can shrink after compaction without reducing consumption totals.
- Parsing failures leave text, tool events, and backend outcomes unchanged.
- Legacy extraction remains backward-compatible where already supported.
- `cd server && uv run pytest` passes.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md

- Write regression tests before production changes.
- Do not commit, stash, reset, or run any Git write command. Coordinator owns Git.
- Do not edit PLAN.md, DESIGN.md, .handover.md, or journal.md.
- Do not modify credentials or global CLI configuration. Do not launch live model requests.
- Do not replace execution transports with RPC.
- Touch only the listed files. Report any needed extra path as a clarification.
- Never put raw payloads, session paths, prompts, or credentials in telemetry.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
