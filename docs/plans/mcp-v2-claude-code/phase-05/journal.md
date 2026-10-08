<!-- ccg-shared-version: 11.0.6 -->

# Phase 5: Journal: Dashboard v2 vocabulary

## META

- Plan: docs/plans/mcp-v2-claude-code/PLAN.md
- Implementation Profile: implement
- Consultation Profile: consult
- Review Profile: review
- Implementation Job: f623d7fe-14b3-456d-b999-61255fe8155a
- Review Job: pending
- Started: 2026-10-07T23:24:22Z
- Finished: 2026-10-08T07:02:53+07:00

## Guidance and preparation

- task_guide was called once for this new phase on 2026-10-08 in the session's local date. Its live signature accepts project_id only; the complete phase request is recorded in prompt.md.
- Route: consult/consult, implement/implement, review/review. The API, model, and server-test portion matches the first implementation recommendation before the UI/client recommendation. All three selected workflows and profiles were verified against the live resource metadata with the existing SDK 2.0.0, without dependency or environment changes.
- The resource-list adapter returned no resources. A verified SDK ClientSession over the configured credential-free loopback endpoint read only the public profiles/workflows resources. The check printed only availability booleans, never target or execution identities. Context7 v2.0.0 documentation verified its lifecycle and read_resource syntax.
- Fresh status: running, 0 active jobs, 0 queued jobs. main is attached at 417a9e75e6571a280aa3e27c7684f5a4c4f86c6c. Phase 4 implementation anchor resolves to the same closure commit. Before preparation, the root was clean; current changes are only Coordinator handover and new Phase 5 artifacts.
- tgrep enumerated the existing tests. Matching scope includes Jobs, ProjectDetail, Projects, Overview, ConfigHealth, shared JobDetails, App, dashboard-flow integration, and api.test.js. JobDetail and RuntimeSettings have no standalone test; existing shared/App/integration coverage is included. The consultation will confirm this set and any caller issue within PLAN scope.
- Required consultation: cross-component HTTP vocabulary, frontend grouping, and startup-bound settings. No implementation is authorized before incorporation and final phase anchoring.

## Baseline checks

- Backend: `timeout --kill-after=5s 180s uv run --extra dev pytest tests/test_dashboard.py -q` passed 41 tests in 0.89s.
- First untouched frontend run failed: 1 failed, 195 passed across 18 files. `Profiles.test.jsx:338` expected the dirty draft value `my-unsaved-draft`, received an empty string. The captured output is the session tool result bw98pay9t.txt.
- Second untouched frontend run passed: 18 files, 196 tests, in 13.67s. Capture: /tmp/mcp-v2-phase05-web-baseline2.log. Both outcomes are retained; the first is not relabelled as a pass. Existing act warnings remain outside this change.
- `git diff --check` passed after the second run. No implementation source changed. Consultation must assess whether the dirty-draft failure affects this phase; no adjacent Profiles source fix is authorized.
- Root-freeze handling: a submission receipt will be stored outside the repository while the consult is active and copied to tracked handover/journal only once terminal. The handover next_action names that receipt so ownership remains recoverable. This follows the explicit root-freeze constraint rather than editing tracked metadata during the job.

## Consultation Response

- Job: 32cb7227-6c6f-43f6-a581-a933fce061a1, consult/consult, terminal succeeded.
- First wait k2fi9y4sr returned running. Only after it finished, one replacement wait kyk6v4ccn returned succeeded. No duplicate job or concurrent wait was submitted. Root remained frozen during both waits; private receipt /tmp/mcp-v2-phase05-consult-receipt.json owns the submission.
- Post-consult reconciliation: attached main still 68dfc1b868620016d21ca6537c0741e344a7a7be and clean. No worker file changes. The result reports no commands/tests/builds/live reads, FILES MODIFIED none, and consultation complete. This is planning evidence, not implementation or independent quality sign-off.

### Recorded consultation findings

