# Phase 4 Recovery 1: Complete the preserved implementation

Read phase-04/prompt.md. Its approved contract and exact implementation file set remain authoritative. Continue from the existing changes rather than replaying the original job. This recovery file is Coordinator-owned and read-only to the worker.

## Recorded state

- Original implementation job abc25b26-d8a7-4c1d-8939-3db92c872cc8 was cancelled at 2026-10-07T20:20:49.703566+00:00. It returned no ERP. Preserve that cancellation record; do not describe the original job as succeeded.
- The last recorded worker command was `uv run --extra dev pytest tests/test_server.py -q`, started at 2026-10-07T17:02:39.802160+00:00 with no completion event for over three hours.
- All partial changes were preserved. Attached main remains at 8ada4a3cfe76137dc2c6943282a65a12522fe234. Phase base remains refs/plans/mcp-v2-claude-code/phase-04/base, acaca18f2cf61398d92ccc93f88b02c68e28207d.
- Existing changed implementation paths: src/openmcp/execution.py, src/openmcp/models.py, src/openmcp/runtime.py, src/openmcp/server.py, tests/test_execution.py, tests/test_runtime.py, tests/test_server.py, tests/test_smoke.py. The separate .handover.md modification belongs to the Coordinator.
- No project job remains active. The daemon was not restarted. No orphan of the exact cancelled server-test command remained.
- The original worker did not finish README, version/lock metadata, conditional facade deletion, complete notes, full verification, or SDK compatibility evidence. Inspect actual state and complete every original acceptance criterion.

## Confirmed diagnostic

- `timeout --kill-after=5s 90s uv run --extra dev pytest tests/test_server.py -vv -x -o faulthandler_timeout=20` exited 1: 12 passed, 1 failed in 1.74s. The first failure is the timeout/page-shape test's database stub missing job_record. The v2 summary also requires dependencies_for_job.
- The same bounded command without -x exited 124. It logged 13 passed and 6 failed before hanging in test_job_wait_cancellation_cleanup. There is no completed suite summary.
- tests/test_server.py:520-534 defines a cancellation-test Runtime without waiting_metadata. server.py:617-618 calls waiting_metadata before starting runtime.wait. job_wait finishes with internal_error, but the test waits forever at tests/test_server.py:542 for wait_started.
- A service-independent reproduction varied only that stub method. Without it: wait_started=false, job_wait finished with internal_error. With it: wait_started=true, job_wait remained pending and cancellation reached runtime.wait. Removing it restored the failure. H1 is confirmed.
- Correct the incomplete test doubles to represent the required v2 interfaces. Do not weaken production metadata or add getattr fallbacks to accommodate stale stubs. Ensure cancellation tests surface early task failure rather than waiting indefinitely for a signal that can never arrive.
- git diff --check also reported a new blank line at EOF in tests/test_smoke.py:1447. Correct only this introduced whitespace.

## Evidence available outside the repository

Read these existing diagnostic artifacts when useful:
- /tmp/mcp-v2-phase4-server-hang.log
- /tmp/mcp-v2-phase4-server-full-diagnostic.log
- /tmp/mcp-v2-phase4-recovery-evidence.tzGQYW/test-evidence.json

The filtered test evidence records actual original RED runs and subsequent focused GREEN results with timestamps. Recover accurate notes from it and the existing implementation session. Do not invent timestamps or infer a full-suite pass from focused results. Preserve earlier consultation and approval sections in journal.md.

## Recovery execution

- Follow root-cause-first and TDD. Record the confirmed fixture failure, then its fresh GREEN. New missing behaviors still require RED before production edits.
- Complete all four tasks and every check in prompt.md, not only the hanging test. Keep the original file scope and every restriction.
- Bound each pytest and isolated SDK command with `timeout --kill-after=5s 180s`. Verify the worker shell tool's timeout units rather than blindly using 120000. The process timeout is authoritative; exit 124 is a failed check, never a pass. Diagnose a timeout instead of waiting indefinitely.
- Existing verified test interpreter: /home/ngosi/projects/openmcp/.venv/bin/python3, SDK 2.0.0. Existing installed interpreter: /home/ngosi/.local/share/pipx/venvs/openmcp/bin/python, SDK 2.3.0. Use isolated temporary fixtures and actual clients. Do not install, upgrade, re-resolve dependencies, or alter either environment.
- Run the original focused suite, full suite, both existing-SDK client checks, and git diff --check freshly. Write actual commands, exit codes, counts, limitations, and every modified path in notes/journal and ERP.
- No Git writes, daemon restart, OpenMCP calls, live/global configuration/database/authentication/session reads, or out-of-scope changes. Temporary notification-disabled test fixtures and the listed diagnostic files are permitted.
- Return the full ERP with NEXT TASK_COMPLETE only after all required checks pass. Otherwise state the concrete blocker and preserve partial work.
