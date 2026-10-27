## User Request

Continue the approved target-environments plan to Phase 2. Keep long-running test commands in the background. Integrate global/project shared environments and target-local overrides into real execution without persisting credentials.

## Phase

Phase 2: Bind environments without persisting credentials.

## Tasks

- task-1: Add minimal non-secret execution-plan metadata identifying environment-enabled jobs/targets. Persist no shared/local values or interpolation templates. Keep historical snapshots readable and their execution identities/behavior unchanged.
- task-2: Wire current project environment resolution into the execution boundary. Resolve by stored target id, preserving all snapshotted non-environment target policy. Handle target removal/invalid project configuration before worker launch with sanitized configuration failures.
- task-3: Resolve the binding before session preparation. Keep it stable for automatic retries and session recovery; resolve again for explicit retry and restarted queued jobs. Reuse existing driver/BackendParams.env transport, add daemon ask credentials last, and avoid os.environ mutation or unbounded secret caches.
- task-4: Bind environment-enabled sessions to opaque global/project revision context without public secret-derived fingerprints. Preserve capacity limits and old identities. Cover concurrency, rotation, retries, restart, cancellation, and secret-free persistence using fake backend processes.

## Context

Repository: /home/ngosi/.worktrees/refract/taget_configure_env
Branch: taget_configure_env
Read first:
- docs/plans/target-environments/DESIGN.md
- docs/plans/target-environments/PLAN.md, Phase 2
- docs/plans/target-environments/phase-01/notes.md

Phase 1 provides config.py resolve_target_environment(catalog, target_or_id, inherited=None), returning only resolved configured overrides. Catalog.envs contains shared raw declarations; TargetConfig.envs_vars and envs contain target declarations, excluded from repr. Project loading already merges environments. The resolver is iterative, uses final-namespace precedence, protects ask references, and returns structural errors.

Current architecture:
- runtime.py resolves a project catalog under the mutation lock on submission, serializes execution_plan_data(plan) into the database, and restarts queued records. Explicit retry parses the stored plan.
- planning.py explicitly serializes and parses non-environment TargetConfig fields. It derives target execution keys and next-target tokens. Keep environment values/templates out of these persisted/public surfaces.
- JobRunner in execution.py parses the stored execution plan and invokes TargetExecutor. TargetExecutor selects a target, prepares/reuses a session, obtains capacity, and performs automatic retry/session recovery. This is where an in-memory environment binding must be available before session selection.
- Existing execution passes a per-attempt ask environment to drivers. DriverRegistry.execute passes env into BackendParams. backends/_shell.py copies os.environ then updates supplied env. Reuse this transport; do not duplicate spawning or alter backends.

Lifecycle contract:
- All persisted execution snapshots remain free of environment values and templates. Persist only minimal non-secret metadata sufficient to identify environment-enabled execution. An absent marker means historical no-configured-environment behavior, even if the same target now has environment configuration.
- Current project environment declarations apply before execution, including restarted queued jobs and explicit retries. Never replace stored backend, args, limits, or retry policy with current target policy.
- If a marked target no longer exists in current configuration, fail safely. Do not silently drop environments. Historical environment-free plans need no current target lookup.
- Resolve once per selected target execution, keep stable through its automatic retries/recovery, and release at termination. No persistent or unbounded job-to-secret cache.
- Protect daemon REFRACT_ASK_* credentials. Configuration resolution must not capture inherited ask credentials or override newly issued ones. Inject generated credentials after configured values.
- Configuration failures are not provider failures: do not retry via provider policy or change provider circuit health.
- Environment-enabled sessions separate projects and incompatible configuration revisions using opaque revision context. Do not expose hashes directly derived from resolved secrets. Legacy environment-free identities remain unchanged. Environment differences must not multiply max_concurrency capacity.
- Target PATH affects launched subprocess environment only. CLI discovery and structured-mode probes retain existing daemon-environment behavior.

## Files

Allowed production/test changes:
- server/src/refract/planning.py
- server/src/refract/runtime.py
- server/src/refract/execution.py
- server/tests/test_planning.py
- server/tests/test_runtime.py
- server/tests/test_execution.py
- server/tests/test_environment.py

Worker evidence files:
- docs/plans/target-environments/phase-02/notes.md
- docs/plans/target-environments/phase-02/journal.md, append Implementation Response only

Do not change config.py, config_inspection.py, drivers.py, backends, database schema, dashboard/editor, README, dependencies/lockfiles, plan/design/handover, other phase files, or unrelated plans. If constraints require an additional path, stop and ask before modifying it. Phase 3 owns dashboard/editor/documentation changes.

## Done When

- Every Phase 2 criterion and reviewer checklist in PLAN.md is met.
- Each behavior change has credible RED then GREEN regression evidence, not only import failures.
- Fake backend subprocesses receive inherited/shared/local/project values in correct precedence. Separate targets/projects do not leak values; os.environ is unchanged.
- Tests cover ask protection, automatic retry, recovery, explicit retry, queued restart, configuration rotation, current target removal, preserved snapshot policy, old plan compatibility, legacy identity, session separation, capacity, cancellation, and safe error classification.
- Distinctive synthetic secret values/templates are absent from execution_plan_json, database events, result metadata, and environment-handling logs. No real credentials or operator configuration are read.
- Full command passes fresh after every task: cd server && uv run pytest
- Use background execution for long tests; let completion notifications resume work rather than polling.
- Record exact RED commands/failure lines and GREEN full-suite counts in phase notes. Append ERP in the journal, report every changed file, and return TASK_COMPLETE only with fresh passing evidence.

## Rules

Follow:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md

Keep changes minimal. Reuse existing helpers and threading/worker patterns for blocking config reads. Preserve unrelated retry/telemetry behavior. The project-local test runner is Python 3.12.13 with existing dev extras already installed. No Git mutations, dependency changes, live providers, service deployment, real config reads, or secret output. Coordinator owns Git, phase state, review, and handover. If unclear, ask through the injected coordinator channel; if unavailable, return BLOCKED. Do not redesign or implement Phase 3.

## Response Format

Return ERP # EXTERNAL RESPONSE with NEXT: TASK_COMPLETE, BLOCKED, or CONTINUE_CONTEXT, and matching Phase 2 status line.
