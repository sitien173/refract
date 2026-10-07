<!-- ccg-shared-version: 11.0.6 -->

# Phase 3 Journal: Reader/writer admission and dependency scheduling

## META

- Plan: docs/plans/mcp-v2-claude-code/PLAN.md
- Implementation Profile: implement
- Consultation Profile: consult
- Review Profile: review
- Consultation Job: pending
- Implementation Job: pending
- Review Job: pending
- Started: 2026-10-07
- Finished: 2026-10-07T17:51:02+07:00

## Setup and Guidance

- Pre-phase root: attached main, clean at 44b8162dd4b1ee8fa0c4669f06f2a47556759b8f. Plan tracking is tracked. Plan base 491e043dedc0263900e137f9a85fbf781e00530f and Phase 2 impl 2a08be6af285085db3f14ef77e05699450fb4daf resolve. Phase 2 DONE, Spec and Quality PASS, no debt.
- No active project job. Daemon status running, PID 482030, startup Wed 2026-10-07 14:01:37 +07 unchanged. No restart before Phase 7.
- task_guide called once for Phase 3. Its v1 input accepts only project_id; the complete phase request is PLAN.md Phase 3 Task Guide Input and prompt.md.
- Routes selected and validated from guide, project profiles, and workflows: consult/consult for architecture and race analysis, implement/implement for non-UI source changes, review/review for independent quality.
- Consultation required because admission, cancellation, retry, and recovery share correctness-sensitive state transitions.
- The optional earlier Phase 3 semantic retrieval was cancelled without findings. Known source/test paths are sufficient for the bounded consultation; no fabricated retrieval evidence is adopted.
- Continue normal wait timeouts under the user's approval. Failures, unresolved decisions, and review-fix limits remain blocking.

## Consultation

- Job 76fa8d6d-760c-49ef-9fd0-20ad8194a886 succeeded. Advice returned BLOCKED only for a bounded models.py edit-scope decision.
- Source evidence: Runtime.cancel returns ActionResult, whose declared fields cannot carry cascaded IDs. The minimum fix is ActionResult.cancelled_dependents: list[str] = Field(default_factory=list). No subclass, tuple, dynamic attribute, or unchecked model update is warranted.
- The user explicitly approved that single field through AskUserQuestion. Running cancellation reports only IDs actually cancelled in the current call, not eventual outcomes. Waiting metadata requires no JobView edit and stays in Runtime.waiting_metadata until Phase 4. The approved additive ActionResult field can appear in the existing v1 wire shape; tool/resource names remain unchanged.
- The scope blocker is resolved. PLAN.md and prompt.md record the single-field extension. Other models.py changes remain out of scope. Consultation recommendations are adopted in prompt.md; no remaining product decision is reported.
- Recommendations cover concrete ready-candidate reservations in one synchronous no-await boundary; startup reader capacity; ready-writer barrier; same-scope serialization; persist/queue before notifier awaits; reverse-link causal cascade before retries; per-dispatch completion handles for terminal-notifier retry race; recovery of interrupted and already-unsuccessful parents before admission; worker survival and task cancellation; immediate target semaphore protection and unconditional release even on recorder failure; orderly shutdown and waiter release.
- Deterministic regression matrix spans every adopted Testing row plus setup, recorder cleanup, terminal notifier, and shutdown fault paths. Existing native enforcement evidence remains required, not a nonmutating-fake claim.
- Read-only reconciliation passed at 130b9b03fc5ede6b1ce7c9be14fc6879d32fa44d: only coordinator-owned handover reference differed, no source or artifact reviewer edits. Daemon PID 482030 and start timestamp unchanged. No consult command or test ran. Known-path Read was sufficient despite unavailable custom search tools.
- Phase 3 base is not written until the finalized prompt is checkpointed.

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase: Phase 3 — Reader/writer admission and dependency scheduling
- Started: 2026-10-07 (time not recorded)
- Finished: 2026-10-07T17:51:02+07:00
- Plan dir: docs/plans/mcp-v2-claude-code
- Pre-job HEAD: d5e81f3b86335e64d573505963fa80915e3e853e
- Authoritative phase base: d58f176734b2908a33772cf506c67306cddf6deb

