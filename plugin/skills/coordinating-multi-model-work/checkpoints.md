# Collaboration Checkpoints

## Overview

Checkpoints exist to control routing and keep the orchestrator thread small.

## CP0: Context Acquisition

- Gather only the minimum context needed to route the next bounded task.
- Use Auggie for full local codebase context retrieval.
- Use Grok Search only when the task needs external/current knowledge or research.
- Normalize the useful output into small reusable `CONTEXT_ARTIFACTS`.
- End CP0 as soon as the bounded task and likely owner are clear enough for CP1.

CP0 tool matrix:

| Need | Primary Tool | When to Trigger Grok Search | Fallback |
| --- | --- | --- | --- |
| Local codebase context / implementation anchors | Auggie | Do not trigger Grok Search during normal local-context retrieval | None |
| External / real-world knowledge | Grok Search | When the task mentions "latest", "current", "best practice", an unknown library, or a raw error that needs external research | None |

## CP1: Task Assessment & Routing

- Run immediately after CP0 completes.
- Read the original user request and the CP0 context artifacts.
- Summarize the core task in one English sentence.
- Check whether the request is clear and sufficiently scoped.
- If not clear, route to `Claude`, output the CP1 routing block, and ask clarifying questions immediately.
- Classify the task using the inline CP1 routing guide below.
- Decide:
  - model ownership
  - whether cross-validation is needed
- Build one `TASK_CONTEXT_BUNDLE` for the next bounded task:
  - `TASK_ID`
  - `CONTEXT_REFS`
  - `HYDRATED_CONTEXT`
- Output the exact `# CP1 ROUTING DECISION` block before the first Task call.

| Task Category | Model | Cross-Validation | Notes / Triggers |
| --- | --- | --- | --- |
| Pure Frontend / UI / Styling | Gemini | No | Fastest path |
| Pure Backend / Logic / API | Codex | No | Use cross-validation only if the task becomes high-impact or architecture-heavy |
| Full-Stack / Architecture | Cross-Validation (Codex + Gemini) | Yes | Both models run in parallel |
| Docs / Comments / Simple Fix | Claude | No | Usually no external models |
| Debugging / Performance | Codex | No | Escalate to cross-validation only if the failure mode stays ambiguous |
| Infrastructure / DevOps | Codex | No | Use cross-validation only for high-risk changes |
| Data / ML / Analytics | Codex | No | Use cross-validation only if the task becomes unusually complex |
| Testing / Test Coverage | Cross-Validation (Codex + Gemini) | Yes | Useful when tests span frontend and backend behavior |
| Cross-Cutting / Security | Codex | Yes | Extra safety layer |
| Uncategorized / Ambiguous | Claude | No | Fail-closed: ask clarifying questions immediately |

## CP2: External Execution

Run CP2 only when CP1 routes the bounded task to `Gemini`, `Codex`, or `Cross-Validation`.

Goal:
- The external model performs the actual work.
- The external model returns the final code/files directly.

Required CP2 input:
- compressed original user request
- task-scoped context bundle built from CP0 artifacts:
  - `TASK_ID`
  - `CONTEXT_REFS`
  - `HYDRATED_CONTEXT`
- CP1 task summary
- success criteria and verification command for the bounded task
- explicit file set
- for follow-up turns on the same worker session: only changed refs, new hydrated snippets, and updated spec gaps

Output contract:
- Return complete final file content for each modified file whenever practical.
- If full file content is impractical, return a unified diff patch instead.
- Use `# EXTERNAL RESPONSE PROTOCOL v1.1`.
- Allow an optional `## CONTEXT ARTIFACTS` section for reusable discoveries that later tasks can reference.

## CP3: Reconciliation

Run CP3 only after CP2 when:
- CP1 chose `Cross-Validation`
- any external model response reports a conflict, overlap, or other non-trivial feedback

Claude must:
- parse every `# EXTERNAL RESPONSE PROTOCOL v1.1` block returned from Codex and/or Gemini
- compare `SUMMARY`, `FILES MODIFIED`, `SPEC COMPLIANCE`, `CLARIFICATIONS NEEDED`, and `NEXT STEPS / CONTINUATION`
- decide whether to proceed, retry external execution, continue the same external session, or ask the user

Decision rules:
- if all models say `Meets Spec? YES` and there are no conflicts, proceed to CP4
- if any model says `PARTIAL` or `NO`, identify the gap and decide whether to retry or fix through external execution
- if `CLARIFICATIONS NEEDED` is present, answer internally if possible; otherwise ask the user
- if any model says `CONTINUE_SESSION`, continue with that model on the same bounded task
- if conflicting edits are reported on the same file, resolve against the original requirement as the source of truth
- if no files were modified but `Meets Spec? YES`, treat the task as completed and proceed to CP4

CP3 constraints:
- do not apply file edits in CP3
- output the exact `# CP3 RECONCILIATION COMPLETE` block

## CP4: Final Spec Review

Run CP4 as the final step of the workflow:
- after CP3 when reconciliation was needed
- directly after CP2 when no reconciliation was needed
- directly after `Claude`-only tasks

Goal:
- perform a pure spec review
- verify whether the result satisfies the original user requirement and the CP1 success criteria

Required CP4 input:
- original user request
- CP1 task summary
- CP1 success criteria
- all files modified by CP2 and reconciled by CP3, if any

CP4 rules:
- review spec satisfaction only
- do not review code quality, style, redundancy, or best practices
- return one of `PASS`, `PARTIAL`, or `FAIL`

Output contract:
- output the exact `# CP4 SPEC REVIEW COMPLETE` block
- if `PASS`, the task is complete
- if `PARTIAL` or `FAIL`, identify the missing or incorrect requirements and recommend the next action

## User Override

- "Use Codex" / "Use Gemini" / "Cross-validate" force corresponding routing.
- "Do not use external models" forces `CLAUDE` for docs and coordination only.
