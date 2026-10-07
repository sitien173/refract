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
- Finished: pending

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

Pending.

## Coordinator Verification

Pending.

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
