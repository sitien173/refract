## User Request

Continue the approved target-environments plan to Phase 3. Keep long-running tests in the background. Preserve editor behavior and document the implemented contract. Execute this phase, independently review it, then finalize the three-phase plan.

## Phase

Phase 3: Preserve editor behavior and document the contract.

## Context

Repository: /home/ngosi/.worktrees/refract/taget_configure_env
Branch: taget_configure_env
Read first:
- docs/plans/target-environments/DESIGN.md
- docs/plans/target-environments/PLAN.md, especially Phase 3
- docs/plans/target-environments/phase-02/notes.md

Phases 1 and 2 are complete with independent PASS. Latest full gate: 896 passed, 15 deselected. Configuration supports shared [envs.name], target envs_vars and envs, environment-only project target overlays, interpolation and protected ask variables. New marked execution snapshots persist only target identifiers, resolve current environments at execution, preserve stored policy, and hold in-memory bindings through automatic retry/recovery. Explicit retry and queued restart rebind. Runtime revision context is per-runtime keyed HMAC with project pre/post-load file identity validation and bounded retry. Environment-free historical plans retain legacy behavior.

## Tasks

- task-1: Add global/project editor round-trip regressions. Existing target/profile edits must preserve shared sets, ordered selections, target-local tables, project overlays and comments. Cover inline and ordinary TOML tables. Preserve stale revision rejection and invalid-candidate atomicity. Change production mutation code only when regressions demonstrate a gap.
- task-2: Verify dashboard configuration/job detail/editor read-write/error responses omit environment values and templates using synthetic markers. Keep historical and marked snapshots compatible. Add narrowly necessary allow-list hardening only; no environment editor controls or secret-bearing API fields.
- task-3: Document complete valid global/project TOML examples, exact precedence, interpolation and escapes, reserved REFRACT_ASK_* keys/references, project trust, plaintext configuration, memory-only lifecycle, target removal, restart/explicit retry semantics, legacy snapshots, session revision isolation, and target PATH discovery limitation. Dashboard environment controls and exact restart replay are unsupported. Test README examples through actual loaders.

## Files

Allowed production/test/documentation changes:
- server/src/refract/config_mutation.py
- server/src/refract/dashboard.py
- server/tests/test_config_mutation.py
- server/tests/test_dashboard.py
- server/tests/test_config_inspection.py
- server/tests/test_environment.py
- server/README.md

Worker evidence:
- docs/plans/target-environments/phase-03/notes.md
- docs/plans/target-environments/phase-03/journal.md, append Implementation Response only

Do not modify config.py, runtime.py, execution.py, planning.py, drivers/backends, database schema, dependencies/lockfiles, plan/design/handover, other phases or unrelated plans. Ask before expanding scope. Do not inspect operator configuration or real credentials.

## Done When

- Every Phase 3 acceptance criterion and reviewer checklist in PLAN.md is met.
- Existing target/profile edits preserve declarations and comments, both inline and ordinary TOML tables.
- Stale revision writes and invalid candidate configurations remain rejected without modifying files.
- Dashboard/mutation responses and errors expose no synthetic environment contents or templates.
- Job detail remains compatible with old and marked snapshots.
- README examples load through actual global and project loaders, using placeholders only. Match TOML table ownership carefully.
- Production behavior changes have genuine failing regression evidence before correction. Already-correct preservation/privacy behavior may use passing characterization coverage; do not invent RED or make unnecessary production changes.
- Fresh full gate after tasks: cd server && uv run pytest
- Keep long tests in background; use completion notifications, never polling.
- Record exact RED/GREEN or characterization commands, failure lines and full-suite counts in notes. Return TASK_COMPLETE only with fresh passing evidence.

## Rules

Follow:
- /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- /home/ngosi/projects/refract/plugin/shared/erp.md
- /home/ngosi/projects/refract/plugin/shared/notes-template.md
- /home/ngosi/projects/refract/plugin/shared/journal-template.md

Keep changes minimal. Coordinator owns Git, handover, phase status, validation and independent review. No Git mutations, new dependencies, live provider checks or deployment. Preserve unrelated docs/plans/shared-retry-policies and docs/plans/worker-job-telemetry. Do not add UI controls. For documentation apply /home/ngosi/.pi/agent/skills/stow/SKILL.md and its public-documentation guidance. If blocked, ask through the coordinator channel or return BLOCKED.

## Response Format

Return ERP # EXTERNAL RESPONSE with NEXT: TASK_COMPLETE, BLOCKED, or CONTINUE_CONTEXT, and matching Phase 3 status line.
