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

Pending. Read-only response will be copied here by the Coordinator after checking the unchanged root.

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
- State checkpoint: pending
