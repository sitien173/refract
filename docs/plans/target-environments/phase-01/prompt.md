## User Request

Implement Phase 1 of the approved target-environments plan. Support shared named environment sets and target-local environment declarations in both global and project TOML configuration. This phase validates and resolves declarations only; execution integration belongs to Phase 2.

## Phase

Phase 1: Validate and resolve environment declarations.

## Tasks

- task-1: Add default-empty shared-set catalog and target envs_vars/envs fields. Validate global mappings, ordered selections, string keys and values, unknown selected groups, and valid empty values. Retain declarations for project merging; no shared mutable defaults.
- task-2: Support project shared-set merging and environment-only [[targets]] overlays. Require existing target ids; reject duplicate overrides and non-environment fields. Explicit envs_vars replaces inherited selection, including []; local mappings merge by key. Project-only sets are selectable by project overrides. Do not mutate base/global or other project catalogs. Preserve unrelated target policy and profiles.
- task-3: Add a small iterative environment resolver in config.py. Merge inherited environment, selected sets in order, and local keys; resolve configured templates against that final namespace. Support forward references, missing-reference errors, cycle errors, $$ escaping, and literal inherited-only values. Long valid reference chains must not hit Python recursion limits. Return only resolved configured overrides for existing downstream environment transport; never mutate os.environ. No execution integration in this phase.
- task-4: Add structural sanitized diagnostics and exhaustive regression coverage for declarations, overlays, interpolation, invalid environment keys/values, malformed references, and protected ask names. Keep raw declarations out of dataclass reprs. Do not leak secret markers, templates, or arbitrary identifiers in errors.

## Context

Repository: /home/ngosi/.worktrees/refract/taget_configure_env
Branch: taget_configure_env
Read the approved design and Phase 1 plan before changing files:
- docs/plans/target-environments/DESIGN.md
- docs/plans/target-environments/PLAN.md

config.py uses frozen TargetConfig/DaemonConfig dataclasses, strict global section validation, _targets, and load_project_config. Project loading currently overlays profiles. config_inspection.py allow-lists safe structural diagnostics through sanitize_config_error and ConfigurationLoadError. Preserve existing conventions, API defaults, profiles, retries, and source revision metadata.

Exact contract:
- [envs.name] is a string mapping; target envs_vars is a list of shared-set names; target envs is a table, not an array.
- Merge project shared sets by set name/key before applying target precedence. Global targets may only select global sets. Project overrides may select project-only sets.
- Merge project target-local keys over global target-local keys. These still override all selected shared sets, including project shared keys.
- Omitted project envs_vars inherits; an explicit [] clears shared selection. Empty local tables do not delete inherited keys.
- Structural validation occurs on load; interpolation occurs after project merging only when the resolver is called. Unselected sets never contribute interpolation dependencies.
- ${NAME} resolves against the final namespace. A configured self-reference is a cycle even if the inherited environment contained that key. Inherited-only values are returned literally, never recursively expanded.
- $$ becomes literal $. $${NAME} becomes literal ${NAME}. Bare $NAME is literal. Reject empty or unterminated ${...} references safely. No shell expansion or command execution.
- Reject empty keys, '=' in keys, NUL in keys/values, non-string values, configured REFRACT_ASK_* keys, and references to REFRACT_ASK_* names. Escaped literal strings are not references. Preserve valid empty string values.
- Sanitize diagnostics consistently, including target ids, group names, reference names, and templates. Use synthetic data only. Public runtime plans and UI controls are out of scope.

## Files

Production/test changes allowed only:
- server/src/refract/config.py
- server/src/refract/config_inspection.py
- server/tests/test_config.py
- server/tests/test_config_inspection.py
- server/tests/test_environment.py, new

Worker evidence files:
- docs/plans/target-environments/phase-01/notes.md
- docs/plans/target-environments/phase-01/journal.md, append Implementation Response only

Do not change PLAN.md, DESIGN.md, .handover.md, other plans, dependency manifests/lockfiles, runtime.py, execution.py, planning.py, backends, dashboard, or README.

## Done When

- Every Phase 1 acceptance criterion and reviewer checklist in PLAN.md is met.
- Each behavior change has credible RED then GREEN evidence. RED must assert intended missing behavior, not fail only on an import or absent helper.
- Focused tests cover precedence, multiple selected sets, projects and targets in isolation, local overrides, [] replacement, empty values, forward/deep references, literal inherited values, escaping, unknown/malformed references, direct and indirect cycles, protected ask names, invalid types, invalid keys and NUL, and no os.environ mutation.
- Existing catalog reconstruction keeps declarations and preserves source revision metadata.
- Reprs and errors do not contain synthetic secret values or templates.
- Run from repository root after each task: cd server && uv run pytest
- Record exact commands, fresh counts, and RED failure lines in notes.md.

## Rules

Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md

Read relevant code before editing. Reuse existing helpers. Keep changes surgical. Use configured project-local test tooling. Coordinator installed existing dev extras; do not change dependencies. Do not read operator runtime configuration, print environment secrets, run live providers, deploy services, commit, reset, stash, or change Git refs. Coordinator owns Git. If scope cannot hold, return BLOCKED with exact questions. Do not redesign or implement later phases. Record all changed paths, including evidence files, in ERP.

## Response Format

Return the ERP # EXTERNAL RESPONSE block with NEXT: TASK_COMPLETE, BLOCKED, or CONTINUE_CONTEXT, and the matching Phase 1 status line.
