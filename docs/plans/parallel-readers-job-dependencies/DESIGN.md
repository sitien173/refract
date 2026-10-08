# Parallel Readers and Job Dependencies Design

**Status:** Confirmed 2026-10-01; merged into `docs/plans/mcp-v2-claude-code/DESIGN.md` on 2026-10-07
**Consultation:** Read-only external consultation succeeded through the `consult` profile.

## Purpose

Allow concurrent read-only jobs within one registered project.
Keep jobs with write access exclusive within that project.
Add explicit dependencies to `job_submit`.

This document specifies behavior; implementation has not started.

## Users and Success Criteria

Users are operators submitting independent analyses and dependent jobs.

| Criterion | Required behavior |
|---|---|
| Same-project concurrency | Independent read-only jobs can overlap, including identical workflows |
| Session safety | Identical session scopes remain serialized |
| Write safety | Jobs with write access never overlap other project jobs |
| Dependencies | Every dependency succeeds before its dependent executes |
| Automatic stopping | Unsuccessful dependencies cancel queued descendants without execution |
| Queue progress | Dependency-blocked jobs consume no workers or admission slots |
| Fairness | Eligible exclusive jobs cannot starve behind later readers |
| Compatibility | Default settings preserve existing same-project serialization |

Actual concurrency remains subject to every applicable capacity limit.

## Constraints and Non-Goals

### Confirmed constraints

- All jobs use the registered project directory.
- Existing context keys provide session isolation.
- Dependencies reference existing jobs within the same project.
- Dependency links remain immutable after submission.
- Jobs retain existing lifecycle states.
- Global and target concurrency limits remain effective.
- Configuration changes never reclassify already-submitted jobs.

### Non-goals

- Concurrent jobs with write access.
- Workspaces, worktrees, or Git automation within OpenMCP.
- Independent session lanes or lane merging.
- Cross-project dependencies or forward dependency references.
- Automatic dependency-result injection into prompts.
- Dependency mutation or general-purpose workflow orchestration.
- Project-specific reader-capacity overrides.
- Live resizing of scheduler capacity.

## Chosen Approach

Use reader/writer admission with existing context scopes.
Persist admission classes derived from saved execution plans.
Evaluate dependencies before reserving scheduler capacity.

Rejected alternatives:

- Parallel writers: conflicts with the confirmed shared-directory policy.
- Independent session lanes: requires lane-aware history and session replacement.
- Workflow-based classification: workflow names do not enforce read-only access.

## Architecture and Data Flow

### Admission classes

| `access_mode` | Admission rule |
|---|---|
| `parallel_read` | May overlap independent `parallel_read` jobs within the project |
| `exclusive` | Runs alone within the project |

Derive `access_mode` from the immutable execution-plan snapshot.
Every possible target must be configured read-only.
Every possible target must have verified read-only enforcement.
Both conditions include fallback targets.
Otherwise, classify the job as `exclusive`.

An advisory prompt does not establish read-only enforcement.
Unsupported adapters and mixed plans remain `exclusive`.
Execution must preserve the enforcement required for admission.

### Submission API

Add the optional `depends_on` parameter to `job_submit`.
The parameter accepts a list of existing job IDs.
Omitted or empty means no dependencies.

Example submission:

```json
{
  "project_id": "registered-project-id",
  "workflow": "consult",
  "prompt": "Review security implications after the prerequisite jobs succeed.",
  "context_key": "security-analysis",
  "depends_on": ["existing-job-id-1", "existing-job-id-2"]
}
```

Dependency results are not automatically injected into this prompt.

### Persistence

Persist each job's `access_mode` alongside its execution-plan snapshot.

Add the `job_dependencies` table:

```text
job_id
dependency_job_id
```

The table records immutable, unique job-to-dependency links.
Both IDs reference existing job records.
Index `dependency_job_id` for reverse dependency lookup.

Validate and insert the job and links atomically.
Reject unknown, duplicate, or other-project dependency IDs.
Require dependencies to pre-exist.
These backward-only immutable links prevent cycles structurally.
No general graph-cycle traversal is required.

