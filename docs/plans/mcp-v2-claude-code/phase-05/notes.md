<!-- ccg-shared-version: 11.0.6 -->

# Phase 5: Decision Notes

Worker-owned. Append one task block per declared task with decisions, spec deviations, tradeoffs, assumptions, human follow-ups, and exact RED/GREEN evidence. Preserve earlier blocks.

## Task 1 — Dashboard job metadata

### Decisions made
- Reused the persisted `job_record.access_mode`, `dependencies_for_job`, and `Runtime.waiting_metadata`; retained dashboard-only prompt, result, target, revision, and execution-plan fields.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED: `timeout --kill-after=5s 180s uv run --extra dev pytest tests/test_dashboard.py::test_project_jobs_are_grouped_bounded_and_keep_all_active tests/test_dashboard.py::test_dashboard_job_metadata_uses_persisted_access_and_real_waiting_reason tests/test_dashboard.py::test_settings_exposes_effective_and_pending_readers_and_put_is_strict tests/test_dashboard.py::test_settings_reader_mutation_rejects_invalid_stale_and_unauthorized_requests tests/test_dashboard.py::test_confirmed_removed_api_aliases_return_json_not_found -q` -> exit 1, 5 failed. Failures exposed array-shaped project jobs, missing metadata/settings fields, absent PUT, and aliases still registered.
- GREEN: the final backend dashboard suite passed (46 tests); the regression republishes catalog configuration after persisting a `parallel_read` job and verifies real dependency waiting metadata remains intact.

## Task 2 — Grouped project jobs and callers

### Decisions made
- Jobs remains project-selected. The three audited screens consume `{active,recent,more_recent}` directly; there is no legacy array fallback or global jobs endpoint.

### Spec deviations
- none

### Tradeoffs accepted
- Older terminal jobs are counted and disclosed, not paginated.

### Assumptions
- Database job order is the existing newest-created order; the endpoint preserves it while partitioning before limiting.

### Follow-ups for human
- none

### Test evidence
- RED: `timeout --kill-after=5s 180s uv run --extra dev pytest tests/test_dashboard.py::test_project_jobs_are_grouped_bounded_and_keep_all_active -q` initially observed the legacy array shape instead of grouped keys.
- RED: `timeout --kill-after=5s 180s npm --prefix web test -- src/screens/Jobs.test.jsx src/screens/ProjectDetail.test.jsx src/screens/Projects.test.jsx src/components/JobDetails.test.jsx src/App.test.jsx src/api.test.js` -> exit 1, 6 files failed, 10 tests failed and 54 passed. Grouped responses did not render correctly, and reader capacity had no form/API.
- GREEN: after caller/mocks were migrated, the same bounded focused frontend command passed 64 tests. The final full web run passed all 202 tests.
- GREEN: backend route regression covers 13 active jobs, 15 terminal jobs, newest-10 recent, integer `more_recent=5`, and exact empty response. Jobs/ProjectDetail/Projects consumer tests and full frontend tests passed; ProjectDetail polling stops after the active group empties.

## Task 3 — Pending reader-capacity settings

### Decisions made
- Effective capacity comes from `scheduler.max_project_readers`; configured/pending capacity comes from `catalog.max_project_readers`. The strict update model forbids extra fields and rejects coercions.
- The PUT reuses `mutations.lock`, `load_source`, `read_document`, and `commit_document(expected_revision=...)`. Publishing updates the catalog but not the already-constructed scheduler.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Restart the daemon when applying a saved reader-capacity change; this phase deliberately did not restart it.

### Test evidence
- RED: included in the exact 5-failure backend batch and 10-failure focused frontend batch above. During implementation, the numeric form regression also caught a draft-initialization race (an initial settings response overwrote the just-entered value); a dirty ref now protects drafts during query refresh.
- GREEN: HTTP tests cover a valid save, strict boolean/string/float/zero/negative/extra-field rejection, CSRF denial, stale revision, unrelated TOML preservation, and unchanged effective scheduler capacity. App/API tests cover numeric submission, no integer truncation, dirty draft preservation through refresh/conflict, and explicit reload before retry. Full backend and frontend suites passed.

## Task 4 — Dashboard route aliases

### Decisions made
- Retained `/dashboard/api/status` and `/dashboard/api/overview` as distinct routes; retained `/dashboard/api/configuration`, `/dashboard/api/config/health`, browser `/dashboard/config`, and project `profile-overrides` CRUD.
- Removed only exact `/dashboard/api/config` and the five project-scoped `/dashboard/api/projects/{project_id}/configuration/profiles` alias registrations.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED: the valid-fixture route test observed successful responses from the aliases instead of JSON 404s.
- GREEN: valid registered-project/override fixtures, existing override IDs, valid Host/Origin/CSRF/revision/body requests now receive status 404 JSON `Dashboard API route not found`; kept routes remain 200. Backend suite passed.

## Task 5 — Bundled assets and verification

