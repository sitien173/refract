# Multi-Model Integration Guide

Claude is orchestrator-only. All implementation code goes through external models.

## Standard Pattern

1. Define one bounded task.
2. Include only the minimum context needed to complete that task.
3. If routing is not `CLAUDE`, execute CP2 with:
   - the original user request
   - the full `CONTEXT_PACKAGE` from CP0
   - the CP1 task summary
   - the success criteria and verify command for the bounded task
4. Ask the worker to return complete final file content whenever practical, with unified diff patch as fallback, using External Response Protocol v1.1.
5. Reuse `SESSION_ID` only for follow-up fixes on the same task.
6. If CP1 chose `Cross-Validation`, or CP2 returned conflicts, overlap, gaps, clarifications, or continuation requests, run CP3 Reconciliation as Claude's decision layer.
7. Always run CP4 Final Spec Review after CP3, or directly after CP2/Claude-only work when no reconciliation is needed.
8. Only `PASS` completes the task. `PARTIAL` and `FAIL` require a retry, follow-up, or user clarification.

## Hard Rules

- Do not ask for draft code that the orchestrator will later re-implement.
- Do not ask for design prose on an implementation task.
- Do not restate the whole PRD, plan, or prior conversation in every prompt.
- Do not send multiple workers the same bounded implementation task.
- Do not ask for changed hunks only when the worker can return the final file content directly.
- Do not turn CP4 into a code-quality or best-practice review pass.

## Prompt Structure

Every implementation prompt should contain:

```text
## Original User Request
[original user request]

## Context Package
[full CONTEXT_PACKAGE from CP0]

## CP1 Task Summary
[single bounded task]

## Files
[explicit file set]

## Success Criteria
[2-5 concrete checks]

## Verify
[exact command]

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: Use exactly this structure:

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

## SPEC COMPLIANCE
- Meets Spec? YES / PARTIAL / NO
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

## CP4 Final Spec Review

Claude performs CP4 in the main thread using:
- the original user request
- the CP1 task summary
- the CP1 success criteria
- the files modified by the workflow

CP4 returns:
- `PASS` when the implementation fully satisfies the spec
- `PARTIAL` when some required behavior is missing or incomplete
- `FAIL` when a core requirement is not satisfied
