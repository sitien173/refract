# OpenMCP workflow reference

Custom workflows live in `<project>/.openmcp/workflows/*.yaml`. The file stem is
the workflow name used at submission. Built-in `implement`, `review`, and
`consult` always exist and need no file.

## Top-level fields

| Field | Required | Purpose |
| --- | --- | --- |
| `version` | yes | Must be `1`. |
| `name` | yes | Matches `^[A-Za-z0-9][A-Za-z0-9._-]*$`. |
| `inputs` | no | Map of input name to definition. |
| `stages` | yes | Map of stage ID to stage definition. |
| `result_stage` | conditional | Required when more than one terminal stage; else inferred. |

## Inputs

```yaml
inputs:
  prompt:
    type: string
    required: true
  commit_message:
    type: string
```

| Field | Default | Notes |
| --- | --- | --- |
| `type` | `string` | One of `string`, `integer`, `number`, `boolean`, `object`, `array`. |
| `required` | `false` | Missing required inputs reject the submission. |

Input names must match `^[A-Za-z0-9][A-Za-z0-9._-]*$`.

## Stages

```yaml
stages:
  <stage_id>:
    mode: read | write
    route: <logical-role>
    prompt: "..."
    needs: [<stage_id>, ...]
    context: <lane-name>
    fanout: 1
```

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `mode` | yes | - | `read` or `write` only. |
| `route` | yes | - | Logical profile role, such as `implement`, `review`, or `consult`, resolved by the active routing profile. Do not use an internal route or target ID. |
| `prompt` | yes | - | Supports variable interpolation. |
| `needs` | no | `[]` | List of upstream stage IDs. |
| `context` | no | stage ID | Named context lane for continuity. |
| `fanout` | no | `1` | `1`-`16`; `read` stages only. |

Stage IDs must match `^[A-Za-z0-9][A-Za-z0-9._-]*$`.

## Modes

- `write`: may commit; shares the job's primary worktree. Write stages must form
  one ordered chain (every pair connected by a dependency path).
- `read`: cannot commit; runs in a disposable detached worktree; may set
  `fanout` for parallel passes.

Callers select the workflow, not the mode. Mode is chosen by whether a stage
must change files.

## Variables

Interpolated inside `prompt` with `${...}`:

| Variable | Meaning |
| --- | --- |
| `${inputs.<name>}` | A declared input value. |
| `${project.root}` | The project root path. |
| `${stages.<stage>.text}` | Upstream stage final text. |
| `${stages.<stage>.outputs}` | Upstream structured outputs. |
| `${stages.<stage>.commit}` | Upstream commit reference. |

A `${stages.X...}` reference is valid only if `X` is in the current stage's
`needs` (directly or transitively via the dependency chain). Referencing a
non-dependency is rejected.

## Result stage

- Terminal stage = no other stage depends on it.
- Exactly one terminal stage: `result_stage` inferred.
- Multiple terminal stages: `result_stage` required and must name a terminal
  stage.

## Validation rules (loader-enforced)

The loader raises on each of these; the error names the offending item:

1. `version != 1` -> unsupported version.
2. `name` fails the name regex.
3. Unsupported input `type`.
4. Stage missing `mode`, `route`, or `prompt`.
5. `mode` not in `{read, write}`.
6. `fanout` outside `1`-`16`, or `fanout != 1` on a write stage.
7. `needs` references an unknown stage.
8. A stage depends on itself.
9. Dependency graph contains a cycle.
10. Two write stages not connected by any dependency path ("must be ordered").
11. Variable references an unknown input/stage or an unsupported field.
12. Variable references a stage not in `needs`.
13. `result_stage` unknown or not terminal.
14. Multiple terminal stages with no `result_stage`.

## Parent chains vs. workflows

A multi-stage workflow bundles stages into one job. A parent/child job chain
(`parent_job_id` on `job_submit`) links separate jobs across submissions, each
starting from the parent's result commit. Use a workflow for a fixed repeatable
pipeline; use parent chains for ad-hoc, human-in-the-loop iteration.
