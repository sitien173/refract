---
name: coordinating-multi-model-work
description: Three-gate Plan -> Execute -> Review workflow for coordinating a coordinator, codex for backend work, and agy for frontend work. Load first for any planning, routing, execution, or review action.
---

# Coordinating Multi-Model Work

Three roles. The **Coordinator** plans, routes, verifies, and integrates.
**codex** owns backend work: API, database, infrastructure, CI/CD, Docker,
scripts, and server tests. **agy** owns frontend work: UI, CSS,
layout, motion, canvas/SVG, client, multimodal, front-end tests.

This skill is the coordinator's workflow. Worker-facing detail lives in the
shared contracts referenced under Gate 2. User instructions override everything
here.

## Core rule

Route implementation by **side**. Cross-Validation is a consultation, never an
implementation owner. Use it only when work is:

- **Full-stack** -- backend and frontend tightly coupled.
- **Unclear** -- requirements, owner, or architecture ambiguous.
- **High-impact** -- public API, security boundary, data migration, breaking change, or irreversible infra/architecture.

Split tightly coupled full-stack work into backend and frontend phases first.
If ownership remains unclear after Cross-Validation, ask the user.

---

# Gate 1 — Plan

Gather just enough context to route. Define one phase as 2-4 related tasks, a
file set, and clear `Done When` checks. Then output:

```text
# ROUTE
- Owner: Coordinator | codex | agy
- Consult: none | Cross-Validation
- Reason: [one line]
- Done When: [tests, build, lint, or acceptance checks]
```

| Work type | Owner |
|---|---|
| Direct edit, rename, doc tweak, clarification | Coordinator |
| Backend work | codex |
| Frontend work | agy |
| Full-stack work | Split into backend/frontend phases |
| Unclear or high-impact work | Cross-Validation consultation |
| Still ambiguous after CV | Ask user |

## Cross-Validation procedure

1. Send the same narrow, read-only question to codex and agy.
2. Use fresh sessions with `reasoning="high"` and `timeout_s=600`.
3. Do not let either worker edit files during consultation.
4. If either call fails, output `BLOCKED` and ask the user.
5. Reconcile agreement and divergences before choosing the owner.

---

# Gate 2 — Execute

The Coordinator manages the routed phase. Run CV first when required, then act
on the resolved owner:

- **Backend** (API, DB, infra, CI/CD, Docker, scripts, server tests):
  call `mcp__plugin_superpowers-ccg_openmcp__run` with `backend="codex"`.
- **Frontend** (UI, CSS, layout, motion, canvas/SVG, client, front-end tests):
  call `mcp__plugin_superpowers-ccg_openmcp__run` with `backend="agy"`.
- **Direct edit** (rename, doc tweak, one-line fix): make it yourself.

Before any phase write, require a clean Git index and clean declared phase files.
Record the starting commit as `phase_base`. Unrelated unstaged files may remain,
but workers must not touch them. Output `BLOCKED` when planned files overlap
existing changes.

Workers edit files directly; on-disk files are the source of truth. Workers
never stage, commit, reset, or squash. Reuse `SESSION_ID` only when its cached
phase matches the active phase. Send only `FIX:` plus delta context for
same-phase fixes. Use `timeout_s=900` for implementation calls.

After every MCP call, check `success` before using other fields. Cache only a
successful, non-empty `SESSION_ID`. Preserve the previous identifier on failure.
On MCP failure or a rejected identifier, update the handover, output `BLOCKED`,
and ask the user. Never retry blindly or switch owners without consent.

Append per-task notes to `docs/plans/<slug>/phase-<NN>/notes.md` and the worker's
full external response to `journal.md`. Load `test-driven-development` for
features and bug fixes. Load `systematic-debugging` for bugs, test failures, and
unexpected behavior. Load `verifying-before-completion` for every phase.

## Dispatch prompt

Write the phase prompt to `docs/plans/<slug>/phase-<NN>/prompt.md` (inline only
for one- or two-sentence tasks). Point it at the absolute bundled contract paths
injected by `SessionStart`:

```text
<plugin-root>/shared/worker-contract.md    # how a worker executes
<plugin-root>/shared/erp.md                # response format
<plugin-root>/shared/notes-template.md     # notes.md template
<plugin-root>/shared/journal-template.md   # journal.md template
```

Never copy these contracts into the consuming repository.

---

# Gate 3 — Review