## SUMMARY
Implemented reader/writer admission, durable dependency scheduling and cancellation, retry/recovery handling, waiting metadata, and current-call dependent cancellation reporting.

## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modify | `src/openmcp/scheduler.py` | Add reader/writer/session reservations, dependency readiness, writer barriers, waiter generations, and shutdown cleanup |
| Modify | `src/openmcp/runtime.py` | Add dependency-aware submission, cascading terminal handling, retry/recovery, waiting metadata, and cancellation results |
| Modify | `src/openmcp/execution.py` | Add terminal callbacks, explicit task-cancellation handling, target semaphore cleanup, and terminal notification safety |
| Modify | `src/openmcp/models.py` | Add the approved `ActionResult.cancelled_dependents` field only |
| Modify | `tests/test_scheduler.py` | Add deterministic admission, fairness, capacity, waiter, and callback regressions |
| Modify | `tests/test_execution.py` | Add dependency lifecycle, recovery, retry, cancellation, capacity, and cleanup regressions |
| Modify | `docs/plans/mcp-v2-claude-code/phase-03/notes.md` | Record per-task RED/GREEN evidence |
| Modify | `docs/plans/mcp-v2-claude-code/phase-03/journal.md` | Record the full implementation response |

## NOTES
- `phase-03/notes.md` — Task 1, Task 2, Task 3, Task 4.
- Phase 2 files were not changed. `.handover.md` appeared modified in status and was preserved as coordinator-owned bookkeeping.

## TESTS RUN
- Task 1 RED: focused scheduler tests -> 4 failed, 5 deselected because constructor support for reader capacity/readiness was absent. GREEN: `uv run --extra dev pytest tests/test_scheduler.py -q` -> 15 passed.
- Task 2 RED: focused dependency submit tests -> 3 failed, 86 deselected because `Runtime.submit` rejected `depends_on`. GREEN: expanded dependency submission selection -> 6 passed, 101 deselected.
- Task 2 compatibility RED: focused recovery submit test -> `sqlite3.OperationalError: cannot start a transaction within a transaction`; Runtime now commits an existing connection-context transaction before calling the Phase 2 transaction-owning API. GREEN: same test -> 1 passed, 106 deselected. No Phase 2 file was changed.
- Task 3 RED: retry-focused regressions -> 1 failed, 4 passed, 89 deselected (unsuccessful parent retry was not rejected). Target cleanup regressions -> 4 failed, 94 deselected (post-acquisition semaphore/active count leaked). GREEN combined retry/recovery/target cleanup -> 9 passed, 98 deselected.
- JobRunner cancellation RED -> 1 failed, 106 deselected; cancellation left the persisted job `running`. GREEN -> 1 passed, 106 deselected.
- Task 4 RED: focused waiting/cancellation tests -> 3 failed, 97 deselected (missing waiting API and additive result field). GREEN -> 3 passed, 104 deselected.
- Required suite: `uv run --extra dev pytest tests/test_scheduler.py tests/test_runtime.py tests/test_execution.py -q` -> 137 passed in 26.07s.
- Full suite: `uv run --extra dev pytest -q` -> 535 passed, 3 deselected in 33.71s.
- `git diff --check` -> exit 0, no output.

## SPEC COMPLIANCE
- Meets Spec? YES — all four Phase 3 tasks and required checks passed. MCP names and shapes remain unchanged apart from the approved additive ActionResult field. Live acceptance remains coordinator-owned.

## CLARIFICATIONS NEEDED
None

## NEXT
TASK_COMPLETE

## B1 Recovery Fix Response

# EXTERNAL RESPONSE
## META
- Phase: Phase 3 — B1 admitted-but-unstarted cancellation fix
- Started: 2026-10-07 (time not recorded)
- Finished: 2026-10-07T21:55:48+07:00
- Plan dir: docs/plans/mcp-v2-claude-code
- Pre-job HEAD: d5e81f3b86335e64d573505963fa80915e3e853e

