# Recommendation: use the built-in `implement` workflow, not a custom one

## Decision

No custom workflow needed. Do not author a `.openmcp/workflows/*.yaml` file for this.

The openmcp-workflows skill's first workflow step is explicit: "If the task is a
single implement, review, or consult, use the built-in - do not author a
workflow." Custom workflows exist only for genuine multi-stage DAGs where one
stage's output feeds the next (e.g. review-then-fix chains, plan-then-implement,
fan-out analysis).

"Fix a null-pointer bug in `src/parser.py` and commit" is a single write stage:

- One agent edits the file and commits.
- No upstream stage produces findings that a later stage consumes.
- No parallel read passes to fan out.
- No cross-stage `${stages.*}` data flow.

Wrapping this in a one-stage YAML would add a file to maintain and validate while
buying nothing over the built-in.

## What to run instead

Submit a built-in `implement` job against the OpenMCP-registered project:

- workflow: `implement` (built-in, no file required)
- inputs:
  - `prompt`: "Fix the null-pointer bug in src/parser.py."
  - `commit_message`: e.g. "Fix null-pointer dereference in src/parser.py"

The `implement` workflow runs a write stage that can edit files and commit, which
is exactly the shape of this task.

## When this would flip to a custom workflow

Author a DAG only if the ask grows to multiple wired stages, for example:

- "Review parser.py, then fix the findings, then commit" -> review (read) -> fix
  (write). That is the canonical review-and-fix example in the skill.
- "Run 3 reviewers in parallel, then fix" -> a `read` stage with `fanout: 3`
  feeding a `write` fix stage.

Until the task has that multi-stage shape, the built-in is the correct choice.
