## User Request
Complete approved target-context-window plan. Work in place.

## Phase
1: Preserve configured capacity throughout target configuration.

## Tasks
- task-1: Test-first strict optional positive integer contextWindow parsing and editor models.
- task-2: Update target projections and safe preserve/clear mutation round trips.
- task-3: Persist context_window in execution-plan targets without changing session identity.
- task-4: Preserve environment-bound session revision for capacity-only edits while retaining real environment-change invalidation.

## Context
Read /home/ngosi/projects/refract/docs/plans/target-context-window/DESIGN.md and PLAN.md. Implement Phase 1 only. Public TOML/API spelling contextWindow, internal TargetConfig.context_window. Existing retryPolicy patterns show optional editor update semantics. planning.py separates target serialization from target identity. Missing values remain compatible. No telemetry calculation or UI changes in this phase.

## Files
- server/src/refract/config.py
- server/src/refract/models.py
- server/src/refract/config_mutation.py
- server/src/refract/dashboard.py
- server/src/refract/planning.py
- server/src/refract/runtime.py
- server/tests/test_runtime.py
- server/tests/test_config.py
- server/tests/test_config_mutation.py
- server/tests/test_dashboard.py
- server/tests/test_planning.py
- docs/plans/target-context-window/phase-01/notes.md
- docs/plans/target-context-window/phase-01/journal.md

## Done When
- All Phase 1 acceptance criteria and reviewer checks in PLAN.md hold.
- contextWindow accepts positive integers; rejects boolean/string/float/zero/negative.
- Omitted editor update preserves configured capacity; explicit null removes TOML key.
- Public target create/list/read/update/runtime inspection retains setting.
- Persisted execution plans retain capacity; old plans load without changing existing identity.
- Changing capacity alone never changes target_execution_key or session identity.
- Preserve environment restrictions, retry policy, unrelated TOML and secret isolation.
- From /home/ngosi/projects/refract: cd server && uv run pytest -q
- Record RED then GREEN for each behavior in notes. Run full verification after each task.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
Do not commit, stash, reset, or mutate Git. Coordinator owns Git.
Do not edit PLAN.md, DESIGN.md, .handover.md, or any other phase.
Keep docs/plans/worker-job-telemetry untouched.
Secret-bearing runtime configuration, .env files, credentials, and real environment values are out of scope.
No dependencies, backend CLI changes, live probes, or adjacent refactors.
If another file is required, ask the coordinator before touching it.

## Response Format
Return the ERP # EXTERNAL RESPONSE block and matching status line.