## SUMMARY
Fixed B1 by separating reserved-but-unstarted dispatches from executing work and making stale ready entries generation-safe.

## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modify | `src/openmcp/scheduler.py` | Track dispatch start and cancel reserved-unstarted work immediately; skip stale dispatch handles |
| Modify | `src/openmcp/runtime.py` | Preserved existing terminal cascade and retry wiring; no B1-specific source change |
| Modify | `src/openmcp/execution.py` | Preserved Phase 3 terminal and cleanup behavior |
| Modify | `src/openmcp/models.py` | Preserved the approved cancellation result field |
| Modify | `tests/test_scheduler.py` | Preserved admission and generation-safety coverage |
| Modify | `tests/test_execution.py` | Add deterministic paused-notifier B1 reproduction, cancellation cascade, and retry-generation assertions |
| Modify | `docs/plans/mcp-v2-claude-code/phase-03/notes.md` | Record B1 RED/GREEN evidence |
| Modify | `docs/plans/mcp-v2-claude-code/phase-03/journal.md` | Append the B1 ERP response |

## NOTES
- `phase-03/notes.md` — B1 Recovery Fix.
- Existing Phase 3 implementation and failed transport record were preserved. The coordinator-owned `.handover.md` and untracked `fix-01.md` were not edited.
- No Phase 2 path was changed.

## TESTS RUN
- RED: `uv run --extra dev pytest tests/test_execution.py -q -k 'cancel_reserved_unstarted_parent_cascades_and_retry_uses_new_dispatch'` -> 1 failed, 108 deselected. Cancellation returned `running` instead of the queued parent's expected `cancelled` state.
- GREEN: same command -> 1 passed, 108 deselected. The paused-notifier test verifies immediate transitive cancellation, exact current-call dependent IDs, waiter release, reservation release, and that only the retry's fresh unset event dispatch executes.
- Required suite: `uv run --extra dev pytest tests/test_scheduler.py tests/test_runtime.py tests/test_execution.py -q` -> 138 passed in 29.71s.
- Full suite: `uv run --extra dev pytest -q` -> 536 passed, 3 deselected in 32.63s.
- `git diff --check` -> exit 0, no output.

## SPEC COMPLIANCE
- Meets Spec? YES — B1 behavior is fixed and regression evidence passes. The earlier Phase 3 implementation is preserved.

## CLARIFICATIONS NEEDED
None

## NEXT
TASK_COMPLETE

## Coordinator Verification

- Implementation job c55ecb3b-ba71-4845-ac5d-3e426a380aec actually failed at 2026-10-07T10:53:25.291377+00:00 with `WebSocket error`. Its MCP result contains no ERP text. The complete worker ERP was saved on disk in this journal with NEXT TASK_COMPLETE before the transport failure. Do not report the job as succeeded.
- Reconciliation: no active project job; daemon status running with no active or queued jobs. Attached main remained at pre-job HEAD d5e81f3b86335e64d573505963fa80915e3e853e. Daemon PID 482030 and startup Wed 2026-10-07 14:01:37 +07 remained unchanged.
- All worker changes are declared: scheduler.py, runtime.py, execution.py, the one approved models.py field, test_scheduler.py, test_execution.py, and phase-03 notes/journal. test_runtime.py was allowed but unchanged. The separate handover modification is coordinator job-reference bookkeeping. No out-of-scope file changed.
- Fresh diagnostic verification of the uncommitted tree: `uv run --extra dev pytest tests/test_scheduler.py tests/test_runtime.py tests/test_execution.py -q` passed 137 tests in 35.79s; `uv run --extra dev pytest -q` passed 535 tests with 3 deselected in 34.20s; `git diff --check` passed. HEAD and changed paths remained the same before and after. This does not replace specification or independent quality review.
- Recovery is blocked on the user's choice: accept the saved ERP as a documented exception to retry, then inspect/checkpoint/review; or retry the failed job once without resetting its partial changes. No checkpoint or recovery job has run.
- Future Phase 4 facts: both installed SDKs expose public pre-validation middleware, ToolError, and structured_output=False. Disabling structured output removes the duplicate copy. A 24000-character ASCII page has 24016 characters of model-visible text and a 48133-character duplicated serialized result by default; escaping can exceed the bound. Phase 4 consultation must resolve size-aware paging and uncapped metadata before implementation.
- The project version in uv.lock remains 1.2.0 at its OpenMCP package record. Phase 4's declared list omits uv.lock. The first bounded scope question timed out without a user answer. That was not approval. A narrowly scoped lockfile version update is still unresolved; dependency versions and both SDK environments must remain unchanged.

