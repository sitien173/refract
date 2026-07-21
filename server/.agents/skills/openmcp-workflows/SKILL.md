---
name: openmcp-workflows
description: Select OpenMCP built-in workflows and compose safe parent job chains. Use when deciding between implement, review, and consult; sequencing review and fix jobs; preserving context across dependent work; or replacing requests for unsupported custom workflow YAML with supported job chains.
---

# OpenMCP workflows and job chains

OpenMCP exposes exactly three workflows:

- `implement` changes files in an isolated worktree and may produce a commit.
- `review` performs read-only code review.
- `consult` performs read-only analysis or advice.

Project-defined `.openmcp/workflows/*.yaml` files are not loaded. Do not author
custom workflow files. Use parent job chains for multi-step work.

Read [references/workflow-reference.md](references/workflow-reference.md) for
inputs, chaining rules, and integration behavior.

## Guardrails

- Choose workflow by intent, never by provider or target.
- Use `implement` only when file changes may be required.
- Use `review` for evidence-based quality findings.
- Use `consult` for analysis that is not code review.
- Set `parent_job_id` only for genuinely dependent jobs.
- A parent must have succeeded and produced a commit before a child starts from
  it.
- Keep one linear implementation chain so integration remains unambiguous.
- Integrate implementation jobs only; review and consult jobs are read-only.
- Never create `.openmcp/workflows` YAML.

## Workflow

### 1. Classify each step

| Intent | Workflow |
| --- | --- |
| Modify repository files | `implement` |
| Review code or an implementation | `review` |
| Inspect, plan, explain, or advise | `consult` |

A single-step request should use one built-in directly.

### 2. Build a parent chain when needed

Common reviewed implementation:

```text
implement -> review
```

Review with a required fix:

```text
implement -> review -> implement fix
```

Consultation before implementation:

```text
consult -> implement
```

Pass the previous job ID as `parent_job_id` only when the next job must inherit
its committed state. A read-only parent with no commit cannot anchor a child
worktree; include relevant findings in the next prompt when needed.

### 3. Preserve context intentionally

Use stable `context_key` values such as:

```text
feature-x/implementation
feature-x/review
feature-x/fix
```

Reuse a key only when conversational continuity is useful. Parent chains carry
Git state; context keys carry backend conversation state.

### 4. Pass precise inputs

All workflows require `inputs.prompt`. `implement` may also use
`inputs.commit_message`.

```json
{
  "workflow": "implement",
  "inputs": {
    "prompt": "Implement validation and run focused tests.",
    "commit_message": "feat: validate input"
  }
}
```

### 5. Integrate the approved implementation

- If implementation succeeds without review, integrate it when requested.
- If review passes, integrate the reviewed implementation.
- If a fix follows review, integrate the successful fix job.
- Never integrate `review` or `consult`.

## Responding to custom-workflow requests

Explain that custom workflow files are unsupported. Translate the requested DAG
into built-in jobs and parent links. State the ordered calls, prompts, profiles,
and integration point instead of producing YAML.

## Handoff

Report the chosen workflow sequence, parent relationships, context keys,
profiles, and which implementation job is eligible for integration.
