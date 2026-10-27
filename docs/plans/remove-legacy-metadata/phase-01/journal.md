<!-- refract-shared-version: 2.0.0 -->

# Phase 1 Journal: Canonical Contract and Conversion Boundary

## META

- Plan: docs/plans/remove-legacy-metadata/PLAN.md
- Implementation Profile: implement
- Consultation Profile: n/a
- Review Profile: review
- Implementation Jobs: 51df334b-64d6-4ce6-8703-92b8019565b3; 0dfde781-a980-4fa0-8288-7fbdf17c2456; bb328b2d-8fe8-4a0a-aa41-974cf9fc84fd
- Review Jobs: 4d7ff3ad-fea4-4bd5-87a8-458bc892438a; b169b574-ba95-405b-a505-9b85e1f7b8a1
- Started: 2026-10-27
- Finished: 2026-10-27; Phase 1 accepted after authorized correction

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase / Started / Finished / Plan dir: Phase 1 / 2026-10-27 / 2026-10-27 / docs/plans/remove-legacy-metadata
## SUMMARY
Implemented strict grouped metadata types, internal-to-public telemetry projection, and a pure schema-15 converter that preserves valid normalized telemetry without fabricating timestamps.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Added | server/src/refract/result_metadata.py | Strict canonical models, explicit public projection, and historical conversion helper |
| Added | server/tests/test_result_metadata.py | Exact-shape, strict validation, projection boundary, and conversion tests |
| Modified | server/tests/test_telemetry.py | Assert public projection excludes internal accounting state |
| Modified | docs/plans/remove-legacy-metadata/phase-01/notes.md | Task decisions and test evidence |
| Modified | docs/plans/remove-legacy-metadata/phase-01/journal.md | Implementation response |
| Tool-modified during required `refract ask` | docs/plans/remove-legacy-metadata/.handover.md | Ask integration recorded implementation job reference; worker did not edit or restore coordinator-owned handover |
## NOTES
- docs/plans/remove-legacy-metadata/phase-01/notes.md (## Task 1, ## Task 2, ## Task 3)
## SPEC COMPLIANCE
- Meets Spec? WITH_DEBT — Implementation and checks pass, but Task 1 first test run was an import-time failure, not valid behavioral RED evidence. The required `refract ask` also automatically changed coordinator-owned `.handover.md`, outside the allowed files. Worker did not modify or restore that file; coordinator must resolve the handover state.
## CLARIFICATIONS NEEDED
None
## NEXT
BLOCKED

# EXTERNAL RESPONSE — Batch 1 Resumption
## META
- Phase / Started / Finished / Plan dir: Phase 1 (Batch 1) / 2026-10-27 / 2026-10-27 / docs/plans/remove-legacy-metadata
## SUMMARY
Reconstructed strict canonical metadata validation and historical conversion test-first, fixed the reported measurement and historical coercion bugs, and passed all exact Phase 1 checks.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/src/refract/result_metadata.py | Reconstructed strict public validation and schema-15 converter; absent telemetry now returns no internal state |
| Modified | server/tests/test_result_metadata.py | Expanded behavior tests and failure-first evidence for canonical and historical validation |
| Modified | docs/plans/remove-legacy-metadata/phase-01/notes.md | Appended Batch 1 diagnoses, RED/GREEN evidence, and fresh verification |
| Modified | docs/plans/remove-legacy-metadata/phase-01/journal.md | Appended this resumption response |
## NOTES
- docs/plans/remove-legacy-metadata/phase-01/notes.md (Batch 1 Reconstruction Evidence; Tasks 1 and 3)
## SPEC COMPLIANCE
- Meets Spec? YES — Current Task 1 and Task 3 implementation has behavioral RED→GREEN evidence; strict measurement and historical checks are covered. Exact phase verification passed. No runtime/database wiring was added.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

# EXTERNAL RESPONSE: Batch 2 Specification Fixes
## META
- Phase / Started / Finished / Plan dir: Phase 1 Batch 2 / 2026-10-27 / 2026-10-27 / docs/plans/remove-legacy-metadata
## SUMMARY
Reconstructed canonical models test first from inert scaffolding, enforced strict quality provenance across boundaries, and passed all phase verification.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/src/refract/result_metadata.py | Strict quality provenance validation and minimal canonical models |
| Modified | server/tests/test_result_metadata.py | Comprehensive quality provenance tests across public and historical boundaries |
| Modified | docs/plans/remove-legacy-metadata/phase-01/notes.md | Appended Batch 2 TDD discard and redo and provenance evidence |
| Modified | docs/plans/remove-legacy-metadata/phase-01/journal.md | Appended Batch 2 response and scope correction |
## NOTES
- docs/plans/remove-legacy-metadata/phase-01/notes.md ## Batch 2 Reconstruction and Provenance Evidence: 2026-10-27
## SPEC COMPLIANCE
- Meets Spec? YES: Task 1 reconstructed test first. Quality provenance strictly preserved. Coordinator directly authored .handover.md without worker violation.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

Phase 1 completed. Journal: docs/plans/remove-legacy-metadata/phase-01/journal.md.

## Coordinator Specification Checks

- Changed product paths match Phase 1: result_metadata.py, test_result_metadata.py, and test_telemetry.py. telemetry.py itself remains unchanged.
- No runtime, JobResult, database, schema, dependency, or dashboard wiring changed.
- The handover job reference was written by the coordinator, not by refract ask. It is not a worker scope violation.
- Fix batch 1 corrected nested extra-field loss, token/percentage checks, absent internal state, and historical attribution coercion.
- Coordinator checks after batch 1 passed: 880 Python tests, 15 live tests deselected, and both plugin checks.
- Fix batch 2 addressed missing valued quality and reconstructed the previously untested Task 1 models from inert scaffolding. Notes retain original failures and superseding behavioral RED/GREEN evidence.
- Two automatic fix batches have been used. Any remaining blocking finding requires user instructions rather than another automatic implementation job.
- Final batch-2 coordinator verification passed: `(cd server && uv run --extra dev python -m pytest -m 'not live')` returned 922 passed, 15 deselected; both plugin checks passed. All commands exited zero. Evidence: /tmp/refract-metadata-phase01-final-python.log, /tmp/refract-metadata-phase01-final-session.log, /tmp/refract-metadata-phase01-final-contracts.log.
- Specification criteria passed: exact grouped shape, strict nested validation, unavailable historical defaults, normalized precedence, separated bookkeeping, original observation timestamps, and unchanged runtime/schema. Credible reconstruction evidence is recorded in the Batch 2 notes.

## Quality Review

Independent review `4d7ff3ad-fea4-4bd5-87a8-458bc892438a`, profile `review`, checked `refs/plans/remove-legacy-metadata/phase-01/base..02648531bc0282aa99ae7d1abe484467886ea16d`.

**Overall: FAIL**

High: `server/src/refract/result_metadata.py:48–53` silently repairs invalid recognized historical provenance. Input `{"telemetry":{"total_input_tokens":{"value":null,"quality":null}}}` succeeds and changes quality to `unavailable`. Explicit null quality should be rejected. The canonical model rejects the same measurement, so the two boundaries disagree.

Minimal correction: default quality only when its key is absent. Reject explicit null quality. Add public and historical regression cases across all seven measurements.

No optional findings. Reviewer accepted the superseding behavioral RED/GREEN reconstruction evidence. The reviewer did not rerun the supplied verification commands. Live wiring, migration execution, operator state, pre-existing defects, and later phases were excluded.

Coordinator reproduced the finding at the same code revision: historical conversion returned unavailable quality while canonical validation raised ValidationError. Review changed no product file or HEAD. The sole pre-existing working-tree modification during review was the coordinator-authored handover review-job reference.

Exact-checkpoint validation at `02648531bc0282aa99ae7d1abe484467886ea16d`: 922 Python tests passed, 15 live tests deselected; both plugin checks passed. HEAD and source stayed unchanged. These tests did not cover the blocking explicit-null case.

Two automatic fix batches were already used. No third implementation job was submitted. Await user authorization for one additional targeted fix and independent re-review.

# EXTERNAL RESPONSE — User-Authorized Targeted Correction
## META
- Phase / Started / Finished / Plan dir: Phase 1 targeted correction / 2026-10-27 / 2026-10-27 / docs/plans/remove-legacy-metadata
## SUMMARY
Fixed explicit-null quality normalization: unavailable measurements now default quality only when the field is absent, while explicit null is rejected for every canonical and historical measurement.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/tests/test_result_metadata.py | Added parameterized canonical and historical explicit-null quality regressions for all seven measurement fields |
| Modified | server/src/refract/result_metadata.py | Minimal absent-key-only unavailable quality default |
| Modified | docs/plans/remove-legacy-metadata/phase-01/notes.md | Appended targeted RED/GREEN and full-check evidence |
| Modified | docs/plans/remove-legacy-metadata/phase-01/journal.md | Appended this ERP response |
## NOTES
- docs/plans/remove-legacy-metadata/phase-01/notes.md (Targeted Review Correction: Explicit Null Historical Quality)
## SPEC COMPLIANCE
- Meets Spec? YES — Behavioral RED showed all seven historical cases accepting explicit null; GREEN and all exact Phase 1 checks passed. Missing quality on unavailable/null measurements remains accepted; valid provenance is unchanged.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Review Result

- Spec Status: PASS
- Quality Status: PASS
- Prior blocking finding: resolved by user-authorized correction.
- Debt: none.
- Next: stop after Phase 1. Phase 2 requires separate authorization.

## User-authorized Targeted Correction

The user replied `next` to the pending authorization request. This authorizes one additional targeted fix and independent re-review, not Phase 2 or another automatic correction batch. Resume reconciliation found no active jobs, attached branch `remove-legacy-metadata`, HEAD `02648531bc0282aa99ae7d1abe484467886ea16d`, and only coordinator changes to this journal and handover. Saved Phase 1 guidance remains implement and review.

H1: `_check_measurement` defaults explicit null quality as though absent | Predict: historical conversion accepts null quality while canonical validation rejects it | Evidence: coordinator reproduction recorded above | Result: confirmed. Require behavioral RED before the minimal correction.

## Targeted Correction Coordinator Validation

Implementation job `1ef9cc17-ef5a-44fa-af20-0d7a54af0b09` returned TASK_COMPLETE. Product delta is limited to the absent-key quality default and two seven-case regression tests. Existing missing-quality cases cover both empty and null-valued measurements across both boundaries. Behavioral RED records seven historical DID NOT RAISE failures before the source correction; canonical rejection already worked.

Fresh coordinator checks passed: 936 Python tests, 15 live tests deselected; both plugin checks passed. Commands are the three Phase 1 Verification Checks. Logs: `/tmp/refract-metadata-phase01-targeted-{python,session,contracts}.log`. Diff check passed. No runtime, schema, database, or API wiring changed. Specification PASS; independent quality re-review pending.

## Independent Re-review

Job `b169b574-ba95-405b-a505-9b85e1f7b8a1`, profile review, returned PASS for fix delta `02648531bc0282aa99ae7d1abe484467886ea16d..949bc7c3f7e75f66f5e577aba2f517d95f4cc8d2`. Prior High finding resolved; no findings or debt. Missing-quality defaults, valued validation, provenance, timestamps, and scope were accepted. Static review only; supplied tests were not independently rerun.

Coordinator verified the exact clean checkpoint before review: 936 tests passed, 15 live tests deselected, both plugin checks passed. Logs: `/tmp/refract-metadata-phase01-accepted-{python,session,contracts}.log`. Review changed no product file or HEAD. The sole review-time dirt was the coordinator-written handover job reference. Reviewer described the tree as clean; coordinator status is authoritative for that detail.

## Final Checkpoint

- Phase base ref: refs/plans/remove-legacy-metadata/phase-01/base
- Phase implementation ref: refs/plans/remove-legacy-metadata/phase-01/impl
- Accepted product checkpoint: `949bc7c3f7e75f66f5e577aba2f517d95f4cc8d2`
- Phase implementation ref captures final coordination checkpoint.
- Plan implementation ref: not written; Phases 2–4 remain unexecuted.
- Phase 1 accepted. Stop before Phase 2. No deployment or live migration authorized.

Phase refs retain evidence after final consolidation.
