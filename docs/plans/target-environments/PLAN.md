# Target Environments Implementation Plan

**Design:** `docs/plans/target-environments/DESIGN.md`, approved 2026-10-27.
**Scope:** Implementation approved. Execute one phase per invocation.
**Base:** `refs/plans/target-environments/base`
**Base commit:** `fbbf0759e7e041c9273a48bd889b7d42a51eef7c`
**Commit:** `feat(config): support shared and target-scoped environments`
**Tracking:** `tracked`

## Outcome

Support `[envs.<name>]`, target `envs_vars`, and target-local `envs` in global and project configuration. Resolve interpolation without shell execution. Keep environment values out of durable job records and dashboard responses. Preserve existing configuration and execution behavior when environments are absent.

The confirmed design owns syntax, precedence, project overlays, interpolation, error behavior, and restart semantics. Read it before every phase.

## Route

- Sequence: implement -> review, separately for each phase.
- Implement Profile: selected through execution-time task guidance.
- Review Profile: selected through execution-time task guidance.
- Reason: configuration, execution, and credential boundaries cross components.
- Done When: phase acceptance criteria, fresh verification, specification review, and independent quality review pass.

No model or profile is pinned by this plan. Planning consultation failed without useful advice. Execution still requires independent review.

## Baseline

Baseline verification passed against the base revision on 2026-10-27:

```sh
cd server && uv run pytest
```

Result: exit 0; 810 passed, 15 deselected, one dependency deprecation warning; 159.44 seconds. Background task: `be63c811c`.

Execution preparation resolved the interpreter limitation without changing dependencies or source. Ran `uv sync --extra dev`, then confirmed project-local Python 3.12.13 and pytest under `server/.venv/`. At `ec77371b81a702cc5720b842a27bbef0645794c5`, whose production tree matches the plan base, `cd server && uv run pytest` passed: exit 0, 810 passed, 15 deselected, 174.80 seconds, task `bf3ec62af`. Subsequent phase checks use this project-local runner.

The default pytest configuration excludes live provider tests. The same existing command is the verification gate for every phase; new tests are collected automatically. No provider credentials or daemon restart are required.

If baseline failures occur, stop before Phase 1. Record exact failures and obtain approval for a bounded baseline-repair phase rather than silently expanding feature scope. Environment setup problems are not passing verification.

## Execution Rules

1. Reconcile live project jobs and attached branch before execution.
2. Preserve unrelated retry-policy and telemetry plans and source changes.
3. Use one implementation job, then one independent review per phase.
4. Apply test-driven development. Observe a regression fail before changing production behavior, then verify it passes.
5. Coordinator owns phase files, anchors, validation, and Git checkpoints.
6. Do not inspect operator runtime configuration or use real credentials. Use synthetic markers only.
7. Do not add dependencies or new dashboard controls.
8. Preserve existing backend transport. Change backend code only after approved scope expansion if tests expose an unavoidable gap.

### Phase 1: Validate and resolve environment declarations

**Task Guide Input:** Implement the approved global and project environment configuration contract. Support reusable string mappings, ordered selections, target-local mappings, environment-only project target overrides, and deterministic interpolation. Preserve global catalog immutability and sanitized diagnostics. Use synthetic tests; no execution integration or dashboard controls.

**Goal:** Produce correct independent environment bindings from validated configuration.

**Files:**
- Modify: `server/src/refract/config.py`
- Modify: `server/src/refract/config_inspection.py`
- Modify: `server/tests/test_config.py`
- Modify: `server/tests/test_config_inspection.py`
- Create: `server/tests/test_environment.py`

**Tasks:**
1. Add default-empty environment declarations to existing catalog and target models. Parse global shared sets and per-target selections and mappings. Preserve raw declarations for later project merging and avoid mutable shared defaults.
2. Extend project loading with shared-set merging and environment-only `[[targets]]` overlays. Replace explicit selections, merge local keys, and retain all unrelated target policy. Validate duplicate entries and unknown identifiers without mutating the base catalog.
3. Add a bounded environment resolver in `config.py`. Merge inherited variables, ordered shared sets, and local keys before resolving `${NAME}`. Support `$$` escaping, forward references, and literal inherited-only values. Detect cycles and missing references without shell evaluation or recursive-depth crashes on long valid chains.
4. Add structural diagnostics and regression coverage. Validate string types, keys, NUL bytes, malformed references, unknown selections, and protected `REFRACT_ASK_*` keys and references. Interpolation occurs only after effective project merging, not prematurely during global load.

**Acceptance Criteria:**
- Existing configurations load with empty defaults.
- Shared sets merge in selection order; target-local keys win.
- Project shared keys override matching global shared keys.
- Project selections replace inherited selections, including `[]`.
- Project local keys merge over global local keys.
- Project-only sets can be selected by project target overrides.
- Unsupported project target policy, duplicate target overrides, unknown target ids, and unknown selected sets fail safely.
- Empty string values survive. Invalid values are not coerced.
- `${NAME}`, `$${NAME}`, `$$`, bare `$NAME`, missing variables, malformed references, direct self-reference, and multi-variable cycles match the design.
- Unselected sets do not affect values or interpolation.
- Two project catalogs and the global catalog remain independent.
- Errors contain neither synthetic secret values nor templates.

**Reviewer Checklist:**
- Confirm shared-set merging happens before target-local precedence.
- Confirm declaration order cannot change interpolation results.
- Confirm inherited-only values are never treated as templates.
- Confirm all catalog reconstruction paths preserve declarations.
- Check errors, object representations, and logs for accidental disclosure.
- Confirm no writes to `os.environ` and no new dependencies.

**Verification Checks:**
- `cd server && uv run pytest`

### Phase 2: Bind environments without persisting credentials

