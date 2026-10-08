# Phase 4 Recovery 2: Fresh implementation context

Continue the existing Phase 4 work with a fresh implementation session. Read prompt.md and recovery-01.md. Their original approved contract, scope, diagnosed hang, and bounded-check requirements remain authoritative. Both recovery files are Coordinator-owned and read-only to the worker.

## Failure and reconciliation

- Recovery job 8417c4ce-bd26-44fe-ba2a-212686f15ff3 failed at 2026-10-07T20:40:15.130773+00:00 because its resumed execution context exceeded the context limit. It returned no ERP. An unchanged retry would reuse that context, so this submission starts fresh without changing workflow or profile.
- Preserve both failed/cancelled job records and every filesystem change. Do not reset, restore, replay the whole phase, or claim either previous job succeeded.
- Fresh reconciliation: attached main at 8ada4a3cfe76137dc2c6943282a65a12522fe234, no active or queued job, phase-04/base unchanged at acaca18f2cf61398d92ccc93f88b02c68e28207d. No checkpoint or daemon restart occurred.
- The first recovery added or updated README.md, pyproject.toml, uv.lock, and test_server.py. All changed source/test paths remain within the original allowed set. The previous preserved paths and separate Coordinator bookkeeping remain present.
- Worker notes and a complete ERP are still missing. Test results and compatibility remain unverified at this tree. The original recorded RED runs are available in the filtered diagnostic file identified by recovery-01.md. Backfill only actual evidence.

## Execute

- Read the full worker contract and ERP pointers in the submission. You are a fresh worker but the filesystem is a continuation, not a clean baseline.
- Inspect the existing implementation, correct the diagnosed stale test doubles and any incomplete behavior, and finish all four original tasks. Conditional backend_runner.py deletion, all public error families, full bounds/paging/privacy, desktop compatibility, and both SDK client checks still require evidence.
- Run test-first for remaining behavior changes. Preserve reviewed scheduling and earlier consultation/approval records. Do not add production fallbacks for incomplete test mocks.
- Wrap pytest and SDK checks in `timeout --kill-after=5s 180s`. A timeout is a failed check requiring diagnosis, not a reason to wait indefinitely. Do not install or upgrade test tooling.
- Use the two existing SDK interpreters from recovery-01.md, isolated notification-disabled fixtures, and actual MCP clients. Do not mutate environments or read live/global configuration/database/authentication/session files.
- Stay within prompt.md's exact implementation paths and worker-owned notes/journal. No Git writes, daemon restart, OpenMCP calls, Coordinator-file edits, or scope expansion.
- Complete every original verification command freshly, record commands/exits/counts and limitations, then return the full ERP. TASK_COMPLETE requires every check to pass; otherwise report the concrete blocker.
