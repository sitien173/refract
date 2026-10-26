<!-- refract-shared-version: 2.0.0 -->

# Phase 1 — Journal: Server-side ask channel

## META

- Plan: docs/plans/worker-ask-coordinator/PLAN.md
- Implementation Profile: implement
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: 2a4b5980-2ea7-4fff-8b7a-ea3a33de1c89
- Review Job: pending
- Started: 2026-10-26T04:16:54Z
- Finished: 2026-10-26T04:44:00Z

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase: 1
- Started: 2026-10-26T04:16:54Z
- Finished: 2026-10-26T04:44:00Z
- Plan dir: docs/plans/worker-ask-coordinator
## SUMMARY
Implemented server-side ask channel with in-memory token registry, loopback POST /ask endpoint, ask timeout configuration, and worker environment injection across backend execution paths.
## FILES MODIFIED
| Action | Path | Change |
| --- | --- | --- |
| create | server/src/refract/ask.py | In-memory token registry with single pending question state and timeout/cancellation handling |
| modify | server/src/refract/config.py | Added ask_timeout_s daemon config setting with default and validation |
| modify | server/src/refract/dashboard.py | Added POST /ask loopback route with auth, conflict, and timeout handling |
| modify | server/src/refract/backends/__init__.py | Added env field to BackendParams |
| modify | server/src/refract/backends/_shell.py | Added env parameter and merging into os.environ at subprocess.Popen |
| modify | server/src/refract/backends/codex.py | Threaded env parameter to stream_shell_command_lines |
| modify | server/src/refract/backends/claude.py | Threaded env parameter to stream_shell_command_lines |
| modify | server/src/refract/backends/agy.py | Threaded env parameter to stream_shell_command_lines |
| modify | server/src/refract/backends/pi.py | Threaded env parameter to stream_shell_command_lines |
| modify | server/src/refract/drivers.py | Added env parameter to DriverRegistry.execute and BackendParams instantiation |
| modify | server/src/refract/execution.py | Added token issuance/revocation and env passing in TargetExecutor |
| modify | server/src/refract/runtime.py | Attached AskRegistry to Runtime and hooked cancellation to release pending asks |
| create | server/tests/test_ask.py | Unit tests for AskRegistry, env injection, and lifecycle revocation |
| modify | server/tests/test_dashboard.py | Route tests for POST /ask covering validation, auth, conflict, and timeout |
| modify | server/tests/test_config.py | Config validation tests for ask_timeout_s default and invalid values |
| modify | docs/plans/worker-ask-coordinator/phase-01/notes.md | Task notes for Tasks 1 through 4 |
| modify | docs/plans/worker-ask-coordinator/phase-01/journal.md | Appended implementation response |
## NOTES
- docs/plans/worker-ask-coordinator/phase-01/notes.md (## Task 1, ## Task 2, ## Task 3, ## Task 4)
## SPEC COMPLIANCE
- Meets Spec? YES - All phase tasks and acceptance criteria met with full test coverage and clean verification runs.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

# EXTERNAL RESPONSE
## META
- Phase: 1
- Started: 2026-10-26T05:19:07Z
- Finished: 2026-10-26T05:25:00Z
- Plan dir: docs/plans/worker-ask-coordinator
## SUMMARY
Fixed AskRegistry.ask to validate token and register pending question atomically under a single lock acquisition.
## FILES MODIFIED
| Action | Path | Change |
| --- | --- | --- |
| modify | server/src/refract/ask.py | Made token validation and pending question registration atomic under self._lock |
| modify | server/tests/test_ask.py | Added regression test verifying atomic validation and registration on token revocation |
| modify | docs/plans/worker-ask-coordinator/phase-01/notes.md | Appended Fix 1 task notes |
| modify | docs/plans/worker-ask-coordinator/phase-01/journal.md | Appended Fix 1 response block |
## NOTES
- docs/plans/worker-ask-coordinator/phase-01/notes.md (## Fix 1)
## SPEC COMPLIANCE
- Meets Spec? YES - Atomic lock acquisition prevents race condition between token revocation and question registration.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE



## Coordinator Validation After Authorized Fix 3

- User authorized one additional fix cycle with `next`.
- Implementation job: `7b68a442-eaf0-4f89-a083-042ca45eb269`.
- Fresh coordinator validation task: `bb3a483a4`.
- `cd server && uv run pytest -q`: 609 passed, 3 deselected in 133.12s; exit 0.
- `bash plugin/tests/run.sh`: passed; exit 0; three existing manifest warnings.
- Inspected Phase 1 delta against `refs/plans/worker-ask-coordinator/phase-01/base`.
- Authorized Fix 3 changed only the registry, ask tests, route tests, and phase notes/journal.
- Prior fixes and backend environment transport changes were preserved.
- Surrogate token and wrong-job route regressions now assert HTTP 403.
- Specification review: PASS for Phase 1; independent quality review pending.
- Phase 2 MCP changes and Phase 3 CLI/live probes remain out of scope.

## Quality Review

- Initial review: `b707e04f-8a71-43f4-8d52-ec9fe012d28a` reported PASS with two findings.
- Coordinator normalized the correctness race finding to FAIL. Fix 1 made validation and pending registration atomic.
- Reviewer also noted unbounded revoked-token retention. Non-blocking debt owner: Refract server maintainer, unless eliminated by the remaining fix.

## Review Result

- Spec Status: FAIL after Fix 2. Automatic two-cycle fix allowance exhausted. Independent re-review remains gated by this specification failure.
- H1: dashboard passes the global ask timeout unchanged; execution never checks it against the workflow timeout. A late ask can outlive its worker. Confirmed by tracing `dashboard.py` and `execution.py`.
- H2: `AskRegistry.cancel` releases pending requests but keeps the token active. Reproduction returned `token-valid-after-cancel True`. Runtime must revoke immediately, preventing a second ask during cancellation.
- H3: `secrets.compare_digest` rejects non-ASCII strings. Reproduction returned `TypeError` for a non-ASCII unknown token, instead of `AskAuthError`. HTTP must return 403.
- BackendParams uses a global ID-keyed environment map and custom lifecycle methods rather than the planned env field. Use a secret-safe dataclass field and update the exact field contract test. This is necessary implementation cleanup within the ask path, not unrelated refactoring.
- Fix 2 is the final automatic fix cycle. Re-review must cover both fixes and report remaining blocking findings.
- Debt: revoked-token retention, Refract server maintainer.
- Remaining blocking finding: `server/src/refract/ask.py` encodes supplied token and job identifiers with strict UTF-8. JSON permits an escaped lone surrogate such as `\ud800`; `token.encode("utf-8")` raises `UnicodeEncodeError`, escaping the route instead of returning the required 403 for an unknown token. The same problem applies to a supplied wrong-job identifier.
- Coordinator reproduction after Fix 2 used the real ASGI app and `tests.test_dashboard.request` without modifying repository files. Posting `json.dumps({"token": "unknown", "question": "q"}).encode()` returned HTTP 403; replacing the unknown token with the Python string `"\ud800"` raised an uncaught `UnicodeEncodeError`.
- Required follow-up: reject non-ASCII authentication identifiers before encoding or safely map encoding failures to AskAuthError. Add route regressions for escaped surrogate token and wrong-job values. User authorization is required for any further fix cycle.
- Coordinator verification task `b765741ba` was launched after Fix 2 and is still running at this handover. No fresh coordinator test-pass claim or reviewed checkpoint is made. Preliminary task `b4b5c2ab2` was cancelled when mandatory specification gaps made its result insufficient.

## Final Checkpoint

- Phase base ref: refs/plans/worker-ask-coordinator/phase-01/base
- Phase implementation ref: refs/plans/worker-ask-coordinator/phase-01/impl
- Plan commit ref: pending
- State checkpoint: temporary commit

# EXTERNAL RESPONSE
## META
- Phase: 1 / Started: 2026-10-26T06:00:00Z / Finished: 2026-10-26T06:23:00Z / Plan dir: docs/plans/worker-ask-coordinator
## SUMMARY
Bound worker asks by remaining workflow time, revoked tokens immediately on cancellation, hardened Unicode authentication failures, and made backend environment transport an explicit secret-safe dataclass field.
## FILES MODIFIED
| Action | Path | Change |
| --- | --- | --- |
| modify | server/src/refract/ask.py | Track workflow deadlines, clamp asks to remaining time, and compare UTF-8 identifiers with compare_digest |
| modify | server/src/refract/execution.py | Bind ask token deadline to attempt start and workflow timeout |
| modify | server/src/refract/runtime.py | Revoke token immediately when cancelling a job, releasing any pending ask |
| modify | server/src/refract/backends/__init__.py | Replace ID-keyed env side table with env dataclass field excluded from repr |
| modify | server/tests/test_ask.py | Regressions for normal, late, finite, unlimited, and cancelled ask behavior |
| modify | server/tests/test_dashboard.py | Regressions for Unicode unknown tokens and wrong-job identifiers returning 403 |
| modify | server/tests/test_smoke.py | Include env in BackendParams field contract and assert repr secrecy |
| modify | docs/plans/worker-ask-coordinator/phase-01/notes.md | Append Fix 2 decisions and exact RED/GREEN/full-check evidence |
| modify | docs/plans/worker-ask-coordinator/phase-01/journal.md | Append this Fix 2 ERP response |
## NOTES
- docs/plans/worker-ask-coordinator/phase-01/notes.md (## Fix 2)
## SPEC COMPLIANCE
- Meets Spec? YES — all four bounded findings were addressed; full server pytest and plugin test suite passed.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

# EXTERNAL RESPONSE
## META
- Phase: 1 / Started: 2026-10-26T06:30:00Z / Finished: 2026-10-26T07:05:00Z / Plan dir: docs/plans/worker-ask-coordinator
## SUMMARY
Safely mapped lone surrogate UTF-8 encoding failures in authentication identifiers to AskAuthError returning HTTP 403.
## FILES MODIFIED
| Action | Path | Change |
| --- | --- | --- |
| modify | server/src/refract/ask.py | Catch UnicodeEncodeError on token and job encoding to raise AskAuthError |
| modify | server/tests/test_dashboard.py | Add POST /ask regressions for escaped lone surrogate token and job identifiers |
| modify | server/tests/test_ask.py | Add validate_token regressions for lone surrogate token and job identifiers |
| modify | docs/plans/worker-ask-coordinator/phase-01/notes.md | Append Fix 3 decisions and exact RED/GREEN evidence |
| modify | docs/plans/worker-ask-coordinator/phase-01/journal.md | Append Fix 3 ERP response |
## NOTES
- docs/plans/worker-ask-coordinator/phase-01/notes.md (## Fix 3)
## SPEC COMPLIANCE
- Meets Spec? YES - Escaped lone surrogates return HTTP 403 and constant-time comparisons are preserved.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Final Review and Phase Acceptance

- Reviewed revision: `757cbd1dfe074dfdbfe7c4e3a4c22a8ad5b1b1a5`.
- Independent review job: `2d996e6f-6dc8-447e-9553-354e37f72790`.
- Reviewed range: `refs/plans/worker-ask-coordinator/phase-01/base..757cbd1dfe074dfdbfe7c4e3a4c22a8ad5b1b1a5`.
- Reviewer returned PASS with one nonblocking finding: unbounded revoked-token retention in `server/src/refract/ask.py`.
- Coordinator quality status: PASS_WITH_DEBT. Owner: Refract server maintainer.
- Specification status: PASS. Unknown and wrong-job surrogate identifiers return HTTP 403; constant-time comparisons remain intact.
- Focused checkpoint regression run: `cd server && uv run pytest -q tests/test_dashboard.py::test_ask_token_auth_and_wrong_job tests/test_ask.py::test_issue_token_and_validate`; 2 passed in 1.60s.
- Complete checkpoint verification task: `b3148df87`.
- `cd server && uv run pytest -q`: 609 passed, 3 deselected in 112.47s; exit 0.
- `bash plugin/tests/run.sh`: passed; exit 0; three existing manifest warnings.
- HEAD and production/plugin files were unchanged by review. Only the coordinator's handover job-reference update was dirty.
- Phase implementation ref: `refs/plans/worker-ask-coordinator/phase-01/impl`.
- Phase 1 accepted. Next: Phase 2, coordinator MCP contract. No Phase 2 implementation started.
- Earlier failed review sections are historical and superseded by this acceptance.
