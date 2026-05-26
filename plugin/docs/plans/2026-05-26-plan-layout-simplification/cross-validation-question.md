# Cross-Validation: Plan Layout Simplification

You are reviewing a proposed simplification of a multi-model coordination workflow used by Claude when orchestrating Codex (back-side) and Gemini (front-side) workers.

## Current layout

```
docs/plans/<slug>/
  PLAN.md
  PHASE-<N>.md            # durable phase journal
  .handover.md            # resume pointer; session_refs cache worker SESSION_IDs
  prompts/phase-<N>.md    # dispatch prompt, per phase
  notes/phase-<N>.task-<M>.md   # decision note, PER TASK (2-4 per phase)
  responses/phase-<N>.md  # EXTERNAL RESPONSE block, per phase
```

## Workflow shape

Three gates: Plan -> Execute -> Review. Worker (Codex or Gemini) is dispatched via MCP with an absolute path to `prompts/phase-<N>.md`. Worker:
1. Implements 2-4 tasks per phase.
2. Commits per task with `phase-<N>.task-<M>: subject`.
3. Writes one decision note per task (`notes/phase-<N>.task-<M>.md`).
4. Writes one phase response (`responses/phase-<N>.md`).
5. Emits completion line.

After Review PASS, Claude squashes per-task commits into one `phase-<N>` commit. Task-level notes survive; commits do not.

## Proposed simplifications

**Proposal A:** Decision notes become per-PHASE instead of per-task. One file `notes/phase-<N>.md` aggregating decisions across all 2-4 tasks in the phase.

**Proposal B:** Collapse `prompts/`, `notes/`, `responses/` into one folder (e.g. `phase-<N>/` or `artifacts/`) so each phase's three files cluster together.

## Questions (answer narrowly, ~150 words each)

1. **Proposal A (per-phase notes):** What is gained vs lost? In particular: does the worker still get clear pressure to articulate per-task decisions? Does losing per-task granularity hurt review or future archaeology? Recommend KEEP-PER-TASK / GO-PER-PHASE / HYBRID.

2. **Proposal B (combined folder):** Does clustering by phase (`phase-<N>/{prompt,notes,response}.md`) beat clustering by artifact-type (`prompts/`, `notes/`, `responses/`)? Consider: navigability, git diff readability, scaling to 5-10 phases, and the fact that resume artifacts (.handover.md, PHASE-<N>.md, PLAN.md) stay at the plan-dir root. Recommend FLAT-PER-TYPE / NESTED-PER-PHASE / OTHER.

3. **Other simplifications worth considering** for this workflow (anything beyond the two proposals). One to three concrete ideas only — do not redesign. Examples of the kind of suggestion welcome: merging `PHASE-<N>.md` and `responses/phase-<N>.md` (overlap?), dropping a redundant artifact, smarter naming, eliminating `.gitkeep` placeholders, etc.

## Output format

```
## Q1
Recommendation: KEEP-PER-TASK | GO-PER-PHASE | HYBRID
[reasoning, ~150 words]

## Q2
Recommendation: FLAT-PER-TYPE | NESTED-PER-PHASE | OTHER
[reasoning, ~150 words]

## Q3
1. [idea + one-line rationale]
2. [idea + one-line rationale]
3. [idea + one-line rationale]
```

Do not edit any files. Reply with the answer block only.
