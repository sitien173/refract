# Collaboration Checkpoints

## Overview

Checkpoints exist to control routing and keep the orchestrator thread small.

The active unit of work is an implementation phase. A good phase contains 2-4 related tasks, one primary executor, one Claude review, and one integration gate.

## CP0: Context Acquisition

- Gather only the minimum context needed to route the next phase.
- Use Auggie for full local codebase context retrieval.
- Use Grok Search only when the task needs external/current knowledge or research.
- Normalize the useful output into small reusable `CONTEXT_ARTIFACTS`.
- End CP0 as soon as the phase and likely owner are clear enough for CP1.

CP0 tool matrix:

| Need | Primary Tool | When to Trigger Grok Search | Fallback |
| --- | --- | --- | --- |
| Local codebase context / implementation anchors | Auggie | Do not trigger Grok Search during normal local-context retrieval | None |
| External / real-world knowledge | Grok Search | When the task mentions "latest", "current", "best practice", an unknown library, or a raw error that needs external research | None |

## CP1: Phase Assessment & Routing

- Run immediately after CP0 completes.
- Read the original user request and the CP0 context artifacts.
- Summarize the active phase in one English sentence.
- Check whether the phase is clear, sufficiently scoped, and contains 2-4 related tasks.
- If not clear, route to `Claude`, output the CP1 routing block, and ask clarifying questions immediately.
- Classify the task using the inline CP1 routing guide below.
- Decide:
  - model ownership
  - whether cross-validation is needed
- Build one `PHASE_CONTEXT_BUNDLE` for the next phase:
  - `TASK_ID`
  - `CONTEXT_REFS`
  - `HYDRATED_CONTEXT`
- Output the exact `# CP1 ROUTING DECISION` block before the first executor call.

| Task Category | Model | Cross-Validation | Notes / Triggers |
| --- | --- | --- | --- |
| UI-heavy visual implementation | Gemini | No | Use only when visual layout, styling, motion, canvas/SVG, or interactions dominate |
| Backend / Logic / API | Codex | No | Default implementation route |
| Full-Stack / Architecture | Codex | No | Use cross-validation only for unresolved architecture conflict |
| Docs / Comments / Coordination | Claude | No | No external executor needed |
| Debugging / Performance | Codex | No | Escalate to cross-validation only if the failure mode stays ambiguous |
| Infrastructure / DevOps | Codex | No | Use cross-validation only for high-risk changes |
| Data / ML / Analytics | Codex | No | Use cross-validation only if the task becomes unusually complex |
| Testing / Test Coverage | Codex | No | Gemini only if tests are mainly visual/UI behavior |
| Cross-Cutting / Security | Codex | No | Add Claude/human review instead of default cross-validation |
| Uncategorized / Ambiguous | Claude | No | Fail-closed: ask clarifying questions immediately |

## CP2: External Execution

Run CP2 only when CP1 routes the phase to `Gemini`, `Codex`, or `Cross-Validation`.

Goal:
- The external model performs the actual work.
- The external model returns the final code/files directly.

Required CP2 input:
- compressed original user request
- phase-scoped context bundle built from CP0 artifacts:
  - `TASK_ID`
  - `CONTEXT_REFS`
  - `HYDRATED_CONTEXT`
- CP1 phase summary
- success criteria, reviewer checklist, and integration checks for the phase
- explicit file set
- for follow-up turns on the same worker session: only changed refs, new hydrated snippets, and updated spec gaps

Output contract:
- Return complete final file content for each modified file whenever practical.
- If full file content is impractical, return a unified diff patch instead.
- Use `# EXTERNAL RESPONSE PROTOCOL v1.1`.
- Allow an optional `## CONTEXT ARTIFACTS` section for reusable discoveries that later tasks can reference.

## CP2 Failure & Fallback

When a CP2 MCP call (`mcp__codex__codex` or `mcp__gemini__gemini`) fails:

### Tiered failure handling

1. **Gemini fallback** — If Gemini fails once with `timeout`, `tool-unavailable`, or session/tool instability, stop using Gemini for that phase and fall back to Codex or Claude-code. Do not spend multiple retries on Gemini.
2. **Codex retry** — If Codex fails with `timeout` or `tool-unavailable`, retry once with identical parameters (including `SESSION_ID` if it was a follow-up).
3. **Fallback** — If Codex still fails, dispatch a Claude-code/Sonnet subagent to implement the phase directly:
   - Use the `Agent` tool with `model: "sonnet"` and `subagent_type: "general-purpose"`.
   - Send the same task context bundle using `prompts/sonnet-fallback-base.md`.
   - The subagent edits files directly via Edit/Write/Bash (no External Response Protocol).
   - After the subagent completes, proceed to CP4 as normal.
4. **Hard BLOCKED** — If the failure reason is `permission-blocked`, do not retry or fall back. Output the `BLOCKED` evidence block per `GATE.md`. The user deliberately denied the tool.

### Cross-validation fallback

If CP1 chose `Cross-Validation` and Gemini fails once, continue with Codex if Codex is available. If Codex also fails after one retry, dispatch ONE Sonnet subagent (not two). The fallback handles the phase as a single implementation.

### Evidence format

When fallback triggers, output:

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI
Status: FALLBACK
Reason: tool-unavailable | timeout | session-failed
Fallback: Codex | Claude-code/Sonnet subagent
```

### CP4 after fallback

CP4 runs identically regardless of whether the MCP worker or the Sonnet subagent performed the work. If CP4 returns `FAIL`, dispatch a bounded follow-up with delta context. If CP4 returns `PASS_WITH_DEBT`, continue only when the debt is explicit and non-blocking.

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
- if any model reports incomplete or failed spec compliance, identify the gap and decide whether to retry or fix through external execution
- if `CLARIFICATIONS NEEDED` is present, answer internally if possible; otherwise ask the user
- if any model says `CONTINUE_SESSION`, continue with that model on the same phase
- if conflicting edits are reported on the same file, resolve against the original requirement as the source of truth
- if no files were modified but `Meets Spec? YES`, treat the task as completed and proceed to CP4

CP3 constraints:
- do not apply file edits in CP3
- output the exact `# CP3 RECONCILIATION COMPLETE` block

## CP4: Phase Review

Run CP4 as the reviewer step for the phase:
- after CP3 when reconciliation was needed
- directly after CP2 when no reconciliation was needed
- directly after `Claude`-only tasks

Goal:
- perform a phase review against the plan
- verify whether the result satisfies the original user requirement, CP1 success criteria, and reviewer checklist

Required CP4 input:
- original user request
- CP1 phase summary
- CP1 success criteria
- reviewer checklist
- integration check results
- all files modified by CP2 and reconciled by CP3, if any

CP4 rules:
- review spec satisfaction only
- do not review broad style, redundancy, or best practices unless they are in the phase checklist
- return one of `PASS`, `PASS_WITH_DEBT`, or `FAIL`

Output contract:
- output the exact `# CP4 SPEC REVIEW COMPLETE` block
- if `PASS`, the task is complete
- if `PASS_WITH_DEBT`, the phase can integrate but debt must be listed
- if `FAIL`, identify the missing or incorrect requirements and recommend the next action

## User Override

- "Use Codex" / "Use Gemini" / "Cross-validate" force corresponding routing.
- "Do not use external models" forces `CLAUDE` for docs and coordination only.