Review every phase before calling it complete. Run the `Done When` checks and
verify requested behavior, changed-file scope, integration result, and fresh
test/build/lint evidence. Missing fresh evidence is a `FAIL`.

For feature and bugfix work, also confirm a failing test existed before the fix,
now passes, and bug fixes carry root-cause evidence. Missing test-first or
root-cause evidence forces `FAIL`. A user-approved TDD exception must be recorded
in `notes.md` with replacement validation evidence.

## Code-quality review

For every code-changing phase, route a code-quality review to **codex**. The
Coordinator does not perform it. Call the MCP tool with `backend="codex"`, an
explicit reviewer prompt, and `timeout_s=600`. Do not require a named profile.
Skip only for docs-only phases, trivial one-line edits, or empty changes.

Run it in a **fresh session**: leave `SESSION_ID` empty so codex reviews with no
implementation context. Never pass the implement step's cached `SESSION_ID`
(`session_refs.codex`), and do not overwrite that cached implement session with
the reviewer's — the reviewer must stay independent of the author.

Fold findings into Spec Status. Correctness or security findings force
`FAIL`; style or quality findings become `PASS_WITH_DEBT` with a debt note.
Append the full response under `## Quality Review` in `journal.md`.

Require this review response shape:

```text
# CODE QUALITY REVIEW
- Status: PASS | PASS_WITH_DEBT | FAIL
- Findings: [severity, path, line, actionable fix]
- Scope checked: [paths]
```

Review the working-tree diff against `phase_base`. Confirm every changed path
appears in the declared phase files or phase artifacts. Output:

```text
# REVIEW
- Spec Status: PASS | PASS_WITH_DEBT | FAIL
- Next: done | debt + owner | retry/clarify
```

`PASS_WITH_DEBT` needs a clear non-blocking debt note; `FAIL` blocks completion.
Reject the phase if notes task blocks, the implementation response, or required
evidence is missing.

After PASS, the Coordinator stages only approved phase files and phase artifacts.
Verify the staged path set before committing. Create one Conventional Commit
(`feat|fix|test|refactor|docs|chore|perf|build|ci|style|revert`). Then record its
hash in `journal.md` and `.handover.md`. Commit those state updates separately as
`chore(plan): record phase <N> handover`. Never reset or squash history.

Skip review only for docs-only coordination phases, one-line trivial edits, or
empty changes.

## Cross-Validation output

```text
# CROSS-VALIDATION
- Agreement: [shared conclusions]
- Divergences: [disagreements and chosen resolution]
- Next owner: codex | agy | Coordinator
```

---

# Resume artifacts

For every executable plan. Layout:

```text
docs/plans/<slug>/
  PLAN.md
  .handover.md
  phase-01/{prompt,notes,journal}.md
```

`.handover.md` is the resume pointer; the Coordinator rewrites it after every
state change. It carries YAML frontmatter plus a short body:

```yaml
---
status: ACTIVE | BLOCKED | DONE  # ACTIVE and BLOCKED prevent a fresh start
topic: <one-line plan topic>     # matched against new requests on resume
current_phase: <N>               # 0 before Phase 1 starts
owner: coordinator | codex | agy
next_action: "Execute Phase <N>"
phase_base: <commit|null>            # commit recorded before phase writes
session_refs: { phase: <N>, codex: <id|null>, agy: <id|null> }
read_first: [ <file>, ... ]      # files a resuming session must read
completed_tasks: [ { phase, task, summary }, ... ]
completed_phases: [ { phase, commit, summary }, ... ]
---
```

Body: blockers, decisions, and uncommitted files. A new session reads
`.handover.md` first, then only the `journal.md` files named in `read_first` --
never scan every phase folder. If frontmatter is missing or malformed, read
`PLAN.md` and current-phase artifacts, then ask the user before execution.

---

# Hard rules

- One phase, one implementation owner, one review.
- Coordinator manages Git. Workers never change repository history.
- Route by side; use CV only when full-stack, unclear, or high-impact.
- Set MCP workers' `cd` to the repo root. Repository paths are relative to it.
- Contract paths are absolute paths from the installed plugin.
- Reuse `SESSION_ID` only within its recorded phase.
- On MCP failure or rejected `SESSION_ID`, output `BLOCKED` and ask the user.
- Feature/bugfix work is test-first; bugs are root-cause-first.
- Code-quality review routes to codex in a fresh session without named profiles.
- No completion claim without fresh evidence.
- Never run `git reset` or squash phase history.
- Update `.handover.md` after every state change.
- User instructions override this skill.