### Session isolation

Reserve this scope throughout each job's execution:

```text
project_id + workflow + context_key
```

Jobs sharing this scope remain serialized.
This restriction also applies to `fresh_session=True`.
Fresh-session success can replace shared session state.

Same-workflow jobs can overlap using distinct context keys:

```json
{"workflow": "consult", "context_key": "security-analysis"}
```

```json
{"workflow": "consult", "context_key": "performance-analysis"}
```

Omitting `context_key` retains the current workflow-derived default.
Same-workflow jobs using that default remain serialized.

Session and history storage require no new lane semantics.

### Admission sequence

1. Validate dependency IDs and resolve the execution-plan snapshot.
2. Derive the admission class from verified execution capabilities.
3. Persist the job and dependency links atomically.
4. Evaluate dependency readiness before reserving worker capacity.
5. Apply project admission, session-scope, and global-capacity limits.
6. Reserve admission before dispatching a concrete job.
7. Retain existing target-capacity enforcement during execution.
8. Persist completion and apply dependency outcomes.
9. Release reservations and reevaluate eligible queued jobs.

Readiness checks and reservations must share one synchronization boundary.
Waiting dependencies reserve neither workers nor project admission slots.
Target-capacity waiting retains existing execution behavior.
Release every reservation through completion, cancellation, and exception paths.

### Ordering and fairness

Maintain submission order among dependency-ready candidates.
Dependency-blocked jobs never become queue barriers.

The earliest dependency-ready `exclusive` job becomes an admission barrier.
Earlier eligible readers may run or finish.
Later readers cannot start before that exclusive job completes.
The exclusive job waits until existing project readers finish.

A dependency-blocked exclusive job is not a barrier.
Independent eligible jobs may pass it.
Once dependency-ready, it becomes a barrier at its position.
Already-running readers finish; additional later readers wait.

Identical session scopes cannot overlap under either admission class.
Completion and cancellation trigger admission reevaluation.
Dependency transitions trigger reevaluation through reverse dependency links.
No dependency-polling loop is introduced.

### Job visibility

Expose these fields through job resources and dashboard data:

```text
access_mode
depends_on
waiting_on
waiting_reason
```

`depends_on` lists the persisted dependency IDs.
`waiting_on` lists unfinished dependency IDs for queued jobs.
`waiting_reason` explains the current admission blocker.
Waiting metadata is derived from current admission conditions.
Cancellation errors and events preserve dependency causes.

## Errors and Edge Cases

### Dependency outcomes

| Dependency condition | Dependent outcome |
|---|---|
| All dependencies succeeded | Eligible for scheduler admission |
| Any dependency queued or running | Remains queued without reserving capacity |
| Any dependency failed, cancelled, or interrupted | Cancelled automatically without execution |

Record the causal dependency ID, state, and cancellation reason.
Apply cancellation transitively to queued descendants.
Notify subscribers and release completion waiters for cancelled dependents.

Submission against unsuccessful terminal dependencies creates a cancelled job.
Submission returns the resulting state, including immediate cancellation.
Validation errors leave no partially persisted job or links.

Commit cancellation before allowing the upstream job's retry.
This prevents retries from hiding an observed dependency failure.

### Retry semantics

Retries retain the existing job ID and dependency links.
Only failed, cancelled, or interrupted jobs remain retryable.

| Dependency condition during dependent retry | Outcome |
|---|---|
| All dependencies succeeded | Queue the dependent for admission |
| Any dependency queued or running | Queue the dependent with dependency waiting |
| Any dependency terminally unsuccessful | Reject retry with a dependency-specific explanation |

Parent retries never revive cancelled descendants automatically.
The caller must explicitly retry each cancelled dependent.

### Restart and shutdown

Mark previously running jobs `interrupted` during restart recovery.
Propagate dependency cancellations before admitting remaining queued jobs.
Rebuild dependency readiness and admission state from persisted records.