- DashboardJob adds persisted access_mode with conservative exclusive default, independent dependency/waiting lists, and waiting_reason. _dashboard_job remains the operator DTO seam. Runtime.waiting_metadata returns a tuple, not a mapping. Keep execution detail, prompt/result/revision and existing execution-plan allowlist.
- Partition project jobs before limiting. Active includes every queued/running job. Recent includes first 10 terminal jobs in existing newest-created order. more_recent counts remaining terminal jobs. Exact empty grouped shape is required.
- Three observed callers: Jobs concatenates grouped rows and stops terminal polling when loaded active is empty; ProjectDetail updates polling/counts/filters/rows and includes omitted history in the total; Projects uses active.length. No legacy array fallback.
- Corrected the prepared assumption: Jobs is project-selected, not an unfiltered global endpoint. Preserve selection URL/navigation.
- Corrected the prepared assumption: RuntimeSettings has tables only and settings has GET only. The requested native reader-capacity input requires one narrow form and PUT /dashboard/api/settings. Both fit the approved source files. No additional edit-path omissions were found.
- GET reports catalog.max_project_readers as configured/pending and scheduler.max_project_readers as effective. The strict PUT accepts only a positive integer, rejects extras/bool/string/float/zero/negative, reuses CSRF/If-Match/loopback protections and mutation errors, changes only the daemon key under the existing lock, and commits through the existing mutation transaction. Preserve unrelated TOML, dirty drafts, conflicts and effective scheduler capacity. Say Saved; restart required.
- Keep distinct status/overview resources and their separate consumers. Keep configuration, remove exact config alias only, not config/health or browser config deep links. Keep project profile-overrides family, remove all five configuration/profiles alias methods. Valid existing-project/override fixtures must produce 404 JSON with Dashboard API route not found, with otherwise valid authorization/revision/body so missing entities are not mistaken for removed routes. Keep catchall-before-SPA ordering.
- Existing matching test allowlist was confirmed within the supplied inventory. Backend regressions must cover immutable access after catalog publication, real dependency waiting, more than 10 active and terminal jobs without lost active jobs, counts/empty/isolation, pending-only settings save and invalid/conflict/security/TOML cases, distinct resources and aliases.
- Untouched Profiles dirty-draft failure followed by untouched pass is pre-existing intermittent evidence, not Phase 5 RED or scope expansion. Its test changes future mock output without triggering a poll/rerender. Setup/focus races are possibilities, not a verified root cause. Preserve both outcomes and report recurrence separately.
- Reproducibility requires a snapshot and full-directory comparison after a second build, including untracked hashed files and removed old hashes, not git diff alone.
- The consult could not use Auggie/tgrep, so repository-wide caller exhaustiveness was explicitly unresolved. Coordinator then ran the permitted exact audit. It confirmed exactly Jobs.jsx, ProjectDetail.jsx and Projects.jsx as production getProjectJobs callers, plus api.js and allowed matching mocks. No scope omission found.

### Coordinator verification and finalization

- Source inspection confirmed RuntimeSettings is table-only; GET settings has no reader field yet; commit_document holds the shared lock, validates revisions/catalog, preserves atomic commit and publishes configuration.
- Exact helper audit confirmed mutations.lock, load_source, read_document, waiting_metadata tuple, newest-created database ordering, and mutateWithCsrf expectedRevision handling. No new mutation-service abstraction is needed.
- All actionable findings are incorporated into finalized prompt.md. Scope is unchanged, with the explicitly acknowledged narrow PUT/form and required tests inside approved files.


## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase: 5 — Dashboard v2 vocabulary
- Started: 2026-10-08 (fresh implementation context; preserved Phase 1–4)
- Finished: 2026-10-08T07:02:53+07:00
- Plan dir: docs/plans/mcp-v2-claude-code
## SUMMARY
Implemented dashboard v2 job metadata/grouping, strict startup-bound reader-capacity settings, confirmed route removals, updated callers, and reproducible bundled assets.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Updated | src/openmcp/dashboard.py | Exposed dashboard job metadata; grouped active/recent project jobs; added strict settings GET/PUT via existing revision/CSRF mutation transaction; removed only confirmed aliases. |
| Updated | src/openmcp/models.py | Added dashboard job metadata and strict reader-capacity update model. |
| Updated | tests/test_dashboard.py | Added grouping, metadata, reader setting, concurrency/effective capacity, and valid-fixture removed-route regressions. |
| Updated | web/src/api.js | Added CSRF/revision-protected reader-capacity update API. |
| Updated | web/src/screens/Jobs.jsx | Concatenated grouped active/recent jobs, polls based on active group, displays omitted history and admission/waiting metadata. |
| Updated | web/src/screens/ProjectDetail.jsx | Consumes grouped jobs in polling/filtering/rows/counts and displays omitted history and metadata. |
| Updated | web/src/screens/Projects.jsx | Uses `active.length` for activity. |
| Updated | web/src/components/JobDetails.jsx | Renders access mode, dependencies, waiting IDs, and waiting reason. |
| Updated | web/src/screens/RuntimeSettings.jsx | Added strict numeric reader-capacity form, effective/pending display, CSRF/revision save, dirty-draft preservation, conflict reload and restart notice. |
| Updated | web/src/App.test.jsx | Covered settings form save, integer-only input, refresh draft preservation, conflict, and explicit reload. |
| Updated | web/src/api.test.js | Covered protected settings PUT method/body/revision. |
| Updated | web/src/components/JobDetails.test.jsx | Covered shared job metadata rendering. |
| Updated | web/src/screens/Jobs.test.jsx | Covered grouped rows/history and active-group polling. |
| Updated | web/src/screens/ProjectDetail.test.jsx | Updated grouped API mocks; covered total/omitted counts and active-group polling. |
| Updated | web/src/screens/Projects.test.jsx | Updated grouped mocks; confirmed activity counts active jobs only. |
| Updated | web/src/integration/dashboard-flow.test.jsx | Updated project-job mock to grouped response. |
| Updated | src/openmcp/dashboard_static/index.html | Regenerated asset references. |
| Deleted | src/openmcp/dashboard_static/assets/index-D-nShQgS.js | Removed obsolete hashed bundle. |
| Deleted | src/openmcp/dashboard_static/assets/index--OvfbQj5.css | Removed obsolete hashed stylesheet. |
| Added | src/openmcp/dashboard_static/assets/index-BxpWJUUF.js | Generated v2 dashboard bundle; SHA-256 `ca39669ee270f42b4f98741612e0d47e7a567a7f9a8fb93ef9e24207902d0a30`. |
| Added | src/openmcp/dashboard_static/assets/index-CWP9Noen.css | Generated dashboard stylesheet; SHA-256 `e7ab844b314613f72ddc0da2dba91294713695f12838ce08e7fed0c04b45bcbf`. |
| Added | docs/plans/mcp-v2-claude-code/phase-05/notes.md | Recorded per-task RED/GREEN, route decisions, asset hashes/reproducibility, and baseline flake evidence. |
| Updated | docs/plans/mcp-v2-claude-code/phase-05/journal.md | Recorded route decisions and appended this ERP; preserved preparation/baseline evidence. |
## NOTES
- docs/plans/mcp-v2-claude-code/phase-05/notes.md — Task 1–5 evidence.
- RED backend command: `timeout --kill-after=5s 180s uv run --extra dev pytest tests/test_dashboard.py::test_project_jobs_are_grouped_bounded_and_keep_all_active tests/test_dashboard.py::test_dashboard_job_metadata_uses_persisted_access_and_real_waiting_reason tests/test_dashboard.py::test_settings_exposes_effective_and_pending_readers_and_put_is_strict tests/test_dashboard.py::test_settings_reader_mutation_rejects_invalid_stale_and_unauthorized_requests tests/test_dashboard.py::test_confirmed_removed_api_aliases_return_json_not_found -q` -> exit 1, 5 failed.
- RED frontend command: `timeout --kill-after=5s 180s npm --prefix web test -- src/screens/Jobs.test.jsx src/screens/ProjectDetail.test.jsx src/screens/Projects.test.jsx src/components/JobDetails.test.jsx src/App.test.jsx src/api.test.js` -> exit 1, 6 files failed, 10 failed, 54 passed. This exposed the old job-array consumers and missing strict settings form/API. The reader form also caught an initial-query draft race during GREEN and now preserves dirty drafts.
- GREEN backend focused: `timeout --kill-after=5s 180s uv run --extra dev pytest tests/test_dashboard.py -q` -> exit 0, 46 passed.
- Full backend: `timeout --kill-after=5s 180s uv run --extra dev pytest -q` -> exit 0, 546 passed, 3 deselected.
- Full frontend: `timeout --kill-after=5s 180s npm --prefix web test` -> exit 0, 18 files and 202 tests passed. Existing act warnings remain. Earlier full-suite runs exposed an intermittent Targets dirty-draft failure, project-profile-override integration failure (its isolated command passed), and Profiles create failure; all were untouched and a later complete full run passed. The pre-implementation Profiles dirty-draft failure-then-pass baseline remains separately preserved in Baseline checks.
- Both bounded `npm --prefix web run build` commands exited 0 (65 modules each). After snapshot `/tmp/openmcp-phase5-assets-final.jR8CW1/dashboard_static`, `timeout --kill-after=5s 180s npm --prefix web run build && diff -r /tmp/openmcp-phase5-assets-final.jR8CW1/dashboard_static src/openmcp/dashboard_static` exited 0 with no differences. New untracked bundle hashes and removed old hashed asset names are in FILES MODIFIED; other bundled fonts/logo retained their hashes.
- `git diff --check` -> exit 0. No Git writes, daemon restart, OpenMCP calls, dependency/environment changes, live/global state reads, or Coordinator handover/prompt edits. Phases 1–4 and the phase-base checkpoint were preserved.
## SPEC COMPLIANCE
- Meets Spec? YES — backend/frontend acceptance tests, settings safeguards, exact route removals, builds, full-directory reproducibility comparison, full pytest, and diff check passed. The documented pre-existing/intermittent Profiles-related baseline outcome and unchanged act warnings are reported separately.
## CLARIFICATIONS NEEDED
None.
## NEXT
TASK_COMPLETE

