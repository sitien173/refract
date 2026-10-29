# Phase 3 Journal: Capacity editing and estimate explanation

## META

- Plan: docs/plans/target-context-window/PLAN.md
- Implementation Profile: implement (recovery after recommended google route failed)
- Consultation Profile: n/a
- Review Profile: implement (recovery route; independent review pending coordinator)
- Implementation Job: initial 0d2182ca-a50e-4163-8cd4-17180acfafbe failed replay_blocked, retryable=false; recovery d7fd4c67-04ce-433d-98ff-48c13107124a
- Review Job: 16533af1-384f-4501-b972-5ddee399729e; closure 55168af5-a758-4973-b298-da3159027a82
- Started: 2026-10-29
- Finished: 2026-10-29T11:59:20+07:00

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase / Started / Finished / Plan dir: Phase 3 / 2026-10-29 / 2026-10-29T11:59:20+07:00 / docs/plans/target-context-window
## SUMMARY
Completed Phase 3 target capacity editing, qualified estimated-context explanation, documentation, and fresh checks after the recommended google worker failed replay_blocked with retryable=false.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/web/src/components/TargetEditor.jsx | Strict positive safe-integer input validation; explicit null clearing; labeled optional capacity field; edit and conflict hydration with existing dirty-draft protections. |
| Modified | server/web/src/components/JobDetails.jsx | Estimated cumulative context explanation only for server-marked estimated usage; unavailable remaining when required capacity/usage is missing. |
| Modified | server/web/src/screens/Targets.test.jsx | Integer create, clear, invalid input, hydration, dirty draft and conflict reload coverage. |
| Modified | server/web/src/components/ConfigEditorSafety.test.jsx | Accessible label and help-description coverage. |
| Modified | server/web/src/components/JobDetails.test.jsx | Estimated and provider snapshot distinction, missing usage and historical telemetry rendering coverage. |
| Modified | server/README.md | TOML example and configuration precedence, clearing, estimation/cache limitations and history documentation. |
| Modified | docs/plans/target-context-window/phase-03/notes.md | Task decisions and RED/GREEN/fresh verification evidence. |
| Modified | docs/plans/target-context-window/phase-03/journal.md | Phase metadata and implementation response. |
## NOTES
- docs/plans/target-context-window/phase-03/notes.md (## Task 1, ## Task 2, ## Task 3)
## SPEC COMPLIANCE
- Meets Spec? YES — Phase acceptance criteria implemented; server, web test suite, and isolated build checks passed. Independent quality review remains for coordinator.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Coordinator Specification Inspection

The recommended google worker failed after partial in-scope editor and test changes. Recovery used the working implement profile and retained those changes. Initial inspection found two rendering issues requiring repair: estimated provider snapshots were described as cumulative because the caption checked quality alone; the new missing-usage guard suppressed valid provider percentages. Remove the unsupported public context_window alias in editor hydration. Initial fresh verification `b8b51aeec` was stopped before repair and is not accepted as evidence. Repair `47db9b59-046e-4be1-a43a-a4c28fc7477a` corrected caption provenance, restored provider percentage rendering, removed the alias, and added positive integer edit coverage. Fresh replacement verification `ba82d6804` is running.

# EXTERNAL RESPONSE
## META
- Phase / Started / Finished / Plan dir: Phase 3 repair cycle 1 / 2026-10-29 / 2026-10-29T12:02:43+07:00 / docs/plans/target-context-window
## SUMMARY
Addressed all four coordinator findings: constrained the estimate caption to derived estimated values, preserved server-provided percentage-only measurements, removed internal-name hydration aliases, and covered integer edit submission.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/web/src/components/JobDetails.jsx | Limit cumulative estimate caption to non-null `derived` + `estimated` usage; remove frontend usage-null masking of server percentage. |
| Modified | server/web/src/components/JobDetails.test.jsx | Add estimated provider snapshot exclusion retaining badge; test provider percentage without usage; set configured-capacity/unknown-usage fixture remaining to null. |
| Modified | server/web/src/components/TargetEditor.jsx | Remove `context_window` alias in both edit and conflict-reload hydration. |
| Modified | server/web/src/screens/Targets.test.jsx | Assert positive integer capacity submission for edit. |
| Modified | docs/plans/target-context-window/phase-03/notes.md | Record repair-cycle RED/GREEN and fresh checks. |
| Modified | docs/plans/target-context-window/phase-03/journal.md | Append repair-cycle response and verification record. |
## NOTES
- docs/plans/target-context-window/phase-03/notes.md (`## Task 4 — Coordinator spec-cycle repairs`)
## SPEC COMPLIANCE
- Meets Spec? YES — All coordinator findings addressed; fresh server/web tests and isolated build passed. No backend or out-of-scope changes.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

# EXTERNAL RESPONSE
## META
- Phase / Started / Finished / Plan dir: Phase 3 repair cycle 2 / 2026-10-29 / 2026-10-29T12:08:32+07:00 / docs/plans/target-context-window
## SUMMARY
Strengthened the dirty-capacity-draft test to exercise changed editor target and revision props, verify draft retention, and verify save uses the original protected revision.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/web/src/screens/Targets.test.jsx | Directly rerender TargetEditor with changed target/revision while draft is dirty; assert the draft survives and submitted update retains the original revision. |
| Modified | docs/plans/target-context-window/phase-03/notes.md | Record test sensitivity and fresh cycle-2 checks. |
| Modified | docs/plans/target-context-window/phase-03/journal.md | Record cycle-2 implementation response. |
## NOTES
- docs/plans/target-context-window/phase-03/notes.md (`## Task 5 — Cycle 2 dirty-draft regression test`)
## SPEC COMPLIANCE
- Meets Spec? YES — The test fails when the dirty-draft guard is disabled, passes with the guard, and confirms the protected revision; full fresh server/web/build checks pass.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Coordinator Verification

Task `ba82d6804` passed before test strengthening: server 1250 passed, 23 skipped, 15 deselected; dashboard 288 passed across 22 files; isolated build exit 0. Checkpoint: `86935be430a047f4d54c7241311b455667eca3e6`. Existing React act and environment warnings were nonfatal. Packaged assets and the separate telemetry plan were unchanged. Fresh task `b31298703` passed after strengthening: server 1250 passed, 23 skipped, 15 deselected; dashboard 288 passed across 22 files; isolated build exit 0. Validated checkpoint: `f62abf37445c952a2ad503eed7456a2c3f534cca`.

## Quality Review

Read-only review `16533af1-384f-4501-b972-5ddee399729e` returned Spec PASS and Quality PASS_WITH_DEBT. It found no correctness/security defects. Its low-severity finding identified a vacuous polling regression test. Cycle 2 replaced it with direct changed-target/revision props and protected-save-revision assertions; production remained unchanged. Read-only re-review `55168af5-a758-4973-b298-da3159027a82` returned Spec PASS and Quality PASS with no remaining findings. No reviewer changes were observed; only the coordinator job-reference update was dirty.

## Review Result

- Spec Status: PASS
- Quality Status: PASS
- Debt: none

## Final Checkpoint

- Phase base ref: refs/plans/target-context-window/phase-03/base
- Phase implementation ref: refs/plans/target-context-window/phase-03/impl
- Plan commit ref: refs/plans/target-context-window/impl
- Validated implementation: f62abf37445c952a2ad503eed7456a2c3f534cca
- Phase status: DONE
