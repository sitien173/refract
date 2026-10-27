## User Request
Continue the approved shared-retry-policies plan on main. Execute Phase 3: dashboard round trips and operator documentation. Phases 1 and 2 are accepted. The Phase 2 historical RED evidence waiver does not apply to Phase 3.

## Phase
3: Dashboard round trips and operator documentation

## Tasks
- task-1: Expose optional retryPolicy references through target read/mutation models and TOML serialization, preserving shared definitions, comments, validation and conflict protections.
- task-2: Add a simple named-reference input to the existing target editor and preserve it through load, edit, submission, clear, rejection and conflict reload.
- task-3: Document shared policy examples, retry counts, defaults, OR matching, exclusions, observability, token costs and unchanged manual fallback; build dashboard assets through the existing build only.

## Context
Read docs/plans/shared-retry-policies/PLAN.md and DESIGN.md. Phase 1 implemented global retryPolicies, target retry_policy references, immutable execution snapshots and stable target identity. Phase 2 implemented bounded same-target execution, conservative replay and cumulative telemetry. Do not alter these execution semantics.
Global policy definitions remain TOML-managed; no policy-management screen. Preserve global retryPolicies during target create/update/delete. An empty editor field must clear the reference without creating a dangling empty policy reference. Inspect existing optional-field conventions and reuse them.
Current accepted phase-02 impl ref points to ad5d84c. Repository was clean at Phase 3 preparation. No active project job. Leave worker-job-telemetry plan and existing product changes untouched.
Existing web build script is vite build. vite.config.js writes ../src/refract/dashboard_static. Those generated assets are tracked and may change only through npm run build.

## Files
Modify only:
- server/src/refract/models.py
- server/src/refract/config_mutation.py
- server/tests/test_config_mutation.py
- server/tests/test_mcp_schema_contract.py
- server/web/src/components/TargetEditor.jsx
- server/web/src/components/ConfigEditorSafety.test.jsx
- server/web/src/screens/Targets.test.jsx
- server/README.md
Generated output only, never hand-edit:
- server/src/refract/dashboard_static/**
Worker coordination output only:
- docs/plans/shared-retry-policies/phase-03/notes.md
- docs/plans/shared-retry-policies/phase-03/journal.md
If other source files are required, ask before editing.

## Done When
- Existing targets without references remain editable.
- A valid reference survives API and dashboard round trips.
- Clearing the reference disables automatic retries.
- Unknown names fail without mutating configuration or discarding drafts.
- Editing unrelated target fields preserves retryPolicy and shared retryPolicies tables.
- Creating or deleting a target does not delete shared policies.
- Conflict reload preserves the freshly loaded reference.
- Public identifiers retryPolicies, retryPolicy and retryAttempt are consistent.
- Documentation explains retryAttempt counts additional attempts, defaults to zero, and retryAttempt=9 permits ten policy attempts. Context recovery has separate internal bounds; manual retries receive fresh budgets.
- Exact codes OR case-insensitive substrings match normalized transient failures only; fatal/cancelled/context-overflow/replay-blocked and unknown replay safety are excluded.
- Explain sequential attempt logs/transcripts, cumulative consumption and costs, no automatic target switching and unchanged manual fallback behavior. Do not promise backend-specific codes.
- No new policy management screen, dependencies, unrelated UI changes or handwritten generated assets.
- Test-first for EACH new behavior: record real failing assertion before implementation and subsequent GREEN. Characterize before behavior-preserving refactors. Do not label GREEN-only runs RED.
- cd server && uv run --extra dev pytest tests/test_config_mutation.py tests/test_mcp_schema_contract.py
- cd server/web && npm test -- src/components/ConfigEditorSafety.test.jsx src/screens/Targets.test.jsx
- cd server && uv run --extra dev pytest
- cd server/web && npm test
- cd server/web && npm run build
- git diff --check

## Rules
Follow bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
Use existing code patterns and minimal changes. Preserve protected identifiers and unrelated formatting. Read existing files before editing. For library-specific uncertainty, fetch current docs using ctx7 per repository instructions, never invent APIs.
No Git operations, dependencies, migrations, live backend probes, daemon restarts, execution/driver edits, earlier-phase edits or telemetry-plan changes. Coordinator owns PLAN.md, DESIGN.md, .handover.md, prompt and Git. Ask via refract ask if scope/design prevents completion.

## Response Format
Return full ERP # EXTERNAL RESPONSE with every touched path, honest RED/GREEN evidence and matching status line.
