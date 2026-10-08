# Dashboard Target and Profile CRUD Plan

Status: ACTIVE
Context key: `dashboard-target-profile-crud`

## Confirmed Outcome

Allow loopback dashboard operators to manage global targets, global profiles, and
project profile overrides. Persist surgical TOML changes, preserve unrelated
formatting, prevent stale or referentially invalid mutations, and publish valid
changes immediately.

## Scope

- Add a centralized TOML configuration mutation service.
- Preserve comments, ordering, shorthand, and legacy target keys.
- Use file revisions and `If-Match` concurrency.
- Atomically replace one source file per mutation.
- Roll back failed runtime publication.
- Validate global changes against registered projects.
- Add protected target, profile, and project-override editor APIs.
- Add complete target CRUD to the Targets page.
- Add complete profile CRUD to the Profiles page.
- Add project profile override CRUD to Project Detail.
- Block referenced deletions with structured diagnostics.
- Preserve current runtime-oriented dashboard responses.

## Risks

- TOML edits could normalize unrelated operator content.
- Global mutations could invalidate project overlays.
- Runtime reload failures could leave disk and memory inconsistent.
- Polling could overwrite dirty frontend drafts.
- Editor responses contain system prompts and backend arguments.
- Reference scanning covers registered projects only.
- Existing jobs must retain submitted execution-plan snapshots.

# ROUTE

- Sequence: implement -> review
- Implement Profile: Resolve per phase at execution
- Consult Profile: none
- Review Profile: Resolve per phase at execution
- Reason: The confirmed design already includes focused consultation.
- Done When: Fresh backend, frontend, build, doctor, and diff checks pass.

### Phase 1: Build safe TOML mutation transactions

**Task Guide Input:** Implement the backend foundation for surgical OpenMCP
configuration mutations. Add a centralized service that reads exact source
bytes, calculates SHA-256 revisions, parses and edits with `tomlkit`, preserves
unrelated comments and ordering, validates candidate global or project
configuration through existing loading semantics, and atomically replaces one
regular file. Support minimal project `.openmcp/config.toml` creation. Reject
stale revisions, symlinks, directories, and non-regular paths. Add synchronized
runtime publication and proven rollback when reload fails. Ensure global
publication refreshes the runtime catalog, executor configuration,
configuration health, and project resolution state without changing existing
execution-plan snapshots. Add focused unit and runtime tests. Do not expose HTTP
routes yet.

**Goal:** Provide one tested transaction boundary for safe configuration writes.

**Files:**