Cancellation and shutdown release project and session reservations.
Dependency-blocked jobs remain cancellable through the existing API.
No additional `blocked` lifecycle state is introduced.

## Migration

### Configuration

Add the daemon setting `max_project_readers`.

```toml
[daemon]
max_project_readers = 2
```

Default: `1`, preserving existing same-project serialization.
Values must be positive integers.
Changes take effect after daemon restart.

Global `max_jobs` and target `max_concurrency` remain effective.
Increasing reader capacity alone cannot override either limit.
No project-specific override is added.

Existing configuration interfaces must accept and expose this setting.
Report the effective startup-bound capacity separately from pending changes.

### Database compatibility

Add job admission classes and the dependency table through migration.
Existing jobs migrate as `exclusive` with no dependency links.
Existing queued jobs never gain parallel admission automatically.

Session and history tables remain unchanged.
Already-submitted jobs retain their saved plans and admission classes.
New submissions use the configuration effective at submission.

## Testing

These are acceptance requirements, not executed test results.
Use deterministic events rather than timing-based sleeps.

| Area | Required evidence |
|---|---|
| Reader concurrency | Same-project, same-workflow readers overlap with distinct context keys |
| Session protection | Identical scopes serialize, including fresh-session jobs |
| Read-only enforcement | Repository writes are denied; unsupported or mixed plans remain exclusive |
| Exclusive admission | No reader/exclusive or exclusive/exclusive overlap |
| Fairness | Ready exclusive jobs prevent later-reader starvation |
| Dependency readiness | Every dependency succeeds; waiting consumes no worker capacity |
| Queue progress | Blocked dependencies never prevent independent eligible work |
| Cancellation | Failed, cancelled, and interrupted parents cancel queued descendants |
| Retry | Parent retries never revive descendants; explicit dependent retries work |
| Recovery | Restart propagates interruption before admitting queued dependents |
| Capacity | Global, project-reader, and target limits hold simultaneously |
| Validation | Invalid links reject submission without partial persistence |
| Compatibility | Default capacity and migrated jobs preserve serialization |
| Visibility | Resources expose dependencies, waiting conditions, and cancellation causes |

Cover cancellation cascades across several dependency levels.
Cover failure-versus-retry races and immediate dependency cancellation.
Cover reservation release after execution errors and shutdown.
Cover notifications and completion waiters for automatically cancelled jobs.

Primary coverage belongs in scheduler, execution, database, and server tests.
Retain existing FIFO and cross-project concurrency regressions.

## Risks and Open Questions

### Risks

- Adapter verification is required before admitting parallel readers.
- External filesystem changes are outside scheduler admission control.
- Session-scope defaults intentionally serialize same-workflow submissions.
- Global and target limits can still restrict reader overlap.
- Cancellation must commit before retry can change dependency state.
- Startup-bound capacity requires clear effective-configuration reporting.

### Open questions

No product decisions remain open within the confirmed scope.
Implementation must establish which adapters satisfy read-only enforcement.

### Consultation and source evidence

External consultation supported the confirmed existing-context approach.
The consultation was read-only and made no repository changes.

Relevant current integration points:

- `src/openmcp/scheduler.py`: project queues, admission, cancellation, completion.
- `src/openmcp/runtime.py`: submission, recovery, retries, scheduler setup.
- `src/openmcp/planning.py`: immutable execution-plan snapshots.
- `src/openmcp/drivers.py`: adapter-specific read-only enforcement.
- `src/openmcp/execution.py`: session reuse and target capacity.
- `src/openmcp/database.py`: jobs, sessions, history, terminal transitions.
- `src/openmcp/config.py`: daemon configuration and project restrictions.
- `src/openmcp/config_mutation.py`: configuration mutation validation.
- `src/openmcp/server.py`: submission parameters and job resources.
- `src/openmcp/models.py`: public job and dashboard representations.
- `src/openmcp/dashboard.py`: job visibility and configuration interfaces.

Clean baseline anchor:

```text
refs/plans/parallel-readers-job-dependencies/base
```
