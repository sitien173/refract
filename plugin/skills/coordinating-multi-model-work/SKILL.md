---
name: coordinating-multi-model-work
description: "Three-gate workflow (Plan → Execute → Review)"
---

Coordinating Multi-Model Work

 Use skill coordinate work between coordinator, Codex, Gemini **Coordinator** handles planning routing review integration simple tasks.
 **Codex** owns back-side work: backend API database infra CI/CD Docker, scripts, server tests.
 **Gemini/ agy** owns front-side work: UI CSS layout motion canvas/SVG, client interactions multimodal, front-end tests.

 ## Core Rule

 Route by **side**.

 Use **Cross-Validation (CV)** only when work is:

 **Full-stack**: backend and frontend tightly coupled.
 **Unclear**: requirements, owner, or architecture ambiguous.
 **High-impact**: public API, security boundary, data migration, breaking change, irreversible infra, or major architecture decision.

 For CV, ask Codex Gemini same narrow question with `reasoning="high"`, compare answers, resolve differences, then route implementation to correct owner.

 User overrides always win.

 ---

# Gate 1 — Plan

 Gather only enough context to route work.

 Define one phase as:

* 2–4 related tasks
* relevant files
* clear `Done When` checks

 Then output:

 ```text
# ROUTE
- Owner: Coordinator| Codex| Gemini| Cross-Validation
- Reason: [one line]
- Done When: [tests, build, lint, or acceptance checks]
 ```

 ## Routing Guide

| Work type                                    | Owner                            |
| ---------------------------------------------| -------------------------------- |
| Simple edit, rename, doc tweak, clarification| Coordinator                      |
| Back-side work                               | Codex                            |
| Front-side work                              | Gemini                           |
| Full-stack, unclear, or high-impact          | Cross-Validation                 |
| Clear single-side work                       | Route directly to side owner     |
| Full-stack phase                             | Split into back/front sub-phases |
| Ambiguous owner                              | Ask user                         |

 ---

# Gate 2 — Execute

 ## Coordinator

 For simple work:

* Edit directly.
* Commit logical changes.

 ## Codex/ Gemini

 Call `mcp__openmcp__run`.

 Use:

* `backend="codex"` for back-side work.
* `backend="gemini"` or `backend="agy"` for front-side work.

 Rules:

* Workers edit files directly. On-disk files are source of truth.
* Reuse cached `SESSION_ID` when continuing same phase.
 For same-phase fixes, send only `FIX:` plus delta context.
 Always pass **absolute paths**.
 On MCP failure or rejected `SESSION_ID`, output `BLOCKED` ask user. Do not retry or switch executor without consent.

 ## Worker Discipline

 Feature bugfix phases must follow:

* `test-driven-development`: failing test before production code.
* `systematic-debugging`: root cause before fixing bugs.
* `verifying-before-completion`: no completion claim without fresh evidence.

 Workers must record:

* RED → GREEN result
* root-cause evidence
* task notes
* commits
* journal entry

 ## Dispatch Prompt

 Write worker prompts to:

 ```text
 docs/plans/<slug>/phase-<NN>/prompt.md
 ```

 Inline prompts only for very small one- or two-sentence tasks.

 Worker prompts should point to:

 ```text
 <project>/.agents/shared/worker-contract.md
 <project>/.agents/shared/erp.md
 <project>/.agents/BACKEND.md
 <project>/.agents/FRONTEND.md
 ```

 Do not edit materialized `.agents` files directly. Edit plugin templates instead.

 ## Worker Commits

 Workers make one commit per task:

 ```text
 phase-<N>.task-<M>: <summary>
 ```

 worker returns hashes in `## COMMITS`.

 coordinator reviews each commit with:

 ```bash
 git show <hash>
 ```

 After Review PASS, coordinator squashes phase into one Conventional Commit:

 ```text
 <type>[scope]: <description>
 ```

 Allowed types:

 ```text
 feat| fix| test| refactor| docs| chore| perf| build| ci| style| revert
 ```

 ## Worker Notes

 After each task, worker appends to:

 ```text
 docs/plans/<slug>/phase-<NN>/notes.md
 ```

 Each task gets:

 ```markdown
 ## Task <M>

 ### Decisions made
- none

 ### Spec deviations
- none

 ### Tradeoffs accepted
- none

 ### Assumptions
- none

 ### Follow-ups for human
- none
 ```

 ## Phase Journal

 Each phase has:

 ```text
 docs/plans/<slug>/phase-<NN>/journal.md
 ```

 coordinator creates it at phase start.

 worker appends its full external response before completion line.

 ---

