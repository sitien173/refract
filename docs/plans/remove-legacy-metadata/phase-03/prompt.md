## User Request

The user replied `next` after Phase 2 acceptance and the explicit Phase 3 authorization boundary. Execute Phase 3 only, with fresh verification and independent review, then stop.

## Phase

Remove the backend legacy usage bridge. Legacy result semantics disappear at their production source without reducing normalized telemetry or changing execution outcomes.

## Tasks

1. Replace BackendResult.usage and DriverResult.usage with explicit optional model identity. Delete USAGE_KEYS, _usage_dict, and parsers used only for removed legacy result outputs.
2. Preserve native provider parsing required by normalized collectors across agy, claude, codex, and pi. Cover final-only/non-streaming results, cache accounting, missing telemetry, model fallback, cancellation, and failures with behavioral regressions.
3. Audit production references and classify remaining native keys as collector inputs or migration input, not public compatibility. Remove only imports/helpers newly orphaned by this phase.

## Context

Worktree: /home/ngosi/.worktrees/refract/remove-legacy-metadata
Branch: remove-legacy-metadata.
Read docs/plans/remove-legacy-metadata/DESIGN.md and Phase 3 of PLAN.md before editing. Phases 1 and 2 are accepted; do not regress their strict grouped contract, provenance/timestamps, migration-only conversion, read-time routing, or separated bounded accounting. Phase 2 accepted ref is refs/plans/remove-legacy-metadata/phase-02/impl, with product checkpoint 0d9930c22a24ab0264a0c2aa4d9b1592746f218c and final coordination 769dee32d0a8ab8b70c1b259e019d02d9345fc0f. Baseline: 963 Python tests passed, 15 live deselected, both plugin checks passed.

Execution currently reads only model identity from the old bridge; replace that last dependency with explicit identity. Neither result type may retain usage dictionaries, aliases, mapping shims, or duplicate counters. Native event parsing remains necessary for normalized observations and legacy provider event recognition. Do not delete collectors just because their payload uses input_tokens or other native keys. Preserve all supported measurements and original provenance. Unknown values stay unavailable; model fallback must not invent context capacity.

## Files

Only these product/test paths may change:
- server/src/refract/backends/__init__.py
- server/src/refract/backends/agy.py
- server/src/refract/backends/claude.py
- server/src/refract/backends/codex.py
- server/src/refract/backends/pi.py
- server/src/refract/drivers.py
- server/src/refract/execution.py
- server/tests/test_streaming_backends.py
- server/tests/test_execution.py
- server/tests/test_smoke.py

Append worker evidence only:
- docs/plans/remove-legacy-metadata/phase-03/notes.md
- docs/plans/remove-legacy-metadata/phase-03/journal.md

If another path is required, ask first. Coordinator owns Git, anchors, phase prompt, design, plan, and handover. Separate historical telemetry/retry-policy plans remain out of scope.

## Done When

- Both result types carry explicit optional model identity and no usage dictionary.
- No duplicate legacy result-usage parser remains; necessary normalized collector parsing remains.
- All four adapters preserve normalized context/consumption/cache measurements when available, including final-only/non-streaming paths.
- Missing observations remain unavailable; configured model fallback fabricates no capacity.
- Provider event fixtures remain unchanged unless explicitly representing the removed result shape.
- Transport, event recognition, cancellation, failures, execution/failure/retry outcomes remain unchanged.
- Production references are audited and remaining legacy-field reads classified as schema-15 converter input or necessary provider parsing.
- Record characterization coverage before behavior-preserving refactors and genuine behavioral RED/GREEN for changed behavior. No import-only RED evidence.
- Run all exact checks from repository root, retain logs and final counts:
  - (cd server && uv run --extra dev python -m pytest -m 'not live')
  - bash plugin/tests/test-session-start.sh
  - bash plugin/tests/test-contracts.sh

## Rules

Follow bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
- TDD: /home/ngosi/projects/refract/plugin/skills/test-driven-development/SKILL.md

No Git mutations, real operator database/state access, daemon actions, deployment, live/network probes, or Phase 4 changes. Use only synthetic temporary fixtures. No new dependencies, telemetry collectors, model capacity tables, UI changes, generated assets, or documentation updates. Preserve accepted earlier phases. Do not normalize raw counters outside existing normalized collectors or fabricate timestamps. Append task evidence and ERP without overwriting prior history. Report every touched file. Ask unresolved decisions through refract ask without exposing injected credentials; if unavailable return BLOCKED.

## Response Format

Return the complete ERP # EXTERNAL RESPONSE block and matching status line. Coordinator owns final specification validation and independent review.
