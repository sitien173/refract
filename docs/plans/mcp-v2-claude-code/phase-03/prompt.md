# Phase 3: Reader/writer admission and dependency scheduling

## User Request

Complete the confirmed OpenMCP v2 plan. Implement reader/writer admission and immutable dependency lifecycle. Preserve the running v1 MCP surface until the Phase 7 cutover.

## Phase

Independent verified readers overlap safely. Writers remain exclusive. Dependents execute only after every parent succeeds, with causal cancellation, retry, and recovery.

## Tasks

- task-1: Replace per-project FIFO admission with startup-bound reader/writer capacity, identical session-scope serialization, and dependency-ready exclusive barriers.
- task-2: Runtime.submit accepts depends_on and persists immutable access mode and links through Phase 2 APIs. Dependency waiting consumes no worker or admission capacity. Reverse links drive transitive cancellation without polling.
- task-3: Preserve retry IDs and links, reject unsuccessful parents, leave unfinished parents waiting, never revive descendants through parent retry, and propagate restart interruptions before admitting queued jobs.
- task-4: Derive waiting_on and waiting_reason for queued jobs, return cascaded IDs from Runtime.cancel, and release completion waiters for cancellations.

## Context

- Read ../PLAN.md Phase 3 and ../DESIGN.md, plus /home/ngosi/projects/openmcp/docs/plans/parallel-readers-job-dependencies/DESIGN.md. The v2 design overrides resource notifications with waiter release but preserves dependency semantics.
- Phase 2 is DONE and independently reviewed. Its actual schema is version 12 after baseline 11. Reuse Database.create_job_with_dependencies, dependencies_for_job, dependents_for_job, job_record access_mode, planning.derive_access_mode, and config.max_project_readers. No new migration or capability policy belongs here.
- Admission depends on the persisted immutable class, never a workflow label or later catalog. Identical project_id + workflow + context_key scopes serialize, including fresh_session=True.
- Maintain submission order among dependency-ready candidates. The earliest ready exclusive job blocks later readers; unfinished dependencies never create a barrier. Running earlier readers finish before the writer starts.
- Keep readiness checks and reservations in one synchronization boundary. Commit dependency cancellations before any notifier await or upstream retry can conceal the failure. Retain existing target concurrency enforcement during execution.
- Queued descendants of failed, cancelled, or interrupted parents are cancelled transitively. Persist causal parent ID, state, and reason. Immediate failed-parent submission returns a cancelled job. Parent retry never revives descendants. Explicit dependent retry retains links and queues only if no parent is terminally unsuccessful.
- Recovery interrupts running jobs and propagates cancellation before admitting remaining queued jobs. Every completion, cancellation, exception, and shutdown releases reservations and waiters.
- Current Runtime operations await resource notifications around enqueue/cancel/retry; the consultation must verify the ordering needed to prevent races. URI/notifier surface removal belongs to Phase 4, not this phase.
- Existing ProjectScheduler(max_jobs, run_job) and default capacity 1 FIFO/cross-project tests remain compatible. New tests use deterministic events, not timing sleeps. Existing tests must not be rewritten to hide regressions.
- Models otherwise remain Phase 4 scope. The user explicitly approved only `ActionResult.cancelled_dependents: list[str] = Field(default_factory=list)` in models.py. Preserve its existing fields and return type. Derive waiting metadata through `Runtime.waiting_metadata(job_id)` returning waiting_on and waiting_reason; keep JobView and current tool/resource names unchanged until Phase 4. The approved additive cancellation field may appear in the existing ActionResult wire shape. Running cancellation returns only IDs actually cancelled during the call; do not predict its later cascade.
- Live daemon is an editable install still running reviewed Phase 1 code. No restart before Phase 7. Never access live/global daemon configuration, database, authentication, or session stores.

## Files

Allowed production and tests, relative to /home/ngosi/projects/openmcp:
- src/openmcp/scheduler.py
- src/openmcp/runtime.py
- src/openmcp/execution.py
- src/openmcp/models.py, only the approved ActionResult.cancelled_dependents field
- tests/test_scheduler.py
- tests/test_runtime.py
- tests/test_execution.py

Worker-owned artifacts:
- docs/plans/mcp-v2-claude-code/phase-03/notes.md
- docs/plans/mcp-v2-claude-code/phase-03/journal.md

All other paths are read-only context. The coordinator owns prompt.md, PLAN.md, DESIGN.md, .handover.md, and Git. Report a necessary extra path as BLOCKED; no silent scope expansion.

## Done When

- Every row of the adopted dependency design Testing table has passing evidence, with current v1 resource exposure deferred to the v2 model/tool surface in Phase 4.
- Same-project, same-workflow readers with distinct context keys overlap within project/global/target capacity. Identical scopes including fresh jobs serialize.
- No writer/reader or writer/writer overlap. Ready writers cannot starve behind later readers; blocked writers do not impede independent ready work.
- Every parent must succeed. Dependency waiting reserves no worker or admission slot. Reverse-link terminal transitions trigger reevaluation, without dependency polling.
- Failed, cancelled, and interrupted parent causes propagate through at least three descendant levels. Cancellation releases queued waiters; causal errors/events survive retry.
- Retry retains ID/links, unfinished parents produce waiting, unsuccessful parents reject with a dependency-specific explanation, and parent retry alone never revives a child. Cover failure-versus-retry notifier races.
- Restart propagates interruption before admission. Execution exceptions, cancellation, and shutdown release project/session/global reservations. Existing target limits remain effective.
- Waiting metadata explains dependency, session, reader capacity, writer barrier, and project exclusivity where applicable. It is derived, not a new lifecycle state.
- Default reader capacity 1 and historical exclusive rows preserve existing FIFO/cross-project behavior unchanged.
- TDD records exact RED failures then GREEN results for each task. All tests use isolated fixtures, never the live daemon.
- uv run --extra dev pytest tests/test_scheduler.py tests/test_runtime.py tests/test_execution.py -q
- uv run --extra dev pytest -q
- git diff --check