- Create: `src/openmcp/config_mutation.py`
- Modify: `src/openmcp/config.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `src/openmcp/execution.py`
- Create: `tests/test_config_mutation.py`
- Modify: `tests/test_runtime.py`
- Modify: `tests/test_execution.py`

**Tasks:**

1. Add failing preservation, concurrency, path-safety, and atomicity tests.
2. Add reusable candidate-loading and TOML document mutation primitives.
3. Add synchronized commit, runtime publication, and rollback behavior.
4. Verify new submissions use new catalogs while existing plans remain stable.

**Acceptance Criteria:**

- Revisions hash exact source bytes.
- Stale expected revisions fail without changing files.
- Candidate validation reuses existing configuration semantics.
- Unrelated TOML regions remain byte-equivalent where `tomlkit` permits.
- Comments, ordering, quoting, shorthand, and legacy keys remain preserved.
- Missing project configuration receives only the requested minimal declaration.
- Unsafe source paths are rejected before writing.
- Temporary writes occur in the source directory.
- Existing file modes remain preserved.
- Runtime publication updates catalog, executor, and health state.
- Publication failure restores exact original bytes when provable.
- Existing execution plans remain unchanged.

**Reviewer Checklist:**

- Confirm no second semantic configuration schema exists.
- Confirm locking spans validation, replacement, and publication.
- Confirm source revisions are rechecked before replacement.
- Confirm rollback never overwrites a later external edit.
- Confirm sensitive values never enter logs or errors.
- Confirm platform-specific directory synchronization is bounded.

**Verification Checks:**

- `uv run pytest tests/test_config_mutation.py tests/test_runtime.py tests/test_execution.py -q`
- `uv run pytest tests/test_config.py tests/test_planning.py -q`
- `git diff --check`

**Commit:** `feat(config): add atomic mutation transactions`

### Phase 2: Expose protected target CRUD

**Task Guide Input:** Add loopback-only dashboard editor APIs for global targets.
Keep the existing runtime `/dashboard/api/targets` response unchanged. Add a
full editor read plus create, update, and delete routes backed exclusively by the
configuration mutation service. Expose every supported target field. Require
same-origin CSRF protection for mutations and loopback protection for full
editor reads. Return `Cache-Control: no-store`, document revisions, and ETags.
Require `If-Match`; use stable 403, 404, 409, 422, 428, and 500 error envelopes.
Keep target identifiers immutable. Block deletion when any global or registered
project profile workflow references the target, returning structured references.
Do not let historical, queued, or running jobs block deletion. Add backend API,
validation, reference, security, and redaction tests.

**Goal:** Provide complete, protected backend CRUD for global targets.

**Files:**

- Modify: `src/openmcp/config_mutation.py`
- Modify: `src/openmcp/models.py`
- Modify: `src/openmcp/dashboard.py`
- Modify: `tests/test_config_mutation.py`
- Modify: `tests/test_dashboard.py`

**Tasks:**

1. Add strict target editor request and response models.
2. Implement target TOML creation, update, reference scanning, and deletion.
3. Register protected editor routes and stable error translation.
4. Add route authorization, concurrency, redaction, and compatibility tests.

**Acceptance Criteria:**

- Editor reads expose every supported target field.
- Existing runtime target responses remain unchanged.
- Full editor reads reject non-loopback access.
- Mutations require loopback host, client, origin, CSRF, and `If-Match`.
- Creates reject duplicate identifiers.
- Updates cannot rename targets.
- Existing legacy `profile` keys remain preserved during updates.
- New targets emit `backend_profile` only.
- Referenced deletion returns all registered global and project references.
- Errors and logs omit system prompts and arguments.
- Successful responses return the new revision and ETag.

**Reviewer Checklist:**

- Confirm protected reads cannot disclose sensitive target fields remotely.
- Confirm route handlers contain no direct TOML manipulation.
- Confirm reference scanning uses declarations, not effective-value equality.
- Confirm existing jobs do not participate in reference blocking.
- Confirm error envelopes state unchanged behavior accurately.

**Verification Checks:**

- `uv run pytest tests/test_config_mutation.py tests/test_dashboard.py -q`
- `uv run pytest tests/test_server.py tests/test_runtime.py -q`
- `git diff --check`

**Commit:** `feat(dashboard): add target configuration API`

### Phase 3: Expose profile and override CRUD

**Task Guide Input:** Add loopback-only dashboard editor APIs for global profiles
and project profile overrides. Keep current profile and project configuration
read responses compatible. Return declarations separately from effective,
inherited, and source-attributed policies. Include all built-in workflows and
use null for workflows not declared at the edited scope. Support complete
workflow policies with ordered targets, `max_attempts`, and `timeout_s`. Preserve
existing shorthand unless an edited workflow requires expansion. Create minimal
project configuration files when absent. Block global profile deletion when
referenced by global or project defaults or `extends`. Implement `Remove
override` semantics that validate the resulting global fallback. Require the
same loopback, no-store, CSRF, ETag, and `If-Match` protections used by target
CRUD. Add focused backend tests.

**Goal:** Provide complete backend CRUD for profiles and project overrides.

**Files:**

- Modify: `src/openmcp/config_mutation.py`
- Modify: `src/openmcp/models.py`
- Modify: `src/openmcp/dashboard.py`
- Modify: `tests/test_config_mutation.py`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_config.py`

**Tasks:**

1. Add strict profile declaration and effective-policy response models.
2. Implement global profile CRUD with inheritance-aware reference checks.
3. Implement project override CRUD and missing-file creation.
4. Add API security, concurrency, shorthand, fallback, and compatibility tests.

**Acceptance Criteria:**

- Responses distinguish declared, inherited, and effective workflow values.
- All built-in workflows appear in editor responses.
- Ordered target failover remains preserved.
- Shorthand changes only when the edited policy requires expansion.
- Global profile changes validate every registered project overlay.
- Default and `extends` references block profile deletion.
- Removing an override returns the resulting effective global fallback.
- Missing project files are created minimally and atomically.
- Global and project files use independent revisions.
- Existing profile summary and project resolution responses remain compatible.