**Task Guide Input:** Integrate Phase 1 resolution into existing durable job execution. Keep target policy snapshots immutable while resolving current project environments before target launch. Support restart, explicit retry, automatic retry, session recovery, and ask credential protection. Persist no environment contents or templates and preserve historical jobs.

**Goal:** Execute every target with its own safe in-memory environment binding.

**Files:**
- Modify: `server/src/refract/planning.py`
- Modify: `server/src/refract/runtime.py`
- Modify: `server/src/refract/execution.py`
- Modify: `server/tests/test_planning.py`
- Modify: `server/tests/test_runtime.py`
- Modify: `server/tests/test_execution.py`
- Modify: `server/tests/test_environment.py`

**Tasks:**
1. Add minimal non-secret metadata identifying new environment-enabled snapshots. Exclude environment values and templates from `execution_plan_data`. Parse historical snapshots with unchanged defaults; keep historical execution identities stable.
2. Supply the execution boundary with current project environment resolution through runtime wiring. Bind declarations to stored target ids without replacing stored backend, arguments, limits, or retry policy. Handle target removal and invalid project configuration with sanitized configuration failures before process launch.
3. Resolve a binding before session preparation and retain it for automatic retries and session recovery within that target execution. Resolve again for explicit retries and restarted queued jobs. Merge daemon-issued ask variables last through the existing driver environment path. No global environment mutation or unbounded job-secret cache.
4. Incorporate opaque global/project configuration revision context into environment-enabled session identity without exposing secret-derived fingerprints. Test isolation, configuration changes, legacy identity, target capacity, cancellation, and secret-free persistence with fake backends.

**Acceptance Criteria:**
- Fake backend processes receive inherited variables, selected shared values, local values, and project overrides exactly as designed.
- Parallel projects and targets never share configured values.
- Daemon-generated ask credentials cannot be overridden or referenced through configuration.
- Automatic retry and session recovery keep the same environment binding.
- Explicit retries and queued restart use current environment configuration.
- Stored non-environment target policy survives configuration changes.
- A removed target fails environment-enabled rebinding safely.
- Historical plans without environment metadata still parse and execute without newly configured environments.
- Environment-free target identity remains unchanged.
- Environment-enabled sessions separate project/configuration contexts; capacity limits are not multiplied.
- `execution_plan_json`, database events, result metadata, and environment-handling logs contain no synthetic secret values or templates.
- Environment-resolution failures do not trigger provider-policy retries or affect provider circuit health.
- Cancellation and termination release any in-memory bindings.

**Reviewer Checklist:**
- Follow submission, persisted snapshot parsing, job start, restart, explicit retry, automatic retry, and session recovery end to end.
- Confirm neither raw declarations nor resolved values enter durable serialization.
- Confirm project resolution runs outside blocking event-loop paths using existing worker patterns.
- Inspect session identity, stale next-target tokens, target semaphores, and health-key behavior for regressions.
- Confirm the backend driver and subprocess transport are reused rather than duplicated.
- Confirm failure handling does not attach raw configuration exceptions to public metadata.

**Verification Checks:**
- `cd server && uv run pytest`

### Phase 3: Preserve editor behavior and document the contract

**Task Guide Input:** Harden existing configuration/dashboard boundaries for environment-bearing configs without adding environment controls. Prove unrelated dashboard edits preserve declarations and comments, public read models omit contents, validation and revision checks remain effective, and all approved TOML and lifecycle semantics are documented.

**Goal:** Make operator configuration safe to maintain through existing tools.

**Files:**
- Modify: `server/src/refract/config_mutation.py`
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/tests/test_config_mutation.py`
- Modify: `server/tests/test_dashboard.py`
- Modify: `server/tests/test_config_inspection.py`
- Modify: `server/tests/test_environment.py`
- Modify: `server/README.md`

**Tasks:**
1. Add editor round-trip regressions for global shared sets, ordered selections, target-local tables, and project overlays. Preserve unrelated values and comments during target/profile edits. Keep current compare-and-swap and candidate validation behavior. Change production mutation code only where these regressions demonstrate a gap.
2. Exercise dashboard configuration, job detail, editor read/write, and error responses with synthetic secret markers. Keep environment contents out of typed responses and safe execution-plan views. Add only narrowly necessary allow-list hardening.
3. Document complete valid global and project TOML examples, precedence, interpolation and escaping, reserved ask keys, trusted project configuration, memory-only lifecycle, target removal, plaintext config storage, and the target `PATH` discovery limitation. State that dashboard environment controls and exact restart replay are not supported.

**Acceptance Criteria:**
- Existing target edits preserve `envs_vars`, `envs`, shared tables, and comments.
- Existing project profile edits preserve environment overlays.
- Stale revision writes and invalid candidate configurations remain rejected without altering files.
- Dashboard and mutation responses reveal no environment values or templates.
- Job detail remains compatible with historical and environment-enabled snapshots.
- README examples parse through the actual global and project loaders in regression tests.
- Documentation matches observed behavior and contains placeholders, not credentials.
- The complete non-live server suite passes after all new regressions are included.

**Reviewer Checklist:**
- Confirm no environment editor controls or new API fields expose secrets.
- Review responses and persisted diagnostics rather than assuming DTO defaults are sufficient.
- Check TOML table ownership so new examples cannot attach keys to the wrong section.
- Verify mutation tests cover inline tables and ordinary TOML tables.
- Preserve unrelated active plan files and existing retry-policy/telemetry behavior.

**Verification Checks:**
- `cd server && uv run pytest`

## Final Acceptance

All three phases require fresh tests, specification review, and independent quality review. Run the same full suite at the final consolidated revision. Report counts, skipped live checks, outstanding debt, changed paths, and cleanliness. No runtime deployment is part of this plan.