## Consultation Findings

Consultation job 76fa8d6d-760c-49ef-9fd0-20ad8194a886 succeeded and returned one bounded scope blocker. The user explicitly approved the single ActionResult field and actual-current-call cancellation semantics; no unresolved product decision remains. The read-only root and daemon were unchanged. Adopt the following minimum recommendations:

- Preserve ProjectScheduler(max_jobs, run_job) and existing two-argument enqueue defaults. Add only needed keyword-only reader capacity, synchronous readiness callback, and per-job admission metadata with exclusive defaults. Runtime supplies startup config.max_project_readers, not its refreshed catalog.
- In one synchronous no-await event-loop section, select a concrete ready candidate and reserve global/project/session capacity before dispatch. Count reserved but not yet running work. Workers never dequeue blocked dependencies. Queue scan skips unfinished dependencies; the earliest ready exclusive job bars later readers even when waiting for earlier readers or session occupancy.
- Persist submission and links, then synchronously evaluate parents. Cancel immediately against an unsuccessful parent; otherwise install queue entry and completion event before any notifier await. Retain causal parent ID/state/reason in errors and events.
- Add a small synchronous terminal callback to JobRunner, invoked after every terminal commit, including missing-project failure, before notification. Walk only reverse links to cancel queued descendants transitively; commit the entire causal cascade before any await or upstream retry. After persistence, remove cancelled entries and release their waiters. Terminal changes reevaluate admission without polling.
- Retry checks parents before reset, keeps ID/links and existing causal events, queues behind unfinished parents, and never resets children. A retry submitted while the old terminal notifier is paused must not disappear because the same ID is still dispatched. Capture completion and reservation handles per dispatch so old cleanup cannot signal or remove the new retry.
- Recovery interrupts running records and reconciles queued dependents against interrupted and already-terminal unsuccessful parents before scheduler admission or notification awaits. Cover a crash between terminal parent commit and cascade.
- Preserve worker service after an ordinary execution callback exception. Scheduler finally releases every reservation and waiter. JobRunner handles task cancellation explicitly, persists the appropriate cancelled/interrupted outcome and cascade before re-raising, but never rewrites an already committed terminal outcome because its notification was cancelled.
- TargetExecutor protects the acquired semaphore immediately, including attempt persistence, capability/recorder setup, invocation, and cleanup failures. An outermost finally releases target capacity even when recorder cleanup fails. Keep target identities, limits, and existing cancellation-aware acquisition unchanged; no dependency polling.
- Shutdown stops admission first, signals active work, handles reserved-undispatched jobs, drains execution and releases reservations/waiters before database close. Unstarted queued records remain durable.
- Deterministic coverage must include same-workflow distinct scopes; fresh/default scope serialization; saved enforcement policy through dispatch/fallback; reader/writer and writer/writer exclusion; ready and newly-ready writer fairness; multiple parents; blocked same/cross-project progress; all unsuccessful parent states and three-level/diamond cascades; immediate cancellation and waiter release; retry/notifier race; restart interrupted and already-failed parent recovery; combined global/project/target limits and target-wait cancellation; invalid Runtime.submit links; historical exclusive/default FIFO behavior; every derived waiting reason and empty nonqueued metadata; causal-event retention; setup/cleanup/runner/task-cancellation/shutdown/notification fault injections. Preserve existing tests and Phase 2 enforcement evidence. A nonmutating fake alone is not proof of native write denial; use the existing enforced policy evidence and report any genuine missing acceptance evidence rather than inventing it.

Exact existing seams: scheduler.py admission and worker cleanup; runtime.py submit/cancel/retry/start notifier ordering; execution.py acquired-target cleanup and JobRunner terminal notifications. Read the complete consultation record through the coordinator-provided findings, not through OpenMCP calls. No extra schema migration or models change beyond the approved one field.

## SKILLS

- test-driven-development: /home/ngosi/projects/superpowers-ccg/skills/test-driven-development/SKILL.md
- verifying-before-completion: /home/ngosi/projects/superpowers-ccg/skills/verifying-before-completion/SKILL.md

## Rules

Follow the existing worker contract and ERP format. Read existing files before edits. Reuse existing helpers and conventions. No speculative infrastructure, adjacent refactoring, new dependency, generic graph traversal, live resizing, or per-project override.

Use custom Auggie retrieval for semantic questions, tgrep for exact searches, and Read for supplied known paths. Do not use native grep/find/ls/Glob/Grep or generic terminal code searches. If custom search tools are unavailable, read known paths and report unresolved needs. Library/CLI APIs require current ctx7 documentation; public web only tvly. Never include secrets in queries.

No OpenMCP calls, Git writes, service restart, global configuration changes, or secret-bearing/live-system reads. Maintain notes and append full ERP responses to journal. Return BLOCKED on a genuinely unresolved requirement or necessary out-of-scope edit.

## Response Format

Return the ERP # EXTERNAL RESPONSE block, actual command output, every modified path, and matching NEXT status. Keep execution identities private.
