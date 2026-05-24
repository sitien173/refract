# Phase 1 — Live agy + codex integration test

- Status: DONE
- Owner: Codex
- Started: 2026-05-23T10:59+07:00
- Finished: 2026-05-23T12:18+07:00

## Route
- Reason: back-side — server-side pytest test + subprocess plumbing.
- Done When:
  - `cd openmcp && pytest -q` passes; 2 live tests deselected.
  - `cd openmcp && pytest -m live -v` runs the 2 tests (pass on CLI env, skip with `missing_cli`/`bad_cd` otherwise).
  - No `PytestUnknownMarkWarning` for `live`.
- Files:
  - Modify: `openmcp/pyproject.toml`
  - Create: `openmcp/tests/test_live_backends.py`

## Files Modified
| Action | Path | Change |
| ------ | ---- | ------ |
| Updated | `openmcp/pyproject.toml` | Registered `live` marker + `addopts = "-m 'not live'"`. |
| Created | `openmcp/tests/test_live_backends.py` | Two `@pytest.mark.live @pytest.mark.asyncio` tests for agy + codex with PONG sentinel; FATAL `missing_cli`/`bad_cd` → skip. |
| Updated | `openmcp/src/openmcp/backends/codex.py` | **Beyond spec.** Added stdout-regex + recent-session JSONL fallbacks for SESSION_ID extraction; exposed by live codex returning OK with empty SESSION_ID. |
| Updated | `openmcp/tests/test_smoke.py` | **Beyond spec.** Regression unit test for the codex session-file fallback. |

## Commits
- phase-1.task-1: `6ebd9b5` register live marker default skip
- phase-1.task-2: `3ec7836` add live backend integration tests
- phase-1.task-3: `8f0d381` verify live runs and codex session fallback
- phase-1.task-3: `032f1f9` add codex session fallback regression test

## Review
- Spec Status: PASS — both gates pass (`pytest -q`: 10 passed / 2 deselected; `pytest -m live -v`: 2 passed / 10 deselected). No marker warning.
- Quality Findings:
  - MEDIUM — `src/openmcp/backends/codex.py:_extract_session_id_from_latest_session` heuristic match (cwd + first-80-char prompt prefix, 30 s window) could mis-attribute under parallel codex runs in the same cwd with similar prompt prefixes.
  - LOW — `_same_path` case-insensitive posix fallback is forgiving but acceptable.
- Final Status: PASS_WITH_DEBT — fix is real bug closure; heuristic is documented in `notes/phase-1.task-3.md`; flagged to user.

## Decisions
- See `notes/phase-1.task-1.md`, `notes/phase-1.task-2.md`, `notes/phase-1.task-3.md`.
- Cross-task: scope expanded beyond the original "add integration test" because the live run surfaced an actual codex SESSION_ID extraction gap. Two extra commits address it; user notified during review.

## Handoff
- User to confirm acceptance of the codex.py session-fallback (commits `8f0d381` + `032f1f9`) or request a revert leaving only the test.
- Optional follow-up: tighten the JSONL match (argv/exec-time fingerprint) to mitigate the MEDIUM finding.