**Reviewer Checklist:**

- Confirm null means undeclared rather than disabled.
- Confirm the backend owns inheritance and provenance calculations.
- Confirm project mutations cannot edit global declarations.
- Confirm self-extension behavior remains compatible.
- Confirm deletion checks include project defaults and project parents.
- Confirm project-file creation adds no unrelated configuration.

**Verification Checks:**

- `uv run pytest tests/test_config_mutation.py tests/test_dashboard.py tests/test_config.py -q`
- `uv run pytest tests/test_planning.py tests/test_runtime.py -q`
- `git diff --check`

**Commit:** `feat(dashboard): add profile configuration API`

### Phase 4: Add target management UI

**Task Guide Input:** Add complete global target CRUD to the existing React
Targets screen using the new protected editor API. Preserve the current runtime
health grid, filters, inspector, and five-second health polling. Add create,
edit, and delete actions. Build a focused target form exposing every supported
field, including ordered repeatable arguments and system prompt text. Keep
runtime status separate from editable configuration. Preserve dirty drafts when
polling or revision conflicts occur. Send CSRF and `If-Match` through shared API
helpers. Show saving, reloading, active, validation, conflict, reference, and
failure states accessibly. Never place system prompts or arguments in tables,
toasts, or generic errors. Add component and integration tests using existing
FlowForge styles.

**Goal:** Let local operators safely manage global targets from the dashboard.

**Files:**

- Modify: `web/src/api.js`
- Create: `web/src/components/TargetEditor.jsx`
- Create: `web/src/components/ConfigurationMutationDialog.jsx`
- Modify: `web/src/screens/Targets.jsx`
- Modify: `web/src/screens/Targets.test.jsx`
- Modify: `web/src/integration/dashboard-flow.test.jsx`
- Modify: `web/src/styles/app.css`

**Tasks:**

1. Add shared revision-aware mutation API helpers and failure mapping.
2. Build the complete target form and confirmation behavior.
3. Integrate create, edit, and deletion into Targets without disrupting health.
4. Add accessibility, dirty-state, conflict, and reference tests.

**Acceptance Criteria:**

- Operators can create targets using every supported field.
- Operators can edit fields without renaming target identifiers.
- Arguments use ordered repeatable string controls.
- Runtime health continues refreshing during editor use.
- Polling never replaces a dirty draft.
- Conflicts retain drafts and offer explicit reload.
- Referenced deletion displays structured blocking references.
- Unreferenced deletion requires confirmation.
- Sensitive fields appear only inside the protected editor.
- Existing filters, inspector details, and health states still work.

**Reviewer Checklist:**

- Confirm API helpers refresh CSRF only for authorization failures.
- Confirm `If-Match` always uses the loaded editor revision.
- Confirm no shell parsing or argument normalization occurs.
- Confirm async state changes are announced accessibly.
- Confirm existing target polling tests remain meaningful.

**Verification Checks:**

- `npm --prefix web test -- --run src/screens/Targets.test.jsx src/integration/dashboard-flow.test.jsx`
- `npm --prefix web run build`
- `git diff --check`

**Commit:** `feat(dashboard): manage targets in UI`

### Phase 5: Add profile management UI

**Task Guide Input:** Add complete global profile CRUD to the React Profiles
screen using the new editor API. Keep the existing profile table compatible and
add selection, create, edit, and delete actions. Build a reusable profile editor
that shows parent selection, locally declared workflows, inherited values,
effective values, provenance, and available targets. Each built-in workflow
uses a declaration toggle, ordered target editor, `max_attempts`, and
`timeout_s`. Preserve dirty drafts during background refreshes and revision
conflicts. Show referenced deletion details and require confirmation when
unreferenced. Use existing FlowForge modal, grid, focus, and alert conventions.
Add focused component and integration tests.

**Goal:** Let local operators safely manage global profiles.

**Files:**

- Modify: `web/src/api.js`
- Create: `web/src/components/ProfileEditor.jsx`
- Modify: `web/src/screens/Profiles.jsx`
- Modify: `web/src/screens/Profiles.test.jsx`
- Modify: `web/src/integration/dashboard-flow.test.jsx`
- Modify: `web/src/styles/app.css`

