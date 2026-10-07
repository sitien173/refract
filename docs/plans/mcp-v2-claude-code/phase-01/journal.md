<!-- ccg-shared-version: 11.0.6 -->

# Phase 1 Journal: Heartbeat wait and progress-token probe

## META

- Plan: docs/plans/mcp-v2-claude-code/PLAN.md
- Implementation Profile: implement
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: bda29aad-a34f-4cfb-a0cb-b7b9e0d416b6
- Review Job: pending
- Started: 2026-10-07
- Finished: 2026-10-07T13:19:00+07:00
- Consult skipped: confirmed plan supplies exact behavior; no unresolved design choice.

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase: Phase 1
- Started: 2026-10-07T13:04:08+07:00
- Finished: 2026-10-07T13:19:00+07:00
- Plan dir: docs/plans/mcp-v2-claude-code

## SUMMARY
Implemented Phase 1 heartbeat wait and progress-token logging while preserving v1 MCP interface.

## FILES MODIFIED
| Action | Path | Change |
| Modify | src/openmcp/server.py | Raise wait timeout, add heartbeat interval, add progress token logging |
| Modify | tests/test_server.py | Add deterministic tests for heartbeat wait and progress token presence |
| Modify | docs/plans/mcp-v2-claude-code/phase-01/notes.md | Record decisions and test evidence for Tasks 1 to 3 |
| Modify | docs/plans/mcp-v2-claude-code/phase-01/journal.md | Update META and record external response |

