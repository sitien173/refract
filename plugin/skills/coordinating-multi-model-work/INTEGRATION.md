# Multi-Model Integration Guide

Claude is planner, orchestrator, reviewer, and integrator. Implementation normally goes through an executor, with Codex as the default route and Gemini reserved for UI-heavy phases.

## Standard Pattern

1. Define one implementation phase with 2-4 related tasks.
2. Turn CP0 findings into small reusable `CONTEXT_ARTIFACTS`.
3. Build one `PHASE_CONTEXT_BUNDLE` for the phase.
4. If routing is not `CLAUDE`, execute CP2 with:
   - a compressed original user request
   - `CONTEXT_REFS` from the phase-scoped bundle
   - `HYDRATED_CONTEXT` snippets for that phase only
   - the CP1 phase summary
   - the explicit file set
   - the success criteria, reviewer checklist, and integration checks for the phase
5. Ask the worker to return complete final file content whenever practical, with unified diff patch as fallback, using External Response Protocol v1.1.
6. Reuse `SESSION_ID` only for follow-up fixes on the same phase, and send deltas only:
   - changed refs
   - new hydrated snippets
   - updated verification failures or spec gaps
7. If CP1 chose `Cross-Validation`, or CP2 returned conflicts, overlap, gaps, clarifications, or continuation requests, run CP3 Reconciliation as Claude's decision layer.
8. Always run CP4 Phase Review after CP3, or directly after CP2/Claude-only work when no reconciliation is needed.
9. Run integration checks after each phase review.
10. `PASS` completes the phase. `PASS_WITH_DEBT` completes the phase with explicit non-blocking debt. `FAIL` requires a retry, follow-up, or user clarification.

## Hard Rules

- Do not ask for draft code that the orchestrator will later re-implement.
- Do not ask for design prose on an implementation task.
- Do not restate the whole PRD, plan, or prior conversation in every prompt.
- Do not repaste the full CP0 discovery output into every worker prompt.
- Do not send multiple workers the same implementation phase unless cross-validation is explicitly selected.
- Do not ask for changed hunks only when the worker can return the final file content directly.
- Do not turn CP4 into a code-quality or best-practice review pass.

## Prompt Structure

Every implementation prompt should contain:

```text
## Original User Request
[original user request]

## Phase Context Bundle
TASK_ID: [stable bounded-task id]

## Context Refs
- [artifact id]
- [artifact id]

## Hydrated Context
[only the small context snippets needed to complete this phase]

## CP1 Phase Summary
[single phase summary]

## Files
[explicit file set]

## Success Criteria
[2-5 concrete checks]

## Reviewer Checklist
[phase review checklist]

## Integration Checks
[exact commands or repo-state checks]

## Response Protocol
Use exactly this structure:

# EXTERNAL RESPONSE PROTOCOL v1.1

## SUMMARY
[one sentence]

## FILES MODIFIED
| Action  | File Path          | Description of Change |
|---------|--------------------|-----------------------|
| Created | src/...            | ...                   |
| Edited  | src/...            | ...                   |

## FILE CONTENTS
[complete final file content for each modified file, preferred; unified diff patch only when full content is impractical]

## CONTEXT ARTIFACTS
[optional reusable artifacts discovered or updated during execution]

## SPEC COMPLIANCE
- Meets Spec? YES / WITH_DEBT / NO
- Explanation: ...

## CLARIFICATIONS NEEDED
None (or list questions)

## NEXT STEPS / CONTINUATION
TASK_COMPLETE / CONTINUE_SESSION / HANDOVER_TO_CLAUDE
```

## When To Cross-Validate

Use `CROSS_VALIDATION` only for design arbitration or unresolved multi-domain ambiguity. When you do:
- keep the file set and success criteria narrow
- compare only the meaningful divergences
- return one reconciled artifact in External Response Protocol v1.1, not two unrelated implementations

## CP4 Phase Review

Claude performs CP4 in the main thread using:
- the original user request
- the CP1 phase summary
- the CP1 success criteria
- the reviewer checklist
- the integration check results
- the files modified by the workflow

CP4 returns:
- `PASS` when the phase fully satisfies the checklist
- `PASS_WITH_DEBT` when the phase is usable and debt is explicit
- `FAIL` when a blocking requirement is not satisfied
