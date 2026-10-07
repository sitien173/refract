<!-- ccg-shared-version: 11.0.6 -->

# Phase 5: Journal: Dashboard v2 vocabulary

## META

- Plan: docs/plans/mcp-v2-claude-code/PLAN.md
- Implementation Profile: implement
- Consultation Profile: consult
- Review Profile: review
- Implementation Job: pending
- Review Job: pending
- Started: 2026-10-07T23:24:22Z
- Finished: pending

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

Pending. Worker appends the full EXTERNAL RESPONSE block here.

## Quality Review

Pending. Coordinator appends the independent review response here.

## Review Result

- Spec Status: PENDING
- Quality Status: PENDING
- Debt: none

## Final Checkpoint

- Phase base ref: refs/plans/mcp-v2-claude-code/phase-05/base
- Phase implementation ref: refs/plans/mcp-v2-claude-code/phase-05/impl
- Plan commit ref: pending
- State checkpoint: finalized scope 0aafdec4a328d231589dbd23918d618b347ba341; phase base was created once at this clean checkpoint. Implementation has not started at this record.