## NOTES
- docs/plans/mcp-v2-claude-code/phase-01/notes.md (## Task 1, ## Task 2, ## Task 3)

## SPEC COMPLIANCE
- Meets Spec? YES - All Phase 1 requirements implemented with passing deterministic tests; live acceptance pending coordinator execution.

## CLARIFICATIONS NEEDED
None

## NEXT
TASK_COMPLETE

## Quality Review

### Review 1

- Job: 9a6a1cc8-2652-4106-95c5-81df08e4b018
- Pinned revision: 9591691a9eba1786b6306366fe1c318a26d53d0e
- Status: FAIL
- P1, src/openmcp/server.py:237: Running heartbeats repeat progress=0.0 with total=1.0. MCP progress must increase. Use an increasing heartbeat counter without a known total and test the values.
- P2, src/openmcp/server.py:131-138: The token detector accepts SDK-normalized values that the dispatcher ignores, including boolean and floating-point wire tokens and a snake-case-only wire key. Detect presence using the SDK's accepted raw wire-token rules and add tests using actual metadata extraction.
- No reviewer writes. The handover difference is the coordinator's post-submission job-reference update.
- V1 shapes, timeout cap, immediate return, and cancellation cleanup were preserved.

### Review 1 Remediation: Fix Cycle 1

- Started: Not recorded
- Finished: 2026-10-07T13:29:15+07:00
- Status: Implemented and locally verified; independent re-review pending.
- P1: Heartbeat progress now begins consistently at 0 with no total and increments by 1 for each running heartbeat. Focused test asserts exact values and omitted total.
- P2: Token-presence logging now checks raw request params for the exact `progressToken` wire key and `str`/`int` types, excluding bool. Tests exercise SDK `_extract_meta` normalization and raw values: string/integer including empty string/zero; bool, float, snake-case-only, and absent metadata.
- RED: focused command produced 3 failed / 7 passed. Precise failure lines are recorded in `notes.md` under Review Fix Cycle 1.
- GREEN: focused regression tests 11 passed / 27 deselected; server tests 38 passed; full tests 476 passed / 3 deselected.
- Live acceptance remains pending and coordinator-owned. No service restart or OpenMCP call performed.

### Review 2

- Job: bf400d69-1304-46bf-a5d8-3ce449791e29
- Range: f7adfe597d5e7a3bb6b429d123e0167e4c537560..98d0a5038a0d33bcaee20130d739d0ec5e7bd933
- Status: PASS for fix cycle 1; no findings or debt.
- Installed SDK 2.0.0 confirmed both blockers fixed, including accepted zero/empty-string tokens and rejected normalized invalid values.
- Reviewer made no writes. Only the coordinator's expected handover job-reference update was present.

### Coordinator Logging-Sink Finding

- H1 confirmed at 2026-10-07T06:40:08Z: `_JsonFormatter` emits progress_token_present as `[REDACTED]`; `_TextFormatter` omits the field.
- Reproduction: `uv run --extra dev python -I -c` constructs a logging record carrying progress_token_present=True and formats it with both production formatters.
- Root cause: src/openmcp/logging_setup.py:175-177 redacts every key containing token before inspecting its boolean type; the text formatter at lines 251-256 renders context fields only.
- The user approved adding src/openmcp/logging_setup.py and tests/test_logging.py to Phase 1 on 2026-10-07.
- Fix cycle 2 must preserve only this exact boolean field while leaving token-value redaction intact. This blocks the mandatory live observability acceptance.
- The user authorized waiting through normal timeouts for all jobs in this plan. Failures, unresolved questions, and review-fix bounds still stop execution.

### Fix Cycle 2 Remediation

- Finished: 2026-10-07T13:46:12+07:00
- Status: Implemented and locally verified; independent re-review pending.
- JSON formatter preserves the exact `progress_token_present` field only for direct bool-valued extras; non-bools continue through generic sensitive-key redaction.
- Text formatter includes only that exact field when its value is a bool; it does not serialize other extras.
- Added formatter regressions for `True`, `False`, non-boolean token content, unrelated secret fields, and message redaction.
- RED: 4 failed / 1 passed / 9 deselected, with JSON redacting both booleans and text omitting both. Exact evidence is in `notes.md` under Review Fix Cycle 2.
- GREEN: focused regressions 5 passed / 9 deselected; requested server/logging tests 52 passed; full suite 481 passed / 3 deselected; `git diff --check` passed.
- Live acceptance remains pending coordinator work. No daemon restart or OpenMCP call performed.

## Coordinator Verification

- Fix cycle 1, fresh coordinator run: `uv run --extra dev pytest tests/test_server.py -q` passed, 38 tests.
- Fix cycle 1, fresh coordinator run: `uv run --extra dev pytest -q` passed, 476 tests, 3 deselected.
- `git diff --check` passed.
- No active project job after the fix. Changed paths match the declared implementation files plus coordinator-owned handover metadata.
- Fix cycle 2, fresh coordinator run: `uv run --extra dev pytest tests/test_server.py tests/test_logging.py -q` passed, 52 tests.
- Fix cycle 2, fresh coordinator run: `uv run --extra dev pytest -q` passed, 481 tests, 3 deselected.
- Original formatter reproduction passed at 2026-10-07T06:48:05Z: JSON preserved progress_token_present=true and text emitted progress_token_present=True.
- Independent re-review and live acceptance remain pending.

## Review Result

- Spec Status: PENDING
- Quality Status: PENDING
- Debt: none

## Live Acceptance

- Client: Claude Code 2.1.292.
- Pre-restart service state: active; MainPID 2443; started Tue 2026-10-06 11:22:10 +07.
- Dashboard preflight: `npm --prefix web test` passed, 196 tests in 18 files. Pre-existing React act warnings were emitted; no dashboard edit was made.
- Daemon restart: pending after independent review and no active jobs.
- Main-conversation six-minute wait: pending.
- Subagent six-minute wait: pending.
- Progress token log: pending.
- Unknown job error received by Claude Code: pending.

## Final Checkpoint

- Phase base ref: refs/plans/mcp-v2-claude-code/phase-01/base
- Phase implementation ref: refs/plans/mcp-v2-claude-code/phase-01/impl
- Plan commit ref: pending
- State checkpoint: pending
