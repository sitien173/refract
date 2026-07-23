# Profile Strategy Refactor — Plan

Design: `docs/plans/profile-strategy-refactor/DESIGN.md`

Two phases. Phase 1 strips fabricated config defaults and legacy scaffolding so
config must be explicit. Phase 2 adds explicit chained `extends` inheritance and
allows partial profiles. Phase 2 depends on Phase 1.

---

### Phase 1: Strict config, no fabricated defaults

**Task Guide Input:** Refactor `src/openmcp/config.py` so daemon configuration
is fully explicit with no fabricated fallbacks. Remove `_default_targets`,
`_default_profiles`, and `_default_legacy_routes`. Remove the entire legacy
routes path: `_legacy_routes`, the `include_defaults` parameter, the `routes`
config section, and the `routing_profiles`/`default_routing_profile` aliases;
`_target_selection` must drop its `legacy_routes` parameter so a bare string
value resolves to a single target id only. Remove `legacy_selections` from
`DaemonConfig` and every reader. `load_config` must require `config.toml` to
exist (missing file is an error), require a non-empty `[targets]`, require a
non-empty `[profiles]`, and require `[daemon].default_profile` to be set and to
name a defined profile (no `"balanced"` fallback). Keep the load-time
per-profile completeness check unchanged in this phase. Also drop the
`routing_profiles` migration branch in `src/openmcp/config_writer.py`. Update
`README.md` and `CLI_ARGUMENTS.md` to describe the required sections and the
absence of defaults. Update `tests/test_smoke.py` (`[routing_profiles.balanced]`
-> `[profiles.balanced]` with explicit `default_profile`) and any other test or
helper that relied on fabricated defaults or `legacy_selections`
(e.g. `tests/orchestration_helpers.py`, `tests/test_config.py`).
**Profile:** `Resolve at execution`
**Goal:** Configuration is explicit; missing targets, profiles, default_profile,
or config file each fail with a clear error, and no legacy aliases remain.

**Files:**
- Modify: `src/openmcp/config.py`
- Modify: `src/openmcp/config_writer.py`
- Modify: `README.md`
- Modify: `CLI_ARGUMENTS.md`
- Modify: `tests/test_smoke.py`
- Modify: `tests/test_config.py`
- Modify: `tests/orchestration_helpers.py`

**Tasks:**
1. Delete the three default factories and the legacy-routes machinery; simplify
   `_target_selection` and `_profiles` signatures accordingly.
2. Make `load_config` strict: require file, `[targets]`, `[profiles]`, and a
   valid `default_profile`; remove `legacy_selections` from `DaemonConfig`.
3. Remove the `routing_profiles` alias handling in `config_writer.py`.
4. Update docs and migrate tests/helpers off defaults and legacy sections.

**Acceptance Criteria:**
- Loading with a missing `config.toml` raises a clear error.
- Missing or empty `[targets]` or `[profiles]` raises a clear error.
- `default_profile` unset or naming an undefined profile raises a clear error.
- No references to `routes`, `routing_profiles`, `legacy_selections`,
  `include_defaults`, or the removed factories remain in `src/`.
- Per-profile completeness check still enforced (unchanged this phase).

**Reviewer Checklist:**
- No fabricated target/profile survives any load path (`load_config` and
  `load_project_config`).
- Error messages name the missing/invalid section.
- `config_writer.py` round-trips a `profiles`-only document without reintroducing
  `routing_profiles`.
- Docs match the new strict contract.

**Verification Checks:**
- `python -m pytest tests/test_config.py tests/test_smoke.py tests/test_planning.py`
- `python -m pytest`
- `rg -n "routing_profiles|legacy_selections|_default_targets|_default_profiles|_default_legacy_routes|include_defaults" src`

**Commit:** `refactor(config): require explicit targets and profiles`

---

### Phase 2: Explicit chained inheritance and partial profiles

**Task Guide Input:** Extend `src/openmcp/config.py` profile resolution to
support explicit inheritance and partial profiles, per
`docs/plans/profile-strategy-refactor/DESIGN.md`. Add a reserved `extends`
string key inside a profile table naming exactly one parent profile; it is not a
workflow. Resolution is lazy and memoized so declaration order is irrelevant:
resolve the parent first, copy its resolved workflow map, then override
per-workflow with the child's declared selections (whole `TargetSelection`
replaced, matching current `dict.update` granularity). Reject unknown parents
and reject cycles with an error naming the cycle. Remove the load-time
per-profile completeness check so a profile may declare any subset of workflows,
including one. Do not add any implicit fill from the default profile; rely on the
existing submission-time rejection in `resolve_execution_plan`
(`src/openmcp/planning.py`) for a workflow a profile does not map. In
`load_project_config`, drop the implicit `inherited_profile` base inheritance:
project profiles start from their own `extends` only. A project profile with the
same name as a base profile replaces it; `extends` resolves against the merged
base+project namespace, and a project profile named `X` that also
`extends = "X"` must resolve the parent from the base-layer snapshot with itself
excluded. Ensure `config_writer.py` preserves the `extends` key. Add tests for
chains, override, partial load, unknown parent, cycles, submission-time
rejection of an unmapped workflow, and the layering/replace/self-extend cases.
**Profile:** `Resolve at execution`
**Goal:** Profiles inherit via explicit `extends` chains and may be partial;
unmapped workflows are rejected only at submission.

**Files:**
- Modify: `src/openmcp/config.py`
- Modify: `src/openmcp/config_writer.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_planning.py`
- Modify: `README.md`
- Modify: `CLI_ARGUMENTS.md`

**Tasks:**
1. Parse and validate the reserved `extends` key; separate it from workflow
   selections.
2. Implement lazy memoized chain resolution with unknown-parent and cycle
   errors.
3. Remove the completeness check; allow partial profiles.
4. Rework `load_project_config` layering: replace same-name, resolve `extends`
   across the merged namespace with the base snapshot for self-extends.
5. Preserve `extends` in `config_writer.py`; add tests and update docs with an
   `extends`/partial-profile example.

**Acceptance Criteria:**
- `extends` composes a multi-level chain; child overrides win per workflow.
- Unknown parent and cyclic `extends` each raise a clear error.
- A profile declaring only `consult` loads successfully.
- Submitting an `implement` job with a consult-only profile is rejected with the
  mapped-workflow error; a `consult` job with it succeeds.
- Declaration order of profiles does not affect resolution.
- A project profile replaces a same-name base profile; a project profile
  `extends`-ing a base name builds on the base definition.

**Reviewer Checklist:**
- No implicit default-profile fallback reintroduced at load or resolve time.
- Cycle detection cannot infinite-loop; self-extend against base snapshot works.
- `extends` is never treated as a workflow or passed to `_target_selection`.
- `config_writer.py` retains `extends` on round-trip.

**Verification Checks:**
- `python -m pytest tests/test_config.py tests/test_planning.py`
- `python -m pytest`

**Commit:** `feat(config): explicit profile inheritance and partial profiles`
