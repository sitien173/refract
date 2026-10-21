<!-- refract-shared-version: 1.2.0 -->

# Phase 1 — Journal: Green baseline and backend usage capture

## META

- Plan: docs/plans/job-failover-metadata/PLAN.md
- Implementation Profile: implement
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: 8c78f2c9-b183-4fe4-8dbd-f99f6a0d812a (failed, timeout), ef1b67e3-1945-4617-b234-2fad20e0bc8d (continuation)
- Review Job: 1af8e191-33ae-4879-bd15-c4ea98f0ba1a (no tool budget), cab8d3c3-20e4-4f7f-9471-4d8301a6dc43 (target error), 4bb2ec26-8b74-43ed-8ad8-1c0dc1030c96 (completed)
- Started: 2026-10-21T14:49:37Z
- Finished: 2026-10-21T15:38:00Z

## Implementation Response


# EXTERNAL RESPONSE
## META
- Phase 1 / Started 2026-10-21T22:20:00+07:00 / Finished 2026-10-21T22:26:02+07:00 / Plan dir docs/plans/job-failover-metadata
## SUMMARY
Implemented fixture-backed usage parsing and normalization; phase remains blocked on web-suite stability and missing exact capture-command records.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/src/refract/backends/__init__.py | Added safe usage normalization helpers |
| Modified | server/src/refract/backends/claude.py | Parse Claude result usage and model/context metadata |
| Modified | server/src/refract/backends/codex.py | Parse Codex completed-turn usage |
| Modified | server/src/refract/backends/pi.py | Parse Pi assistant message usage |
| Modified | server/src/refract/backends/agy.py | Parse Agy result usage |
| Modified | server/web/src/screens/ProjectDetail.test.jsx | Wait for form readiness before submit |
| Created | docs/plans/job-failover-metadata/phase-01/notes.md | Task 1–4 decisions, evidence, field path table |
| Modified | docs/plans/job-failover-metadata/phase-01/journal.md | Implementation response and checkpoint |
## NOTES
- docs/plans/job-failover-metadata/phase-01/notes.md (## Task 1–4)
## SPEC COMPLIANCE
- Meets Spec? WITH_DEBT — Python tests pass; full web suite has intermittent failures and the three-consecutive-run requirement was not met; exact fixture capture commands were not available from the interrupted job.
## CLARIFICATIONS NEEDED
- Recover exact CLI capture commands if these must be recorded verbatim; fixtures were retained without recapturing.
## NEXT
BLOCKED

## Quality Review

Job 4bb2ec26-8b74-43ed-8ad8-1c0dc1030c96:

# CODE QUALITY REVIEW
- Status: PASS
- Findings: low, non-blocking, server/src/refract/backends/__init__.py, 20-32, Restrict `model_name` to `str` only and numeric usage keys to non-bool `int` directly instead of allowing `int` for `model_name` via `_usage_value` and re-checking `isinstance(value, bool)` in `_usage_dict`.
- Scope checked: server/src/refract/backends/{__init__,agy,claude,codex,pi}.py, server/src/refract/drivers.py, server/tests/test_streaming_backends.py, server/web/src/screens/ProjectDetail.test.jsx

## Review Result

- Spec Status: PASS. Worker BLOCKED items resolved by Coordinator: web suite passed 6 consecutive runs (203/203); capture commands reconstructed from backend argv in notes.md.
- Quality Status: PASS_WITH_DEBT
- Evidence: `uv run pytest -q` 548 passed, 3 deselected; `uv run pytest -q tests/test_streaming_backends.py` 18 passed; `npx vitest run` x6 203/203.
- Debt: `_usage_dict` type narrowing (low); owner Coordinator, fold into Phase 3 metadata work.
- Debt: fixture capture commands are reconstructed, not verbatim; owner human.

## Final Checkpoint

- Phase base ref: refs/plans/job-failover-metadata/phase-01/base
- Phase implementation ref: refs/plans/job-failover-metadata/phase-01/impl
- Plan commit ref: pending
- State checkpoint: temporary commit
