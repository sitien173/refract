# Profile Config Fragments Plan

Status: ACTIVE
Context key: `profile-config-fragments`

## Confirmed Outcome

Load direct-child `*.config.toml` fragments globally and per project. Allow only
target and profile definitions. Validate every fragment before effective
configuration resolution. Main `config.toml` files replace matching fragment
definitions entirely.

## Scope

- Add case-sensitive, non-recursive fragment discovery.
- Sort fragment filenames deterministically.
- Preserve source paths through parsing and validation.
- Allow only `targets` and `profiles` fragment sections.
- Warn and fail on same-directory fragment conflicts.
- Reject invalid fragments even when main files shadow them.
- Apply global and project precedence.
- Support project target definitions.
- Preserve profile inheritance and base immutability.
- Document fragment locations, format, and precedence.

## Risks

- Early merging could hide invalid fragment definitions.
- Filename ordering must not create hidden precedence.
- Target references need the effective target catalog.
- Profile inheritance must preserve layer snapshots.
- Project targets expand repository trust.
- Startup warnings occur before logging configuration.

# ROUTE

- Sequence: implement -> review
- Implement Profile: Resolve at execution
- Consult Profile: none
- Review Profile: Resolve at execution
- Reason: Confirmed design already includes focused consultation.
- Done When: Fresh focused and full tests pass.

### Phase 1: Load validated global fragments

**Task Guide Input:** Add source-aware loading of direct-child, case-sensitive
`*.config.toml` fragments beside the global OpenMCP `config.toml`. Fragments may
contain only `[[targets]]` and `[profiles.*]`. Sort filenames for deterministic
processing without giving filenames precedence. Validate every fragment before
main-file shadowing. Duplicate target or profile identifiers across global
fragment files must emit one `ConfigFragmentConflictWarning`, then raise
`ValueError`. Overlay global `config.toml` definitions last. Main definitions
replace matching targets and profiles entirely. Preserve existing target
validation, profile inheritance, default-profile validation, and behavior when
no fragments exist. Add focused tests. Do not add project fragments yet.

**Goal:** Build the effective global catalog from validated fragments.

**Files:**

- Modify: `src/openmcp/config.py`
- Modify: `tests/test_config.py`

**Tasks:**

1. Add failing discovery, validation, and conflict tests.
2. Add source-aware fragment parsing and deterministic discovery.
3. Separate per-source validation from effective catalog resolution.
4. Overlay main definitions and preserve current global behavior.

**Acceptance Criteria:**

- Only direct-child `*.config.toml` files are discovered.
- Matching is case-sensitive and non-recursive.
- Discovery and diagnostics use sorted filenames.
- Empty fragments and unsupported sections fail clearly.
- Every fragment error includes its source path.
- TOML errors retain line and column details.
- Duplicate fragment target identifiers warn and fail.
- Duplicate fragment profile identifiers warn and fail.
- Conflict details identify both source paths.
- Main-versus-fragment duplicates produce no warning.
- Main target replacement resets omitted fields to defaults.
- Main profile replacement drops fragment workflows.
- Invalid shadowed fragments still fail loading.
- Fragment profiles can extend other fragment profiles.
- Main profiles can extend surviving fragment profiles.
- Profiles resolve against effective main-over-fragment targets.
- Main `[daemon].default_profile` may name a fragment profile.
- Existing configurations work unchanged without fragments.

**Reviewer Checklist:**

- Confirm fragments never gain daemon or logging settings.
- Confirm filename order creates no precedence.
- Confirm warning details match the raised error.
- Confirm invalid shadowed sources cannot escape validation.
- Confirm complete definitions replace instead of merging.
- Confirm all target argument guardrails remain active.
- Confirm global self-extension remains a cycle.

**Verification Checks:**

- `uv run pytest tests/test_config.py -q`
- `uv run pytest tests/test_planning.py tests/test_smoke.py -q`
- `git diff --check`

**Commit:** `feat(config): load global profile fragments`

### Phase 2: Apply project fragments and document precedence

**Task Guide Input:** Extend source-aware `*.config.toml` loading to direct
children of each project's `.openmcp` directory. Permit `[[targets]]` and
`[profiles.*]` in project fragments. Also permit `[[targets]]` in project
`.openmcp/config.toml`. Apply complete-definition precedence from global
fragments, global main, project fragments, then project main. Treat duplicates
between project fragment files as warning-plus-error conflicts. Allow project
definitions to replace global definitions without warnings. Preserve explicit
profile inheritance, project self-extension against global snapshots, target
validation, and base catalog immutability. Document discovery, allowed
sections, precedence, replacement semantics, errors, and project trust. Add
focused regression tests.

**Goal:** Resolve project catalogs using all four layers.

**Files:**

- Modify: `src/openmcp/config.py`
- Modify: `tests/test_config.py`
- Modify: `README.md`

**Tasks:**

1. Add failing project discovery and precedence tests.
2. Load project targets and profiles through shared helpers.
3. Preserve cross-layer inheritance and immutable base catalogs.
4. Document fragment usage, precedence, and trust implications.

**Acceptance Criteria:**

- Project fragments load without a project main file.
- Project fragment matching remains direct and case-sensitive.
- Project fragment conflicts warn and fail deterministically.
- Project definitions replace global definitions without warnings.
- Project main definitions replace project fragment definitions.
- Project target replacement resets omitted fields to defaults.
- Project profile replacement drops fragment workflows.
- Project fragments may extend visible global profiles.
- Project main profiles may extend project fragment profiles.
- Project self-extension still uses the global snapshot.
- Project profile target references use effective project targets.
- Invalid shadowed project fragments still fail resolution.
- Failed project loading never mutates the base catalog.
- Existing profile-only project configurations remain valid.
- README explains format, locations, precedence, and failures.
- README identifies project target trust implications.

**Reviewer Checklist:**

- Confirm global catalogs never mutate during project loading.
- Confirm project overrides replace whole definitions.
- Confirm cross-layer inheritance has no implicit merging.
- Confirm project targets retain argument validation.
- Confirm missing project files preserve current behavior.
- Confirm documentation matches implemented discovery exactly.

**Verification Checks:**

- `uv run pytest tests/test_config.py -q`
- `uv run pytest -q`
- `uv build`
- `uv run openmcp doctor`
- `git diff --check`

**Commit:** `feat(config): load project profile fragments`

## Final Review

Specification review must confirm both phase outcomes. Quality review must
inspect each phase delta only. Fresh final evidence requires:

```bash
uv run pytest -q
uv build
uv run openmcp doctor
git diff --check
```
