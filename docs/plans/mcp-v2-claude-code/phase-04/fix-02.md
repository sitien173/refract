# Phase 4 Fix 2: Terminal result privacy and paging termination

This is the second and final automatic fix cycle. Continue the validated checkpoint 0e52035e2915e2c3356117138525190e8cacec1b without resetting or replaying the phase. Read prompt.md, notes.md, journal.md, and this batch. The approved contract remains authoritative. This file is Coordinator-owned and read-only to the worker.

## Independent review result

Review job 70e346a2-de8d-4b51-9940-361821a9de7a returned Meets Spec NO, Quality FAIL, FILES MODIFIED none, NEXT FIX_REQUIRED. It reviewed phase-04/base..0e52035e2915e2c3356117138525190e8cacec1b. The root remained clean at that HEAD. The reviewer independently passed 232 focused tests but confirmed both blockers below. Preserve those findings and the earlier evidence.

## P1: Raw terminal execution errors leak through MCP

- server.py:168 forwards job.result.error verbatim. execution.py:551,583 raises and persists the raw execution error. Recursive forbidden-key removal does not sanitize string contents.
- Independent isolated reproduction with provider-secret-model-backend-detail returned secret_exposed=true in a normal terminal job_wait response.
- Correct the public MCP terminal-error boundary only. Keep the detailed persisted error unchanged for the operator dashboard. Do not change execution, scheduler, database, dashboard, or ordinary result text.
- Non-empty untrusted execution diagnostics need a short safe public message, not raw exception or provider/model/session text. Preserve safe dependency/cancellation causes explicitly. Do not use a permissive prefix match that can forward appended diagnostics.
- Verified scheduler-generated dependency cancellation format from runtime.py:214 is `Dependency {dependency_id} ended in state {dependency_state}` without a final period. Validate the whole stored string against actual dependency IDs and allowed unsuccessful terminal states before treating it as public. Retry-tool messages have a different final period and are not this result field.
- Add an actual-client failed-driver regression that contains private diagnostic markers. Assert no marker appears anywhere in the MCP response, while the database retains the detailed original error. Also cover dependency-cancellation information and rejection of a forged or diagnostic-suffixed cause.

## P1: Empty/EOF metadata overflow loops forever

- In server.py:158-181, start == end == len(result_text) with an oversized envelope fails the fit but bypasses the current start < len(result_text) guard. Halving zero leaves the interval unchanged forever.
- Independent isolated one-second reproduction confirmed non-termination. This includes empty terminal output and an EOF read with oversized public metadata.
- Every failed-fit iteration must either raise or strictly reduce the remaining candidate interval. If no text remains and the public metadata does not fit, immediately return bounded response_too_large. Preserve ordinary empty/EOF success when metadata fits.
- Add regressions for empty text plus oversized summary metadata, EOF offset plus oversized metadata, and tight one-code-point boundaries. Use a finite iteration sentinel or a separately deadline-bound subprocess for RED so the regression itself cannot hang pytest indefinitely.
- Cover oversized persisted execution diagnostics too. After the privacy correction, a raw private error may collapse to a safe bounded message and fit normally. That is valid. If the resulting public metadata still cannot fit, require response_too_large. Do not restore raw errors merely to force an overflow response.

## Allowed fix paths

- src/openmcp/server.py
- tests/test_server.py
- phase-04/notes.md and phase-04/journal.md, worker-owned sections only

Every other repository path is read-only, including this batch and all Coordinator records. Keep the fix minimal. No new abstraction, dependency, configurability, or unrelated cleanup. Preserve all original behavior already verified by review: tools, schemas/annotations, strict validation, atomic project resolution, scheduling, notifications, mutation overflow IDs, and versions.

## Verification and ERP

Record RED before source edits for both defects, then fresh GREEN. Run every original focused/full command and both existing SDK actual-client checks with timeout --kill-after=5s 180s. Add targeted actual-client privacy and metadata-only termination checks under SDK 2.0.0 and 2.3.0. Existing interpreters are /home/ngosi/projects/openmcp/.venv/bin/python3 and /home/ngosi/.local/share/pipx/venvs/openmcp/bin/python. Do not install or upgrade anything.

No Git writes, OpenMCP calls, daemon restart, environment changes, live/global configuration/database/authentication/session reads, or Coordinator-file edits. Temporary notification-disabled fixtures are permitted. Return full ERP with exact paths, commands, exits, counts, and limitations. TASK_COMPLETE requires both blockers and the original checks to pass. Append accurate evidence without replacing earlier approvals, failures, or review records.