## Coordinator validation and specification batch 1

- Actual implementation job f623d7fe-14b3-456d-b999-61255fe8155a returned succeeded and ERP NEXT TASK_COMPLETE. This was coordinated OpenMCP implementation, not direct work. Coordinator corrected the inaccurate META line without rewriting the worker ERP. The worker's notes.md action is Updated, not Added, because preparation had already created the file.
- Waits kc6xe7453, k851tijt5, kpqztsyfj returned running; only after each completion was the next single wait started. kig40lrt8 returned succeeded. Private submission receipt remains /tmp/mcp-v2-phase05-implementation-receipt.json. No poll, duplicate job, concurrent wait, daemon restart, or Coordinator root edit occurred while active.
- Terminal reconciliation: attached main still 0ace49fe533c2f59b2d801660155ac8e5104664c. All actual changed paths and the two untracked generated hashes matched the phase allowlist and ERP path set. Worker left no out-of-scope source changes.
- Fresh Coordinator checks: dashboard46passed1.30s; frontend18files/202tests passed13.42s; full backend546passed3deselected36.73s; two bounded builds each succeeded65modules1.60s; full generated-directory diff was empty; diff check passed. Captured frontend output: /tmp/mcp-v2-phase05-coordinator-web.log. HEAD remained unchanged. Existing baseline failures remain recorded separately.
- Source delta inspection confirmed operator metadata mapping, active/recent/integer count partitioning, pending/effective reader fields and strict one-key model, existing lock/transaction/CSRF/revision reuse, exact route removals, all three callers and generated asset scope.
- Spec is FAIL pending batch1: Jobs' no-project placeholder still returns an array instead of grouped empty shape; both table renderers omit complete depends_on/waiting_on IDs, while the reason supplies only the first dependency. Shared detail is correct.
- H1: reader dirty draft survives refresh but submission uses the newest settings revision. Predict initialA/draft5/refreshB submits5,B and bypasses the draft conflict. Existing test forces409 without asserting the post-refresh revision. This is a source-supported hypothesis, not yet dynamically confirmed. fix-01.md requires a regression before any reader source correction and forbids speculative handling if refuted.
- First automatic fix cycle is prescribed in fix-01.md. No independent quality review has started. The initial validated implementation will be preserved as a temporary checkpoint before the fix; phase implementation anchor remains pending.

## Quality Review

Pending. Coordinator appends the independent review response here.

## Review Result

- Spec Status: FAIL, specification batch 1 pending
- Quality Status: PENDING
- Debt: none

## Final Checkpoint

- Phase base ref: refs/plans/mcp-v2-claude-code/phase-05/base
- Phase implementation ref: refs/plans/mcp-v2-claude-code/phase-05/impl
- Plan commit ref: pending
- State checkpoint: finalized scope 0aafdec4a328d231589dbd23918d618b347ba341; phase base was created once at this clean checkpoint. Implementation has not started at this record.
