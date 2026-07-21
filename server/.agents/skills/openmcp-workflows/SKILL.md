---
name: openmcp-workflows
description: Author and validate custom multi-stage OpenMCP workflow DAGs stored as .openmcp/workflows/*.yaml. Use this skill whenever the user wants a repeatable multi-step job that the built-in implement/review/consult workflows can't express as a single step - for example review-then-fix chains, plan-then-implement, fan-out analysis, or any pipeline where one stage's output feeds the next. Reach for this skill when the user says "make a workflow", "chain review into a fix", "run N reviewers in parallel", "add a stage that depends on", or describes a fixed sequence of agent steps. Prefer it over hand-writing YAML so the DAG passes OpenMCP validation on the first load.
---

# OpenMCP custom workflows

Built-in `implement`, `review`, and `consult` cover single-step jobs. Author a
custom workflow only when work needs multiple stages wired into a DAG - one
stage's output flowing into the next, or several read stages fanning out.

A workflow declares typed `inputs` and named `stages`. Each stage runs in a
`mode` (`read` or `write`) through a logical `route`, and stages depend on each
other through `needs`. The selected routing profile resolves route names to
targets at submission time, so workflows stay provider-agnostic.

Read [references/workflow-reference.md](references/workflow-reference.md) for the
full field tables and every validation rule before writing a non-trivial
workflow. Re-read the validation section after any load error - the loader is
strict and the message names the exact stage or variable at fault.

## Mental model

- **Callers choose workflows, never modes.** `mode` is an internal execution
  property: `write` stages can commit and share the job's primary worktree;
  `read` stages run in disposable detached worktrees and cannot commit. You pick
  the mode based on whether the stage must change files.
- **Routes are logical roles.** Use profile keys such as `implement`, `review`,
  and `consult`, which the active routing profile maps onto internal route IDs.
  Never put a route ID, target ID, or provider name in a workflow stage.
- **Variables carry data between stages.** A prompt references upstream results
  with `${stages.<stage>.text}`. This only works if the current stage lists that
  stage in `needs`.

## Guardrails

The loader rejects a workflow that breaks any of these, so getting them right
means the workflow works on first submission.

- `version` must be `1`. `name` must match `^[A-Za-z0-9][A-Za-z0-9._-]*$`.
- Every stage needs `mode` (`read` or `write`), `route`, and `prompt`.
- **Write stages must form one ordered chain.** Any two write stages must be
  connected by a dependency path, directly or transitively. Read stages may run
  concurrently. This keeps commits linear and integrable.
- `fanout` is `1`-`16` and only for `read` stages; a write stage cannot fan out.
- A prompt may reference `${inputs.<name>}`, `${project.root}`, and
  `${stages.<stage>.text|outputs|commit}`. A referenced stage must be in the
  current stage's `needs`, or validation fails.
- Set `result_stage` when there is more than one terminal stage. With a single
  terminal stage it is inferred. `result_stage` must be terminal.
- The dependency graph must be acyclic and every `needs` entry must name a real
  stage.

## Workflow

### 1. Decide it needs to be custom

If the task is a single implement, review, or consult, use the built-in - do not
author a workflow. Author one only for a genuine multi-stage shape. State this
briefly if you decide a built-in suffices.

### 2. Name inputs

Declare the inputs the prompts interpolate. `prompt` is the common one; add a
`commit_message` when a write stage commits. Types are `string`, `integer`,
`number`, `boolean`, `object`, `array`. Mark required inputs.

### 3. Lay out stages and dependencies

Give each stage a role-based `route`, a `mode`, and a `context` lane name.
Express ordering with `needs`. Read stages that can run in parallel share no
dependency; write stages must chain.

### 4. Wire data flow

Feed an upstream stage's result into a downstream prompt with
`${stages.<upstream>.text}`, and only reference stages the downstream lists in
`needs`.

### 5. Set the result stage

If one stage is terminal (nothing depends on it), it is inferred. Otherwise set
`result_stage` to the terminal stage whose output is the job result.

## Canonical example: review then fix

```yaml
version: 1
name: review-and-fix
inputs:
  prompt:
    type: string
    required: true
  commit_message:
    type: string
stages:
  review:
    mode: read
    route: review
    context: reviewer
    prompt: "Review this request and list required changes: ${inputs.prompt}"
  fix:
    mode: write
    route: implement
    needs: [review]
    prompt: |
      Implement ${inputs.prompt}
      Address these review findings:
      ${stages.review.text}
result_stage: fix
```

`review` runs read-only, `fix` consumes its findings and commits. `fix` is the
sole terminal stage, so `result_stage: fix` is explicit here for clarity but
would also be inferred.

## Fan-out example

A `read` stage may set `fanout` (2-16) to run several independent passes,
useful for parallel review or exploration:

```yaml
stages:
  survey:
    mode: read
    route: review
    fanout: 3
    prompt: "Independently review: ${inputs.prompt}"
```

## Validate before handing off

Store the file under `<project>/.openmcp/workflows/<name>.yaml` and commit it. It
becomes selectable as a workflow name on the next submission (no restart). If a
job submission returns a validation error, the message names the offending stage
or variable - fix that specific item against the reference rules rather than
rewriting the whole file.

## Handoff

Report the workflow name and file path, the stage graph in dependency order,
which stages write versus read, the required inputs, and the result stage.