# Worker Response Format

 ```text
# EXTERNAL RESPONSE

 ## META
- Phase/ Owner/ SessionID/ Started/ Finished/ Plan dir

 ## SUMMARY
 [one sentence]

 ## FILES MODIFIED
| Action| Path| Change |

 ## COMMITS
- phase-<N>.task-<M>: <hash> <subject>

 ## NOTES
- phase-<NN>/notes.md

 ## SPEC COMPLIANCE
- Meets Spec? YES| WITH_DEBT| NO — [one line]

 ## CLARIFICATIONS NEEDED
 None

 ## NEXT
 TASK_COMPLETE| CONTINUE_SESSION| HANDOVER_TO_CLAUDE
 ```

 Then end with:

 ```text
 Phase <N> completed. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
 ```

 ---

# Gate 3 — Review

 Review every phase before calling it complete.

 Run phase `Done When` checks.

 Verify:

* requested behavior
* changed file scope
* integration result
* fresh test/build/lint evidence

 Initial status:

 ```text
 PASS| PASS_WITH_DEBT| FAIL
 ```

 Missing fresh evidence means failure.

 For feature bugfix work verify:

* failing test existed before fix
* test now passes
* bug fixes include root-cause evidence

 Missing test-first or root-cause evidence is CRITICAL forces `FAIL`.

 Skip only for:

* docs-only coordination phases
* coordinator one-line trivial edits
* empty file changes

 ## Review Output

 ```text
# REVIEW
- Spec Status: PASS| PASS_WITH_DEBT| FAIL
- Next: done| debt+ owner| retry/clarify
 ```

 `PASS_WITH_DEBT` requires clear non-blocking debt note.

 `FAIL` blocks completion.

 Reject phase if any are missing:

* commit hashes
* notes task blocks
* journal external response

 ---

# Cross-Validation Output

 ```text
# CROSS-VALIDATION
- Agreement: [shared conclusions]
 Divergences: [disagreements and chosen resolution]
 Next owner: Codex| Gemini| Coordinator
 ```

 ---

# Resume Artifacts

 Use resume artifacts only for multi-phase multi-session plans.

 Plan layout:

 ```text
 docs/plans/<slug>/
  PLAN.md
  .handover.md
  phase-01/
    prompt.md
    notes.md
    journal.md
 ```

 ## `.handover.md`

 coordinator rewrites this after every state change.

 tracks:

* current phase
* status
* owner
* cached worker session IDs
* next action
* read-first files
* completed tasks
* blockers
* decisions
* uncommitted files

 A new session reads `.handover.md` first, then only listed `journal.md` files.

 Do not scan every phase folder unless handover is missing or corrupt.

 ---

# Hard Rules

* One phase, one owner, one review.
* Route by side.
 Do not use Cross-Validation unless work is full-stack, unclear, or high-impact.
 Workers edit files directly; no draft-then-reimplement.
 Workers make one commit per task.
 Coordinator reviews worker commits, then squashes after PASS.
 Missing commits, notes, or journal entries fail Review.
 Use absolute paths for MCP workers.
 Feature and bugfix work must be test-first.
 Bugs require root-cause-first debugging.
* No completion claim without fresh evidence.
* User instructions override this skill.