**Tasks:**

1. Add profile and effective-policy API helpers.
2. Build the complete reusable profile workflow editor.
3. Integrate create, edit, and delete actions into Profiles.
4. Add inheritance, ordering, conflict, deletion, and accessibility tests.

**Acceptance Criteria:**

- Operators can create and edit global profiles.
- Every built-in workflow can be declared or inherited.
- Ordered failover targets remain visibly ordered.
- Declared, inherited, and effective policies remain distinguishable.
- Parent profile and provenance remain visible.
- Conflicts retain drafts and offer explicit reload.
- Referenced deletions identify defaults and parent references.
- Existing profile summary behavior remains intact.

**Reviewer Checklist:**

- Confirm the frontend does not calculate inheritance.
- Confirm undeclared workflows remain distinct from empty policies.
- Confirm target ordering supports keyboard interaction.
- Confirm form validation maps to specific workflow controls.
- Confirm no sensitive target values enter profile responses or UI.

**Verification Checks:**

- `npm --prefix web test -- --run src/screens/Profiles.test.jsx src/integration/dashboard-flow.test.jsx`
- `npm --prefix web run build`
- `git diff --check`

**Commit:** `feat(dashboard): manage profiles in UI`

### Phase 6: Add project overrides and verify complete flow

**Task Guide Input:** Add project profile override CRUD to the Profile Resolution
section of React Project Detail. Reuse the global profile editor while clearly
separating project declarations, global inheritance, and effective behavior.
Add create override, edit override, and remove override actions. Label removal
as `Remove override` and preview the resulting global fallback before
confirmation. Preserve dirty drafts during project and configuration-health
polling. Add project-focused frontend and backend integration coverage for
missing-file creation, conflict recovery, validation failures, runtime
activation, and existing-job plan preservation. Update operator documentation
to explain editable scopes, local-only security, revisions, immediate
activation, deletion restrictions, and registered-project integrity. Run fresh
full verification.

**Goal:** Complete project override management and validate the end-to-end system.

**Files:**

- Modify: `web/src/api.js`
- Modify: `web/src/screens/ProjectDetail.jsx`
- Modify: `web/src/screens/ProjectDetail.test.jsx`
- Modify: `web/src/integration/dashboard-flow.test.jsx`
- Modify: `web/src/styles/app.css`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_runtime.py`
- Modify: `README.md`
- Modify: `docs/plans/admin-configuration-dashboard/DESIGN.md`

**Tasks:**

1. Integrate reusable profile editing into Project Detail.
2. Add fallback previews, missing-file, and conflict integration coverage.
3. Document configuration editing, security, activation, and integrity limits.
4. Run full backend, frontend, packaging, and doctor verification.

**Acceptance Criteria:**

- Project Detail can create, edit, and remove profile overrides.
- The UI labels project removal as `Remove override`.
- Removal previews resulting effective global behavior.
- Missing `.openmcp/config.toml` files are created on first override.
- Project polling never replaces dirty drafts.
- Valid changes become active without daemon restart.
- Existing jobs retain previous execution plans.
- Documentation no longer states that target and profile files are read-only.
- Documentation explains registered-project reference limitations.
- Complete backend and frontend suites pass freshly.

**Reviewer Checklist:**

- Confirm project actions cannot mutate global profile declarations.
- Confirm fallback previews use server-resolved data.
- Confirm operator documentation matches actual authorization behavior.
- Confirm no remote administration capability was introduced.
- Confirm all prior dashboard flows remain functional.
- Confirm package artifacts include the rebuilt dashboard.

**Verification Checks:**

- `uv run pytest -q`
- `npm --prefix web test`
- `npm --prefix web run build`
- `uv build`
- `uv run openmcp doctor`
- `git diff --check`

**Commit:** `feat(dashboard): manage project profile overrides`

## Final Review

Specification review must confirm every confirmed design decision. Quality
review must inspect each phase delta independently. Fresh final evidence requires:

```bash
uv run pytest -q
npm --prefix web test
npm --prefix web run build
uv build
uv run openmcp doctor
git diff --check
```
