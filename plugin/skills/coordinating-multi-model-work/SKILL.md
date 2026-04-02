---
name: coordinating-multi-model-work
description: "Routes bounded implementation tasks to Codex (backend and systems) or Gemini (frontend) via MCP tools. Claude is orchestrator-only and should stay out of the implementation hot path. Use when: implementation, debugging, refactoring, UI work, APIs, databases, scripts, CI/CD, or cross-model arbitration."
---

# Coordinating Multi-Model Work

## Overview

Claude is the orchestrator. It routes tasks, coordinates workers, and integrates results, but never writes implementation code.

Use this module to route one bounded task at a time:
- **Codex** — backend and systems
- **Gemini** — frontend

## Core Rules

1. Reduce the current work to one bounded task with a clear file set and verification command.
2. Route that bounded task to exactly one worker unless there is real architectural uncertainty.
3. Reuse the same worker `SESSION_ID` for follow-up fixes on that task.
4. Ask for the actual final artifact using External Response Protocol v1.1: full file content first, unified diff second, never prototypes or design prose.
5. Use CP3 as a Claude-only reconciliation layer when cross-validation or other non-trivial external feedback appears.
6. Always run CP4 Final Spec Review as the last step.
7. Keep CP4 focused on spec satisfaction only, not code quality or style feedback.

## Cross-Validation

`CROSS_VALIDATION` is rare. Use it only when:
- the task genuinely spans frontend and backend at the same time, or
- two viable designs remain after scope reduction, or
- the failure mode is still ambiguous after one worker pass.

Do not use cross-validation as the default for ordinary implementation work.

## Checkpoint Workflow

Before CP1, do CP0 context acquisition with the Hybrid Context Engine:
- Auggie for semantic "where/what/how"
- Morph WarpGrep for fast parallel search
- Serena for symbols, references, and memory
- Grok Search only for external/current knowledge

At CP1, perform Task Assessment & Routing using the original request, the CP0 context package, and the inline routing guide below, then emit the exact `# CP1 ROUTING DECISION` block.

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

At CP2, if routing is not `Claude`, send the original user request, the full CP0 context package, and the CP1 task summary plus success criteria to the chosen external model. Require External Response Protocol v1.1 with complete final file content preferred and unified diff acceptable.

At CP3, parse every external response block, resolve conflicts or clarifications, and decide whether the task is ready for CP4, needs a retry, or needs user input.

At CP4, use the original user request, the CP1 task summary, the CP1 success criteria, and the modified files to decide `PASS`, `PARTIAL`, or `FAIL`. Do not perform code-quality, style, redundancy, or best-practice review in CP4.

## Response Protocol

All external model prompts must reference Serena memory `global/response_protocol`.

## Reference Files

- `coordinating-multi-model-work/checkpoints.md`
- `coordinating-multi-model-work/routing-decision.md`
- `coordinating-multi-model-work/GATE.md`
- `coordinating-multi-model-work/INTEGRATION.md`
- `coordinating-multi-model-work/review-chain.md`
- `coordinating-multi-model-work/cross-validation.md`
