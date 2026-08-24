<!-- ccg-shared-version: 10.0.3 -->

# Phase 3 — Journal: Direct-invocation API accepts claude

## META

- Plan: docs/plans/claude-backend/PLAN.md
- Implementation Profile: openai
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: a8c29e2c-c388-486c-ac72-7348b7e34093
- Review Job: e7235c0b-2ccc-4a4c-b296-c83d939d955f
- Started: 2026-08-24
- Finished: 2026-08-24T11:25:19+07:00

## Implementation Response

<!-- Worker appends the full `# EXTERNAL RESPONSE` block here. -->

# EXTERNAL RESPONSE
## META
- Phase: 3 / Started: 2026-08-24 / Finished: 2026-08-24T11:25:19+07:00 / Plan dir: docs/plans/claude-backend
## SUMMARY
Extended the direct-invocation runner and server API for Claude, added explicit dispatch and fallback handling, and verified live execution.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | `src/openmcp/backend_runner.py` | Added Claude executor injection, dispatch, and unknown-backend failure handling. |
| Modified | `src/openmcp/server.py` | Accepted Claude in `run` and injected its executor. |
| Modified | `tests/test_smoke.py` | Added compatibility-runner Claude and unknown-backend tests. |
| Modified | `tests/test_live_backends.py` | Added the live Claude PONG test. |
| Modified | `docs/plans/claude-backend/phase-03/notes.md` | Recorded task decisions and verification evidence. |
| Modified | `docs/plans/claude-backend/phase-03/journal.md` | Recorded completion metadata and this implementation response. |
## NOTES
- phase-03/notes.md (## Task 1, ## Task 2, ## Task 3, ## Task 4)
## SPEC COMPLIANCE
- Meets Spec? YES — live Claude execution passed; focused tests passed; full-suite failures are exactly the four documented pre-existing server timeout failures.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Quality Review

# CODE QUALITY REVIEW
- Status: PASS_WITH_DEBT
- Findings: LOW, tests/test_smoke.py:378, The intentional invalid `Literal` argument will fail static checking; use `cast(BackendName, "unknown")` (or a narrow documented ignore). The early-return completion-log asymmetry is not a finding.
- Scope checked: src/openmcp/backend_runner.py, src/openmcp/server.py, tests/test_smoke.py, tests/test_live_backends.py

## Coordinator Verification

The worker reported YES on spec. That claim held. Fresh evidence at `94bd24f`,
clean tree, synced venv:

| Command | Result |
|---|---|
| `uv run pytest -q` | 4 failed, 170 passed, 3 deselected |
| `uv run pytest -m live -k claude -q` | 1 passed |

The live test ran against the real installed `claude` 2.1.220 rather than
skipping. That is the first end-to-end proof of the backend: real subprocess,
real print-mode JSON, real session id, PONG returned.

The four failures are the documented `tests/test_server.py` timeout-contract
failures predating this plan. Untouched by this phase.

Annotations in both changed modules use `from __future__ import annotations`, so
they resolve as strings. Checked directly:

- `server.run` backend annotation is `"Literal['agy', 'codex', 'pi', 'claude']"`.
- `backend_runner.BackendName` resolves to `('agy', 'codex', 'pi', 'claude')`.
- The `claude_executor` default resolves to `openmcp.backends.claude`.

The pi arm moved from a bare `else` to an explicit `elif backend == "pi"` and
keeps `args=("--approve",)`. The claude arm passes no `args`, so no target policy
leaks into the compatibility runner. Unknown backends now return a
`success: False` dict instead of reaching pi.

Task 3 required no work. Phase 1 had already added the claude import and the
`ClaudeParams` transport-only assertion; both still pass.

The implementation left two trailing blank lines at the end of
`tests/test_live_backends.py`. Stripped before commit.

## Review Result

- Spec Status: PASS
- Quality Status: PASS_WITH_DEBT
- Debt: one LOW finding, closed in this phase rather than carried. The
  unknown-backend test passed a bare `"unknown"` string to a `BackendName`
  parameter. Now `cast(BackendName, "unknown")` with a comment stating the
  deliberate misuse. No static type checker is configured in this repository, so
  the finding had no failure mode today; the cast documents intent regardless.
- Carried into Phase 4: nothing.

## Final Commit

- Implementation: `d38b8a9 feat(runner): support claude in the direct-invocation API`
- Implementation notes: `94bd24f chore(plan): record phase 3 implementation notes`
- Debt fix: `2a22dc5 fix(tests): cast the deliberate invalid backend literal`
- State record: this journal update's commit
