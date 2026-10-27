<!-- refract-shared-version: 2.0.0 -->

# Phase 3 Journal: Remove the Backend Legacy Usage Bridge

## META

- Plan: docs/plans/remove-legacy-metadata/PLAN.md
- Implementation Profile: implement
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: 572a63b9-e11b-46e5-bdbf-8af6c7fe1d3f
- Review Job: cce694f8-ae04-4887-8453-98aca8f64ce5
- Started: 2026-10-27
- Finished: 2026-10-27

## Authorization and Preparation

The user replied `next` after Phase 2 acceptance and its explicit authorization boundary. Execute Phase 3 only. No Phase 4, live/operator state access, daemon actions, migration, or deployment is authorized.

Reconciliation found no active project jobs and a clean attached remove-legacy-metadata branch at `769dee32d0a8ab8b70c1b259e019d02d9345fc0f`. Plan and Phase 2 accepted anchors resolve. Tracking mode is tracked; retain existing isolated worktree. Fresh Phase 3 task guidance selects implement and review profiles. Accepted baseline product passed 963 Python tests, 15 live deselected, and both plugin checks.

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase: Phase 3
- Started: 2026-10-27T16:00:00+07:00
- Finished: 2026-10-27T16:40:00+07:00
- Plan dir: docs/plans/remove-legacy-metadata/phase-03
## SUMMARY
Replaced legacy backend/driver result usage dictionaries with explicit optional model identity, removed legacy result-usage parsers and constants, preserved all normalized telemetry collectors across agy/claude/codex/pi, and verified execution outcomes.
## FILES MODIFIED
| Action | Path | Change |
| --- | --- | --- |
| M | server/src/refract/backends/__init__.py | Replace usage with model on BackendResult; delete USAGE_KEYS, _usage_value, _usage_dict |
| M | server/src/refract/backends/agy.py | Replace legacy usage parsing with stream model extraction; pass model to BackendResult |
| M | server/src/refract/backends/claude.py | Replace legacy usage parsing with model extraction; pass model to BackendResult |
| M | server/src/refract/backends/codex.py | Pass parser collector model_name to BackendResult; delete legacy usage parser |
| M | server/src/refract/backends/pi.py | Replace legacy usage parsing with stream model extraction; pass model to BackendResult |
| M | server/src/refract/drivers.py | Replace usage with model on DriverResult and map from BackendResult.model |
| M | server/src/refract/execution.py | Read model identity directly from DriverResult.model without legacy usage dictionary access |
| M | server/tests/test_execution.py | Update test cases for model parameter and add context capacity fallback test |
| M | server/tests/test_streaming_backends.py | Add tests for model identity replacement, adapter streaming/cache, and cancellation precedence |
| M | docs/plans/remove-legacy-metadata/phase-03/notes.md | Append decision and test evidence for Tasks 1, 2, and 3 |
| M | docs/plans/remove-legacy-metadata/phase-03/journal.md | Record Implementation Response ERP block |
## NOTES
- docs/plans/remove-legacy-metadata/phase-03/notes.md (## Task 1, ## Task 2, ## Task 3)
## SPEC COMPLIANCE
- Meets Spec? YES - All Phase 3 requirements satisfied with full verification passing.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Coordinator Inspection and Fresh Verification

Worker returned TASK_COMPLETE and reports 966 Python tests passed, 15 live deselected, and both plugin checks passed. Changed product/test paths match the declared Phase 3 set; test_smoke.py was not modified. HEAD remains phase base f8fd25305edd64a668d5f9cc9cb07406f6d9edba, and diff check passes. Worker-supplied timestamps are reported evidence, not independently verified orchestration times.

Coordinator inspected the result-type, driver/execution, four-adapter and test diffs. The task-2 evidence records an incidental generator TypeError rather than establishing pre-refactor passing characterization. Clarify/recover actual characterization evidence before specification acceptance; do not infer it from the final passing suite. The audit notes also name from_legacy_row although the accepted converter is convert_schema15_metadata; verify the concrete reference inventory before acceptance.

Fresh coordinator task `b94669b28` is running the three exact checks, with logs `/tmp/refract-metadata-phase03-coordinator-{python,session,contracts}.log` and a 600-second Python bound. Await terminal notification without polling. No checkpoint or independent review yet.

## Implementation Response (Evidence Correction)

# EXTERNAL RESPONSE
## META
- Phase: Phase 3
- Started: 2026-10-27T16:00:00+07:00
- Finished: 2026-10-27T16:55:00+07:00
- Plan dir: docs/plans/remove-legacy-metadata/phase-03
## SUMMARY
Corrected audit reference inventory, classified all remaining keys and removed symbols, and documented process evidence gaps honestly without source modifications.
## FILES MODIFIED
| Action | Path | Change |
| --- | --- | --- |
| M | docs/plans/remove-legacy-metadata/phase-03/notes.md | Append evidence correction, reference inventory, and process gap disclosures |
| M | docs/plans/remove-legacy-metadata/phase-03/journal.md | Append updated Implementation Response ERP block |
## NOTES
- docs/plans/remove-legacy-metadata/phase-03/notes.md (## Evidence Correction and Audit Inventory)
## SPEC COMPLIANCE
- Meets Spec? WITH_DEBT - All functional requirements and checks pass; debt reflects missing pre-refactor characterization log and lack of behavioral test-first RED beyond constructor keyword failure.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Implementation Response (Test-First Reconstruction)

# EXTERNAL RESPONSE
## META
- Phase: Phase 3
- Started: 2026-10-27T16:00:00+07:00
- Finished: 2026-10-27T17:15:00+07:00
- Plan dir: docs/plans/remove-legacy-metadata/phase-03
## SUMMARY
Completed test-first behavioral reconstruction of all Phase 3 adapter model extraction routes, removed newly orphaned imports, and verified all three checks.
## FILES MODIFIED
| Action | Path | Change |
| --- | --- | --- |
| M | server/src/refract/backends/__init__.py | Replace usage with model on BackendResult; delete USAGE_KEYS, _usage_value, _usage_dict |
| M | server/src/refract/backends/agy.py | Replace legacy usage parsing with stream model extraction; pass model to BackendResult |
| M | server/src/refract/backends/claude.py | Replace legacy usage parsing with model extraction; pass model to BackendResult |
| M | server/src/refract/backends/codex.py | Pass parser collector model_name to BackendResult; delete legacy usage parser |
| M | server/src/refract/backends/pi.py | Replace legacy usage parsing with stream model extraction; pass model to BackendResult |
| M | server/src/refract/drivers.py | Replace usage with model on DriverResult; map model; remove orphaned field import |
| M | server/src/refract/execution.py | Read model identity directly from DriverResult.model without legacy usage dictionary access |
| M | server/tests/test_execution.py | Update test cases for model parameter and add context capacity fallback test |
| M | server/tests/test_streaming_backends.py | Add behavioral tests for all model extraction routes, adapter streaming/cache, and cancellation precedence |
| M | docs/plans/remove-legacy-metadata/phase-03/notes.md | Append decision notes, reference inventory, and NEW test-first reconstruction evidence |
| M | docs/plans/remove-legacy-metadata/phase-03/journal.md | Record Implementation Response ERP blocks |
## NOTES
- docs/plans/remove-legacy-metadata/phase-03/notes.md (## NEW Test-First Reconstruction and Behavioral Regression Evidence)
## SPEC COMPLIANCE
- Meets Spec? YES - Complete behavioral test-first RED to GREEN evidence established across all extraction routes, with zero debt and all checks passing.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Evidence Correction and Reconstruction

Initial fresh coordinator task `b94669b28` passed 966 Python tests, 15 live deselected, in 131.21 seconds; both plugin checks exited 0. This verified the initial tree but did not resolve process evidence gaps.

Evidence-only correction `2a08d6d4-82ca-4e64-860b-521f1cab321c` confirmed missing historical characterization/behavioral RED and corrected the reference inventory. Its WITH_DEBT claim was not accepted: required evidence cannot be waived as debt. Second bounded specification correction `3e3bb87b-aa0d-4424-8d8b-2cd7a79f6b5d` reconstructed uncharacterized behavior test-first, explicitly labeling new evidence, and reports 967 tests passed, 15 live deselected, both plugin checks passed. Notes now include passing characterization and assertion-level RED for Agy/Pi extraction, followed by a test covering every extraction route and driver/execution propagation. The newly orphaned drivers.py field import was removed. All modified paths remain within scope; diff check passes. Both automatic specification-fix batches are consumed.

Coordinator fresh task `bbc795552` is running all three exact checks against the reconstructed tree. Logs: `/tmp/refract-metadata-phase03-reconstructed-{python,session,contracts}.log`. Await terminal notification without polling. No acceptance checkpoint or independent review before validation finishes.

## Reconstructed-tree Specification Gate

Fresh coordinator task `bbc795552` passed: 967 Python tests, 15 live deselected, in 132.34 seconds; both plugin checks exited 0. Logs: `/tmp/refract-metadata-phase03-reconstructed-{python,session,contracts}.log`. No source changes occurred during verification, diff check passed, and no active job remained. All changed paths match the Phase 3 declaration.

Coordinator specification status: PASS for review admission. Both result types now carry optional model identity without usage dictionaries, legacy-only parsers/constants are deleted, and execution reads explicit identity. Necessary native collector parsing and transports are unchanged. Existing and added fixtures cover normalized consumption/cache/context, final-only paths, missing observations, model fallback without invented capacity, cancellation and failures. Reconstruction appended assertion-level RED/GREEN and characterization evidence rather than claiming historical test order. The corrected reference inventory separates migration inputs, provider collector inputs, and canonical normalized/runtime fields. Independent review must still judge correctness and completeness of these changes.

## Quality Review

Read-only job `cce694f8-ae04-4887-8453-98aca8f64ce5` reviewed `refs/plans/remove-legacy-metadata/phase-03/base..edf47b7af89dc3a15034563e613a0cb8a04bf0fb`. Status: PASS. No correctness, security, blocking compliance findings, or debt. It confirmed bridge/helper removal, explicit model propagation, configured fallback without capacity invention, unchanged normalized collectors/final-only/cache/transport/cancellation/failure behavior, unchanged provider fixtures, and valid remaining provider/migration/native reads.

Reviewer acknowledged reconstruction evidence is new and does not establish historical test-first execution across every route. It accepted the appended characterization, assertion-level Agy/Pi RED/GREEN, and broader extraction/propagation regressions. Full checks were not independently rerun during review. No writes, Git changes, operator access, live probes, services, deployment, or Phase 4 work occurred.

Coordinator confirmed reviewed HEAD unchanged, no active job, and only its expected latest_review handover edit dirty. Final edits are coordination-only; product remains identical to the freshly verified checkpoint. Phase 3 is accepted, with no consolidation or later-phase execution.

## Review Result

- Spec Status: PASS
- Quality Status: PASS
- Debt: none
- Next: stop; obtain explicit Phase 4 authorization

## Final Checkpoint

- Phase base ref: refs/plans/remove-legacy-metadata/phase-03/base
- Phase implementation ref: refs/plans/remove-legacy-metadata/phase-03/impl
- Plan commit ref: pending
- Accepted product checkpoint: edf47b7af89dc3a15034563e613a0cb8a04bf0fb
- State checkpoint: final coordination checkpoint captured by phase implementation ref

Phase refs retain reviewed evidence after final plan consolidation.
