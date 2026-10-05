# Phase 2: Terminal job desktop notifications

## User Request
Complete desktop-notifications according to the confirmed DESIGN.md and PLAN.md. Phase 1 is implemented and reviewed.

## Phase
Add native terminal-job notification delivery with independently guarded failures, live config behavior, and mocked tests.

## Tasks
Follow Phase 2 tasks, acceptance criteria, reviewer checklist, and verification checks in `/home/ngosi/projects/openmcp/docs/plans/desktop-notifications/PLAN.md` exactly.
1. Add send_job_notification(job: JobView, project_alias: str) -> bool. Construct Notify, set application_name to OpenMCP, title to OpenMCP job <state>, message to <alias> / <context_key> / <workflow> / <target_id or ->, and return bool(send(block=True)).
2. When enabled, capture the persisted job before the first await and defer lookup error reporting until after MCP publication. Keep the existing MCP try block unchanged. After it, read the live self._catalog.notifications.enabled flag and independently guard project lookup and asyncio.to_thread delivery using the captured job. Only captured terminal states send. Missing job/project skips. False returns and exceptions log warning event job.desktop_notification_failed with job_id, without re-raising into the caller.
3. Test helper formatting, empty target, content privacy, send(block=True), and boolean results with patched openmcp.notifications.Notify.
4. Test terminal transitions, default-off behavior, no sends for queued/running/retry-to-queued, false/exception failure isolation with unchanged job outcomes and MCP notification URI sequences, and live _catalog flag toggles. Include succeeded, failed, queued cancel, and startup recovery to interrupted, exactly one call per transition. Patch openmcp.runtime.send_job_notification. Keep the real runtime, scheduler, and database behavior.

## Context
Read DESIGN.md and Phase 2 of PLAN.md. Existing terminal notifications converge in Runtime._notify_job_resource through JobRunner, queued cancel, and startup recovery. The URI template is openmcp://jobs/{job_id}. Existing helpers in tests/orchestration_helpers.py and existing cancellation/recovery tests can be reused.
Phase 1 introduced NotificationsConfig(enabled=False) and DaemonConfig.notifications. Config parsing and dependency files are out of scope here.

Coordinator fetched current Context7 docs for /ms7m/notify-py. Confirmed Notify() construction, application_name property assignment, title/message assignment, and send(block=True) returning bool. Blocking send may wait up to 35 seconds and fail by false return or exception. Notify construction can fail on unsupported/headless platforms. The entire helper invocation must therefore run in asyncio.to_thread under the independent exception guard. Sources: https://github.com/ms7m/notify-py/blob/master/_autodocs/api-reference-notify.md and https://github.com/ms7m/notify-py/blob/master/_autodocs/architecture.md.

## Files
- src/openmcp/notifications.py
- tests/test_notifications.py
- src/openmcp/runtime.py
- tests/test_execution.py
- docs/plans/desktop-notifications/phase-02/notes.md
- docs/plans/desktop-notifications/phase-02/journal.md

## Done When
All Phase 2 acceptance criteria hold, and these fresh commands pass:
- `uv run pytest tests/test_notifications.py tests/test_execution.py -q`
- `uv run pytest -q`

## SKILLS
- TDD: `/home/ngosi/projects/superpowers-ccg/skills/test-driven-development/SKILL.md`
- Verification: `/home/ngosi/projects/superpowers-ccg/skills/verifying-before-completion/SKILL.md`

## Rules
Read existing files before editing. Use Auggie semantic retrieval and tgrep exact search for code exploration, with Read only for known paths. No grep, find, cat, ls, generic filesystem exploration, or other search tools. Stay within the listed files. Do not edit handover, prompts, Git, config.py, dependencies, server, or dashboard. Do not inspect secret-bearing local files. Never send a real OS notification. Behavioral TDD is required: collectable tests must fail for intended missing behavior before real production implementation. Import errors are not RED. Record exact RED and GREEN commands and failure assertions in per-task notes. Maintain notes and append the ERP block to the journal. Coordinator owns commits and handover. Use foreground test commands to ensure outputs are captured before returning; avoid redundant background wait messages.

## Review Fix 1

The coordinator reproduced a blocking correctness failure on revision 66238188ddcaa19ffe540f961f7a99bda8710a86. A failed job's MCP notifier was paused with an asyncio.Event. While paused, Runtime.retry reset the job to queued and completed its own queued notification. Releasing the terminal publish produced zero helper calls instead of one. Root cause: the job lookup after await self.notifier observes the reset state rather than the terminal transition.

- Add a deterministic asyncio.Event regression in tests/test_execution.py using a real persisted failed job, real Runtime.retry, and a patched helper. Pause only the first publish, retry to queued, release the first publish, and assert exactly one helper call carrying state failed. Confirm the intended assertion fails before production changes. No backend or OS notification may run.
- Fix with a pre-await persisted JobView snapshot only when notifications are enabled. Retain the existing MCP try block unchanged and send after it. Use the snapshot, not a post-await job lookup. Capture lookup exceptions and defer warning-only reporting until after MCP publication so lookup failures cannot suppress MCP. No deduplication registry, per-job locks, or notifier-contract changes.
- Preserve default-off no job lookup and no helper construction, live flag toggles, missing row skips, off-event-loop helper execution, and existing failure isolation. Add targeted tests for snapshot lookup failures and default-off no lookup if needed to verify the changed control flow.
- Resolve the independent review's warning-coverage debt: in the existing false/exception failure-isolation test, capture logs and assert event job.desktop_notification_failed and correct job_id for both cases. Warning behavior already exists, so record passing characterization evidence rather than inventing a RED for a behavior you did not change.
- Append Task 5 and later blocks and the fix ERP to existing notes/journal. Never overwrite earlier evidence. Run both phase verification commands fresh.

The coordinator updated DESIGN.md and PLAN.md to record this ordering correction. Those coordination files remain worker read-only. Allowed worker files are unchanged.

## Review Fix 2

Final bounded review-fix cycle. Independent review d0dd8556-762b-434d-87ea-01d48d95785b confirmed these findings on revision 4a874928782fe0fa7111bcaf7b50e002af6a1d1b:

1. MEDIUM, runtime.py:97-102: deferred lookup warning uses exc_info=True outside the except handler and logs NoneType instead of the captured exception. Add assertions in the snapshot lookup failure test that record.exc_info contains RuntimeError, the database locked exception, and a non-null traceback. Run the intended failure before production changes. Fix with exc_info=(type(lookup_error), lookup_error, lookup_error.__traceback__). Preserve the warning-after-MCP ordering.
2. MEDIUM, test_execution.py:3286-3298: the concurrency regression starts the scheduler, allowing the retried job to execute and create an unrelated terminal notification during assertions. Keep the real Runtime.retry and persisted database transition, but leave the scheduler unstarted. Remove the unused FakeDrivers assignment from this test. The regression must still demonstrate failed-to-queued during the paused terminal MCP publish and exactly one failed-state helper call.
3. LOW, test_execution.py:3319 and 3348: the new lookup-failure and disabled-no-lookup tests omit Runtime cleanup. Wrap each in try/finally with await runtime.close(). Do not modify unrelated tests.

Only runtime.py, test_execution.py, and phase-02 notes/journal need edits. Append Task 6 and the fix ERP, preserving earlier evidence. Verify the concurrency regression three times, both control-flow tests, and all phase verification commands. Capture fresh counts. Do not add another abstraction or change the notification contract.

## Response Format
Return the ERP # EXTERNAL RESPONSE block and matching status line.