## Read-only Recovery Diagnosis

- Confirmed blocker B1: cancelling an admitted but unstarted queued parent is treated as running. scheduler.py:139 chooses solely from dispatch.reserved; runtime.py:371 consequently records a cancellation request and reports state running without cancelling the saved queued parent, its dependents, or their waiters.
- Isolated reproduction used existing FakeDrivers/config helpers, a temporary home and project, max_jobs=1, notifications disabled, and deterministic events. The sole worker was paused in a previous job's terminal notifier after its reservation was released. A new parent remained queued but reserved; its child waited on that parent.
- Exact output: `{"before_worker_release":{"reported_state":"running","parent_state":"queued","child_state":"queued","cancelled_dependents_count":0,"project_reservations":1},"after_worker_release":{"parent_state":"cancelled","child_state":"cancelled"}}`.
- The queued cancellation criterion is not met while that notifier remains paused. Existing green tests cover pending queued parents behind an active job, not this admitted-but-unstarted case. A fix must cancel the actual queued parent and cascade immediately, release its reservation and waiters, and ensure stale ready-queue entries cannot execute or release a later retry of the same ID. No production or test file changed during diagnosis.
- No fix job, checkpoint, or formal independent review has run. Recovery still requires the user's answer; a new narrowly scoped fix prompt is now warranted rather than an unchanged replay of the complete phase.

## Resume Authorization

- On 2026-10-07, the user directed completion of mcp-v2-claude-code. Resume with the saved ERP as a documented exception to unchanged retry, preserve the failed transport record and every existing change, and dispatch the bounded B1 correction in fix-01.md.
- Fresh reconciliation: attached main at d5e81f3b86335e64d573505963fa80915e3e853e; active jobs empty; latest implementation c55ecb3b-ba71-4845-ac5d-3e426a380aec failed. Changed paths match the saved implementation and coordinator-owned recovery artifacts. Plan and Phase 3 base refs resolve; Phase 3 base remains an ancestor.
- Daemon PID 482030 and startup Wed 2026-10-07 14:01:37 +07 unchanged. No restart or live configuration change. Phase 4 lockfile scope will be resolved at its gate.

## B1 Coordinator Verification

- Recovery job a5330062-9222-4215-8369-47f9f433751f succeeded with NEXT TASK_COMPLETE. The original failed job remains failed. The saved implementation was preserved.
- Inspected production diff and deterministic B1 regression. Dispatch started state distinguishes execution from reservation. Unstarted cancellation releases its reservation and completion event. Workers ignore stale dispatch objects, and retry uses its own event and reservation. All changed paths remain in approved Phase 3 scope and coordinator recovery artifacts.
- Fresh coordinator checks at unchanged HEAD d5e81f3b86335e64d573505963fa80915e3e853e: focused suite 138 passed in 22.80s; full suite 536 passed, 3 deselected in 36.34s; git diff --check passed.
- No active project job. No daemon restart. Specification PASS; independent quality review pending.
- The repeated Phase 4 uv.lock scope question timed out without user input. This is not approval. Keep that scope decision unresolved.

## Quality Review

Pending.

## Review Result

- Spec Status: PENDING
- Quality Status: PENDING
- Debt: none

## Final Checkpoint

- Phase base ref: refs/plans/mcp-v2-claude-code/phase-03/base, d58f176734b2908a33772cf506c67306cddf6deb. Created once at the clean finalized prompt checkpoint after consultation and user scope approval.
- Phase implementation ref: refs/plans/mcp-v2-claude-code/phase-03/impl, pending
- Plan commit ref: pending
- State checkpoint: pending
