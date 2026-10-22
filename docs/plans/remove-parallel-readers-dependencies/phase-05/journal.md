<!-- refract-shared-version: 1.2.0 -->

# Phase 5 — Journal: Plugin contract, versions, and changelog

## META

- Plan: docs/plans/remove-parallel-readers-dependencies/PLAN.md
- Implementation Profile: implement
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: 697c5b77-2e46-47bd-9164-309db804c471
- Review Job: d4a066a9-6efc-4a20-b95c-165e7cda44ce FAIL; a9298ba4-d496-4815-9949-7db8a51aa44b PASS
- Started: 2026-10-22T19:01:00+07:00
- Finished: 2026-10-22T19:02:09+07:00

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase 5 / Started 2026-10-22T19:01:00+07:00 / Finished 2026-10-22T19:02:09+07:00 / Plan dir docs/plans/remove-parallel-readers-dependencies
## SUMMARY
Updated the plugin contract and tests, release versions, and changelog for 2.0.0; completion is blocked by verification failures in files outside the permitted edit list.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | plugin/skills/coordinating-multi-model-work/references/tool-contract.md | Removed dependency surface and documented reduced summary, cancellation response, FIFO admission, and unknown-argument behavior |
| Modified | plugin/skills/coordinating-multi-model-work/SKILL.md | Replaced reader/writer/session-fair admission statement |
| Modified | plugin/tests/test-contracts.sh | Updated reduced-surface and release assertions; added removed-surface absence checks |
| Modified | plugin/.claude-plugin/plugin.json | Set version to 2.0.0 |
| Modified | .claude-plugin/marketplace.json | Set plugin version to 2.0.0 |
| Modified | server/pyproject.toml | Set project version to 2.0.0 |
| Modified | server/uv.lock | Set refract package version to 2.0.0 only |
| Modified | CHANGELOG.md | Added the 2.0.0 release notes and pre-restart configuration instruction |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-05/notes.md | Recorded task decisions and verification evidence |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-05/journal.md | Appended this ERP response |
## NOTES
- phase-05/notes.md (## Task 1, ## Task 2, ## Task 3)
## SPEC COMPLIANCE
- Meets Spec? NO — plugin tests, version checks, and `git diff --check` pass, but the server suite fails because an unallowlisted test asserts version 1.0.0; the required residue check also finds removed-surface strings in unallowlisted tests. No files outside the phase allowlist were changed.
## CLARIFICATIONS NEEDED
Please authorize updates to the affected existing tests (`server/tests/test_smoke.py`, `server/tests/test_execution.py`, `server/tests/test_dashboard.py`, and relevant `server/tests/test_server.py` assertions), or revise the allowed-files/Done When constraints.
## NEXT
BLOCKED

## Review Response

<!-- Coordinator appends the independent review response here. -->

## Coordinator Evidence

- Job 697c5b77 BLOCKED: server/tests/test_smoke.py asserted version 1.0.0 and residue appeared in unallowlisted tests.
- Coordinator resolution in 4ac9e08: test_smoke.py version assertions to 2.0.0; test_server.py `_stub_job_record` returns `{}` instead of the removed access_mode key. Remaining residue is rejection tests in test_config.py and test_server.py, absence assertions in test_server.py, test_execution.py, test_dashboard.py, and fixture prompt text in server/tests/fixtures/usage/pi.jsonl. The phase prompt residue list was widened from PLAN.md to name the Phase 2 and Phase 3 rejection tests.
- Review d4a066a9 FAIL: Medium, weakened version guards in test-contracts.sh. Coordinator fix 7618b76 and ac0024e restored strict parity and synced .codex-plugin/plugin.json, plugin/shared markers, and plugin/package.json to 2.0.0.
- Fresh checks: plugin run.sh 0; pytest 543 passed, 3 deselected; vitest 0/202 failed; git diff --check clean.
- Review a9298ba4 PASS, no findings.