### Decisions made
- Generated assets only with the declared Vite build; no manual generated-file edits.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- `timeout --kill-after=5s 180s uv run --extra dev pytest tests/test_dashboard.py -q` -> exit 0, 46 passed.
- `timeout --kill-after=5s 180s npm --prefix web test` -> final exit 0, 18 files and 202 tests passed.
- `timeout --kill-after=5s 180s uv run --extra dev pytest -q` -> exit 0, 546 passed, 3 deselected.
- `timeout --kill-after=5s 180s npm --prefix web run build` -> exit 0 on both builds. Each transformed 65 modules. After snapshot `/tmp/openmcp-phase5-assets-final.jR8CW1/dashboard_static`, the second build followed by `diff -r` returned 0 with no differences.
- Final generated assets: `index-BxpWJUUF.js` SHA-256 `ca39669ee270f42b4f98741612e0d47e7a567a7f9a8fb93ef9e24207902d0a30`; `index-CWP9Noen.css` SHA-256 `e7ab844b314613f72ddc0da2dba91294713695f12838ce08e7fed0c04b45bcbf`. The obsolete tracked hashed files `index-D-nShQgS.js` and `index--OvfbQj5.css` were removed; no other generated files were untracked.
- `git diff --check` -> exit 0.
- Baseline flake retained: before implementation, `Profiles.test.jsx` dirty-draft case failed once (1 failed, 195 passed), then the untouched suite passed (196 passed). During implementation, separate full runs also intermittently failed an unrelated Targets dirty-draft case, a project-override integration assertion (its isolated test passed), and a Profiles create assertion. These were not modified; the final full web suite passed. Existing React act warnings were not suppressed or fixed.

## Specification fix cycle 1 — grouped job lists and reader-revision hypothesis

### H1 RED and confirmation
- Added a revision assertion to the existing actual App flow. In an isolated temporary frontend fixture, settings first returned capacity `1`/revision `initial-rev`; after the dirty value `5` and a completed refresh it displayed capacity `2`/revision `background-rev`. Clicking Save invoked the update with `(5, background-rev)` instead of `(5, initial-rev)`. The focused test `timeout --kill-after=5s 180s npm --prefix web test -- src/App.test.jsx -t 'keeps dirty reader drafts through refresh and requires explicit reload after conflict'` exited 1 on the exact revision mismatch. H1 is confirmed; the stale-draft write could bypass the expected 409.

### H1 GREEN
- RuntimeSettings now captures the reader draft's originating revision alongside its value. Dirty refreshes preserve both. Saving uses that captured revision. Conflict retains the input and disables retry; an explicit reload uses one settings response for the displayed value and bound revision, avoiding a second inconsistent GET. The same focused test then passed, checking `(5, initial-rev)`, forced 409 retention, explicit reload to capacity `3`/`reload-rev`, and the next save `(3, reload-rev)`.

### Grouped job detail regressions
- RED: `timeout --kill-after=5s 180s npm --prefix web test -- src/screens/Jobs.test.jsx src/screens/ProjectDetail.test.jsx -t 'concatenates active and recent groups|filters Jobs table|keeps Jobs project-selected'` -> exit 1, 2 relevant failures: complete `depends_on`/`waiting_on` ID lists were absent from both tables. Fixtures include multiple completed and waiting dependencies; the runtime waiting_reason still intentionally describes the first blocker only.
- GREEN: the same bounded command -> exit 0, 3 passed (including the no-project Jobs route guard). Both tables now render the complete lists alongside waiting_reason. Jobs' no-project data placeholder is the exact grouped empty shape without a global request or array fallback.
- Polling regression test-harness iteration: an initial focused ProjectDetail polling test timed out after 5s because fake timers were enabled after the polling timer was scheduled. Moving fake-timer setup before the tab activation made the finite test pass; production source was unchanged for this test-harness correction.

### Fresh checks for fix cycle 1
- `timeout --kill-after=5s 180s uv run --extra dev pytest tests/test_dashboard.py -q` -> exit 0, 46 passed.
- `timeout --kill-after=5s 180s npm --prefix web test` -> exit 0, 18 files and 203 tests passed.
- `timeout --kill-after=5s 180s uv run --extra dev pytest -q` -> exit 0, 546 passed, 3 deselected.
- Both bounded `npm --prefix web run build` invocations exited 0 (65 modules each). Full snapshot `/tmp/openmcp-phase5-fix01-assets.qdgyHW/dashboard_static` matched the repeated build via `diff -r` (exit 0, no differences). New bundle `index-D1wsrB8z.js` SHA-256: `206fa6401c47bcf8272ddf64369c95a1fb7165b6fae7391e26fc5a1393fa58d2`; `index-CWP9Noen.css` retained SHA-256 `e7ab844b314613f72ddc0da2dba91294713695f12838ce08e7fed0c04b45bcbf`. Obsolete `index-BxpWJUUF.js` was removed; all other fonts/logo and CSS remained unchanged.
- Final `git diff --check` -> exit 0. No API helpers, backend/shared source, Coordinator artifacts, dependencies, environment, or daemon were changed.
