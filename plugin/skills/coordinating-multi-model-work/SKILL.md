---
name: coordinating-multi-model-work
description: Three-gate Plan -> Execute -> Review workflow for coordinating a coordinator, Codex (back-side), and agy (front-side). Load first for any planning, routing, execution, or review action.
---

# Coordinating Multi-Model Work

Three roles. The **Coordinator** plans, routes, executes, reviews, and
integrates. **Codex** owns back-side work: backend, API, database, infra,
CI/CD, Docker, scripts, server tests. **agy** owns front-side work: UI, CSS,
layout, motion, canvas/SVG, client, multimodal, front-end tests.

This skill is the coordinator's workflow. Worker-facing detail lives in the
shared contracts referenced under Gate 2. User instructions override everything
here.

## Core rule

Route by **side**. Use **Cross-Validation (CV)** only when work is:

- **Full-stack** -- backend and frontend tightly coupled.
- **Unclear** -- requirements, owner, or architecture ambiguous.
- **High-impact** -- public API, security boundary, data migration, breaking change, or irreversible infra/architecture.

For CV, ask Codex and agy the same narrow question with `reasoning="high"`,
reconcile the answers, then route implementation to the correct owner.

---

# Gate 1 — Plan

Gather just enough context to route. Define one phase as 2-4 related tasks, a
file set, and clear `Done When` checks. Then output:

```text
# ROUTE
- Owner: Coordinator | Codex | agy | Cross-Validation
- Reason: [one line]
- Done When: [tests, build, lint, or acceptance checks]
```

| Work type | Owner |
|---|---|
| Simple edit, rename, doc tweak, clarification | Coordinator |
| Back-side work | Codex |
| Front-side work | agy |
| Full-stack, unclear, or high-impact | Cross-Validation |
| Full-stack phase | Split into back/front sub-phases |
| Ambiguous owner | Ask user |

---

# Gate 2 — Execute

The Coordinator executes the routed phase directly. Run CV first when required,
then act on the resolved owner:

- **Back-side** (backend, API, DB, infra, CI/CD, Docker, scripts, server tests):
  call `mcp__plugin_superpowers-ccg_openmcp__run` with `backend="codex"`.
- **Front-side** (UI, CSS, layout, motion, canvas/SVG, client, front-end tests):
  call `mcp__plugin_superpowers-ccg_openmcp__run` with `backend="agy"`.
- **Simple edit** (rename, doc tweak, one-line fix): make it yourself.

Workers edit files directly; on-disk files are the source of truth. Always pass
absolute paths, reuse the cached `SESSION_ID` for same-phase continuation, and
send only `FIX:` + delta context for same-phase fixes. On MCP failure or a
rejected `SESSION_ID`, output `BLOCKED` and ask the user — never retry blindly
or switch owner without consent.

One commit per task (`phase-<N>.task-<M>: <summary>`); collect the hashes and do
not squash until Review PASS. Append per-task notes to
`docs/plans/<slug>/phase-<NN>/notes.md` and the worker's full external response
to `docs/plans/<slug>/phase-<NN>/journal.md`. For feature/bugfix work load
`test-driven-development`, `systematic-debugging`, and
`verifying-before-completion` via Skill: failing test before production code,
root cause before any fix, fresh evidence before any completion claim.

## Dispatch prompt

Write the phase prompt to `docs/plans/<slug>/phase-<NN>/prompt.md` (inline only
for one- or two-sentence tasks). Point it at the materialized contracts:

```text
<project>/.agents/shared/worker-contract.md    # how a worker executes
<project>/.agents/shared/erp.md                 # response format
<project>/.agents/shared/notes-template.md       # notes.md template
<project>/.agents/shared/journal-template.md     # journal.md template
<project>/.agents/BACKEND.md                      # Codex domain rules
<project>/.agents/FRONTEND.md                     # agy domain rules
```

Edit the plugin's `shared/` and root domain templates, never the materialized
`.agents/` copies.

---

# Gate 3 — Review

Review every phase before calling it complete. Run the `Done When` checks and
verify requested behavior, changed-file scope, integration result, and fresh
test/build/lint evidence. Missing fresh evidence is a `FAIL`.

For feature and bugfix work, also confirm a failing test existed before the fix,
now passes, and bug fixes carry root-cause evidence. Missing test-first or
root-cause evidence forces `FAIL`.

Review each worker commit with `git show <hash>`. Output:

```text
# REVIEW
- Spec Status: PASS | PASS_WITH_DEBT | FAIL
- Next: done | debt + owner | retry/clarify
```

`PASS_WITH_DEBT` needs a clear non-blocking debt note; `FAIL` blocks completion.
Reject the phase if commit hashes, notes task blocks, or the journal external
response are missing. After PASS, squash the phase into one Conventional Commit
(`feat|fix|test|refactor|docs|chore|perf|build|ci|style|revert`).

Skip review only for docs-only coordination phases, one-line trivial edits, or
empty changes.

## Cross-Validation output

```text
# CROSS-VALIDATION
- Agreement: [shared conclusions]
- Divergences: [disagreements and chosen resolution]
- Next owner: Codex | agy | Coordinator
```

---

# Resume artifacts

For multi-phase, multi-session plans only. Layout:

```text
docs/plans/<slug>/
  PLAN.md
  .handover.md
  phase-01/{prompt,notes,journal}.md
```

`.handover.md` is the resume pointer; the Coordinator rewrites it after every
state change. It tracks current phase, status, owner, cached worker session IDs,
next action, read-first files, completed tasks, blockers, decisions, and
uncommitted files. A new session reads `.handover.md` first, then only the
listed `journal.md` files -- never scan every phase folder unless the handover
is missing or corrupt.

---

# Hard rules

- One phase, one owner, one review.
- Coordinator executes Gate 2 directly: simple edits itself, worker tasks via MCP.
- Route by side; use CV only when full-stack, unclear, or high-impact.
- Absolute paths for MCP workers; reuse cached `SESSION_ID`, send `FIX:` + delta for same-phase fixes.
- On MCP failure or rejected `SESSION_ID`, output `BLOCKED` and ask the user.
- Feature/bugfix work is test-first; bugs are root-cause-first.
- No completion claim without fresh evidence.
- Edit plugin templates, never materialized `.agents/` copies.
- User instructions override this skill.
