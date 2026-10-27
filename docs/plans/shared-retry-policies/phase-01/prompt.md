## User Request
Complete shared-retry-policies on main. Execute Phase 1 only in this job. User waived waiting for telemetry plan completion. Leave that plan and its existing commits untouched.

## Phase
1: Validated policies and durable execution snapshots

## Tasks
- task-1: Add immutable retry policy data, strict global parsing and target references; preserve registry through project overlays.
- task-2: Resolve shared policy values into immutable execution snapshots. Round-trip new snapshots and read legacy snapshots without live configuration.
- task-3: Preserve exact pre-change target execution keys and sessions across policy-only changes. Sanitize diagnostics.

## Context
Read docs/plans/shared-retry-policies/PLAN.md and DESIGN.md. Consultation 556ea624-0f44-4357-a0af-c75eb8e1b03e identified _target_data/asdict identity coupling and explicit DaemonConfig reconstruction in project overlays. Preserve the exact historical identity payload with a literal pre-change key fixture, not just comparing newly computed keys. New retry snapshot data must fail closed when malformed. Do not implement retry execution or dashboard changes here.
Baseline at ef9f219 passed: phase checks 116; execution group 176; mutation/schema 64; focused web 28; full server 728 with 15 live deselections; full web 242; dashboard build exit 0. No product changes existed before this job.

## Files
Modify only:
- server/src/refract/config.py
- server/src/refract/planning.py
- server/src/refract/config_inspection.py
- server/tests/test_config.py
- server/tests/test_planning.py
- server/tests/test_config_inspection.py
- server/tests/test_runtime.py
Coordination output only:
- docs/plans/shared-retry-policies/phase-01/notes.md
- docs/plans/shared-retry-policies/phase-01/journal.md

## Done When
- Two targets can reference one global retryPolicies policy via retryPolicy.
- Missing policy sections/references preserve no-retry behavior.
- retryAttempt defaults to zero and counts additional attempts; reject negative, boolean, fractional and string counts.
- errorCodes/errorPatterns default to empty lists; entries must be nonempty strings; empty lists are valid.
- Unknown policy fields, malformed lists/declarations, dangling references, and target-local retry/retryAttempt declarations are rejected.
- Project overlays retain global policies and reject project-local policies.
- Old execution-plan JSON remains readable with retries disabled.
- Resolved immutable snapshots survive later policy edits/deletion without live lookup.
- New malformed persisted retry data is rejected.
- Retry-only configuration changes preserve exact historical execution keys and existing sessions.
- Configuration diagnostics expose no operator-provided patterns or arbitrary declaration/field contents.
- Tests cover all criteria and all remain green.
- `cd server && uv run --extra dev pytest tests/test_config.py tests/test_planning.py tests/test_config_inspection.py tests/test_runtime.py`

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
Use test-first for new behavior. Record actual RED failure lines and GREEN outputs in notes.md per task. Establish passing characterization before identity refactoring. Keep edits minimal. Do not edit PLAN.md, DESIGN.md, .handover.md, telemetry plan, Git state, execution.py or dashboard. No live probes or daemon restarts. No new dependencies. Ask via refract ask for unresolved design/scope questions; do not silently expand scope.

## Response Format
Return the ERP # EXTERNAL RESPONSE block and matching status line.
