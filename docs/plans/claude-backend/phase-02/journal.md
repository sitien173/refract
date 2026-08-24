<!-- ccg-shared-version: 10.0.3 -->

# Phase 2 — Journal: Driver compiles claude argv and dispatches explicitly

## META

- Plan: docs/plans/claude-backend/PLAN.md
- Implementation Profile: openai
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: c3b03ea0-daf7-4636-bca9-9938b7d5f11e
- Review Job: 3f8f232e-a2fb-4cf3-89a7-3dc8086c712c
- Started: 2026-08-24
- Finished: 2026-08-24T11:15:34+07:00

## Implementation Response

<!-- Worker appends the full `# EXTERNAL RESPONSE` block here. -->

# EXTERNAL RESPONSE
## META
- Phase: 2 / Started: 2026-08-24 / Finished: 2026-08-24T11:15:34+07:00 / Plan dir: docs/plans/claude-backend
## SUMMARY
Wired Claude into configuration and planning allowlists, compiled its policy argv, and added explicit Claude driver dispatch with regression coverage.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | `src/openmcp/config.py` | Allowed `claude` targets. |
| Modified | `src/openmcp/planning.py` | Allowed Claude targets in execution plan snapshots. |
| Modified | `src/openmcp/drivers.py` | Compiled Claude policy flags and added explicit Claude/unknown-backend dispatch. |
| Modified | `tests/test_config.py` | Added Claude config loading and reserved-argument coverage. |
| Modified | `tests/test_smoke.py` | Added Claude argv, resume, compilation, dispatch, and fallback tests. |
| Modified | `docs/plans/claude-backend/phase-02/notes.md` | Recorded task decisions and verification evidence. |
| Modified | `docs/plans/claude-backend/phase-02/journal.md` | Recorded completion metadata and this implementation response. |
## NOTES
- phase-02/notes.md (## Task 1, ## Task 2, ## Task 3, ## Task 4)
## SPEC COMPLIANCE
- Meets Spec? YES — scoped verification passed (104 tests), the Claude plan snapshot round-trips, and the full suite has only the four documented pre-existing server timeout failures.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Quality Review

# CODE QUALITY REVIEW
- Status: PASS_WITH_DEBT
- Findings: LOW, tests/test_smoke.py:441, Replacing the new-session invocation removed coverage that `--resume` is absent without a session. Add a separate empty-`SESSION_ID` argv assertion while retaining the resume assertion.
- Scope checked: src/openmcp/config.py, src/openmcp/planning.py, src/openmcp/drivers.py, tests/test_config.py, tests/test_smoke.py

## Coordinator Verification

The worker reported YES on spec. That claim held. Fresh evidence at `d49d614`,
clean tree, synced venv:

| Command | Result |
|---|---|
| `uv run pytest tests/test_config.py tests/test_smoke.py tests/test_planning.py -q` | 104 passed |
| `uv run pytest -q` | 4 failed, 167 passed, 2 deselected |

The four failures are the documented `tests/test_server.py` timeout-contract
failures predating this plan. Untouched by this phase.

Every acceptance criterion was checked against the committed source. The
execution plan round-trip criterion had no dedicated test in `test_planning.py`,
so it was verified directly: `_parse_targets` accepts a claude target and
`_target_args` compiles it to
`('--verbose', '--safe-mode', '--strict-mcp-config', '--system-prompt', 's',
'--tools', 'Read,Grep,Glob', '--model', 'm', '--effort', 'high')`, matching the
DESIGN.md order exactly.

The pi arm moved from a bare `else` to an explicit `elif target.backend == "pi"`.
Unknown backends now return `TARGET_FATAL` with `invalid_args` instead of
reaching pi. Routing for `agy`, `codex`, and `pi` is otherwise byte-identical.

`validate_target_args` was left unchanged, as specified. Its existing `--` check
at `config.py:344` already covers claude; the new parametrize case is a
regression guard only.

## Review Result

- Spec Status: PASS
- Quality Status: PASS_WITH_DEBT
- Debt: one LOW finding, closed in this phase rather than carried. Folding the
  `--resume` assertion into the Phase 1 argv test had removed coverage that a
  new session omits `--resume`. Fixed directly as a single-file test addition;
  no fix job was needed for a LOW non-blocking finding.
- Carried into Phase 3: nothing.

## Final Commit

- Implementation: `aa75fa6 feat(drivers): route claude targets through the claude adapter`
- Implementation notes: `d49d614 chore(plan): record phase 2 implementation notes`
- Debt fix: `fix(tests): assert claude new-session argv omits --resume`
- State record: this journal update's commit
