# Direct Repository Execution and Workflow Simplification

**Status:** Approved

## Context

OpenMCP currently models every job as a generic staged workflow. It creates a private Git branch and primary worktree, creates additional detached worktrees for read stages, copies ignored-file overlays between them, and requires explicit integration for successful write jobs.

That design no longer matches the desired product. OpenMCP now supports only three built-in, single-stage workflows. The generic DAG, worktree, overlay, parent-chain, and integration machinery increases runtime size and couples scheduling, persistence, Git state, and target execution.

The largest concentration is `runtime.py`, which currently owns submission, worktree setup, workflow scheduling, retries, integration, cleanup, target selection, health, and context history. The associated orchestration test file has grown beyond 2,000 lines.

## Goals

- Run every job directly in its registered repository.
- Commit successful implementation changes immediately.
- Serialize all daemon jobs within each project.
- Preserve concurrency between different projects.
- Replace generic staged workflows with fixed one-step jobs.
- Remove overlays, parent chains, and explicit integration.
- Split orchestration responsibilities into focused modules.
- Preserve target failover, health, sessions, context history, cancellation, and durable job records.
- Migrate completed historical jobs into the simplified schema.

## Non-goals

- Redesign backend adapters, process management, logging, or target configuration.
- Add custom workflows or extension points.
- Preserve the removed MCP contract through no-op tools or fields.
- Automatically integrate historical private-branch commits.
- Automatically remove historical worktrees or `openmcp/*` branches.
- Coordinate daemon jobs with manual operator edits.
- Snapshot or restore ignored files.

## Product Decisions

1. Successful `implement` jobs commit directly to the current branch.
2. All jobs for one project run serially in submission order.
3. Jobs for different projects may run concurrently.
4. `job_integrate` and integration states disappear.
5. Stages disappear from execution, persistence, and public models.
6. `parent_job_id` and parent dependency semantics disappear.
7. Local overlays and `.openmcp.local.toml` disappear.
8. Failed and cancelled implementations reset tracked state and remove non-ignored untracked files.
9. Existing completed job history migrates. Unfinished legacy jobs become interrupted.
10. The refactor remains focused on orchestration and directly affected files.

## Architecture

### Runtime facade

`runtime.py` remains the public application facade used by `server.py`. It composes the database, scheduler, job runner, target executor, drivers, and repository adapter. Its public methods remain thin coordinators:

- project registration
- job submission
- job waiting
- cancellation
- whole-job retry
- daemon status and reload
- project, target, and context queries

The facade does not execute Git commands or target failover loops.

### Scheduler

A new `scheduler.py` owns:

- the global `max_jobs` execution limit
- one FIFO queue per project
- the ready-project queue
- the active-project set
- running cancellation events
- completion events
- startup restoration of queued jobs
- clean shutdown

Only one job from a project can be active. A project with additional work is returned to the ready queue after its active job finishes. Waiting same-project jobs never occupy global workers. This prevents one busy project from starving unrelated projects.

Queued cancellation changes the persisted state and leaves a terminal entry that workers skip. Running cancellation sets the job's cancellation event.

### Job runner

A new `execution.py` contains the job lifecycle coordinator. It:

1. loads the persisted job and immutable plan
2. inspects the registered repository
3. requires a clean checkout
4. saves the current HEAD as `base_commit`
5. marks the job running
6. invokes the target executor once
7. commits, verifies, or resets repository state
8. persists the result and final state
9. updates the project's observed HEAD and cleanliness

The job runner does not manage worker capacity or expose MCP models.

### Target executor

Target execution moves from `Runtime` into a focused collaborator in `execution.py`. It retains current behavior:

- ordered target selection
- backend availability checks
- per-target concurrency semaphores
- timeouts
- failover and backoff
- circuit health
- session continuation
- bounded context history
- target and attempt events

It receives one workflow, one target selection, one prompt, one repository path, and one cancellation event. Stage identifiers, lanes, fanout, and stage contexts disappear. The workflow name becomes the context role.

### Repository adapter

`repositories.py` replaces `workspaces.py`. It provides only:

- repository inspection
- HEAD lookup
- change detection
- commit creation
- hard reset
- removal of non-ignored untracked files

It contains no worktree, branch, patch, overlay, or integration operations.

## Source Layout

### New modules

- `scheduler.py`: durable queue execution and project serialization
- `execution.py`: job lifecycle and target execution
- `repositories.py`: direct Git operations

### Reduced modules

- `runtime.py`: composition and public facade
- `workflows.py`: fixed workflow definitions and request validation
- `planning.py`: one immutable target selection per job
- `database.py`: job-level persistence without stages
- `models.py`: simplified public job models
- `server.py`: reduced MCP contract
- `config.py`: remove worktree and run-directory paths

### Removed modules

- `workspaces.py`
- `overlays.py`

Backend modules, `drivers.py`, `processes.py`, and `logging_setup.py` remain structurally unchanged.

## Workflow Model

OpenMCP keeps three fixed workflow definitions:

| Workflow | Capability | Repository behavior |
|---|---|---|
| `implement` | `code` | Commit successful changes |
| `review` | `review` | Require no repository changes |
| `consult` | `consult` | Require no repository changes |

Each job executes exactly once. The workflow module validates:

- the workflow name
- a non-empty prompt
- an optional commit message only for `implement`

The following concepts disappear:

- workflow document parsing
- workflow versions and digests
- stage specifications
- stage modes
- dependency graphs
- fanout
- prompt templates and stage variables
- result-stage selection
- stage-specific timeout overrides

Profiles still map each built-in workflow to `TargetSelection`. Selection-level `max_attempts` and `timeout_s` remain.

## Immutable Plans

`ExecutionPlan` becomes a snapshot for one job:

- profile name
- workflow name
- selected `TargetSelection`
- referenced target configurations

The plan is resolved and persisted during submission. Configuration changes affect only later submissions. Legacy execution-plan shapes are not executable after migration because unfinished legacy jobs become interrupted.

## Public MCP Contract

### Retained tools

- `status`
- `reload`
- `doctor`
- `project_register`
- `task_guide`
- `job_submit`
- `job_wait`
- `job_cancel`
- `job_retry`

### Simplified signatures

```text
job_submit(
    project_id,
    workflow,
    prompt,
    commit_message="",
    context_key="",
    profile="",
)

job_wait(job_id, timeout_s=0)
job_retry(job_id)
```

`commit_message` is rejected for `review` and `consult`.

### Removed contract

- `job_integrate`
- `parent_job_id`
- generic `inputs`
- `from_stage`
- `include_stage_outputs`
- stages in job responses
- branch and integration metadata
- artifacts in job results
- `integrated` and `integration_conflict` states

The remaining job states are:

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`
- `interrupted`

`JobView` retains identity, project, workflow, profile, context key, state, timestamps, and base commit. It exposes job-level target ID and cumulative attempt count. `JobResult` contains text, commit, and error.

A queued job has an empty base commit until execution begins.

## Submission and Scheduling Flow

1. Resolve the project.
2. Validate workflow, prompt, and commit message.
3. Reload project configuration.
4. Resolve and persist the immutable target plan.
5. Create the queued job record.
6. Append the job to its project's FIFO queue.
7. Signal the project as ready if inactive.

Project registration requires a clean Git repository with an attached branch. Job execution repeats both checks because repository state can change while a job waits. A queued job executes against whichever attached branch is current when it starts.

## Execution Flow

### Successful implementation

1. Require a clean repository.
2. Save current HEAD as the job base.
3. Run target failover directly in the repository root.
4. Stage all tracked and non-ignored untracked changes.
5. Commit with the requested message or the existing OpenMCP default.
6. If no changes exist, use the existing HEAD.
7. Persist response text, target, attempts, result commit, and success.
8. Update the project record.

There is no later integration step.

### Successful review or consultation

1. Require a clean repository.
2. Save current HEAD as the job base.
3. Run the selected target directly in the repository root.
4. Inspect the repository after execution.
5. If it remains clean at the same HEAD, persist success.
6. If it changed, reset it and fail the job.

Read workflow output remains valid only when its repository behavior remained read-only.

### Target failure, cancellation, or runtime exception

After execution begins, unsuccessful jobs run:

```text
git reset --hard <base_commit>
git clean -fd
```

The original execution error remains primary. A reset failure is appended to the persisted error. A repository that cannot be restored blocks later jobs through their clean-check preflight.

A queued cancellation never touches the repository.

### Existing dirty state

If execution preflight finds existing changes, the job fails without resetting anything. The daemon did not create those changes and therefore does not remove them.

### Ignored files

Ignored files are directly visible to agents. They are neither committed nor restored by Git. Changes to existing ignored files survive success, failure, cancellation, and recovery. This is the explicit replacement for overlays.

## Recovery and Retry

Startup performs recovery before dispatching queued jobs:

1. Find jobs persisted as running.
2. Mark them interrupted.
3. For each job with a base commit, reset its project to that commit and clean non-ignored untracked files.
4. Record restoration failures in the job error and events.
5. Restore legacy-independent queued jobs into per-project FIFO queues.

Only one job can have been running per project. Interrupted jobs are not automatically retried.

`job_retry(job_id)` accepts failed, cancelled, or interrupted jobs. It:

- reuses the same job ID
- retains the immutable plan
- clears the prior result and error
- retains cumulative target attempt counts
- requeues the entire job
- resolves a new base commit when execution starts

No stage selection or partial resume remains.

If the daemon stops after Git commits but before success is persisted, startup treats the job as interrupted and resets to its saved base. Durability favors a known persisted outcome over preserving an ambiguous commit.

## Persistence

The simplified jobs table stores:

- identity and project
- workflow and profile
- prompt and commit message
- context key
- immutable execution plan JSON
- state
- base commit
- result text and commit
- target ID and cumulative attempts
- error
- creation and update timestamps

Projects, events, context sessions, context turns, and target health remain.

The following persistence disappears:

- workflow JSON
- result-stage identifiers
- parent job IDs
- integration bases
- private branches
- worktree paths
- stage rows
- artifact rows

New executions store results only in SQLite. They do not create transcript, patch, overlay, or run-directory files.

## Database Migration

The migration introduces SQLite `PRAGMA user_version = 5` and rebuilds the jobs table transactionally.

For each legacy job it:

1. extracts `prompt` and `commit_message` from `inputs_json`
2. locates the persisted result stage, falling back to the last ordinal
3. copies stage text, target ID, attempts, commit, and error into job columns
4. copies the immutable plan JSON
5. maps the state
6. preserves timestamps and context identity

State mapping is explicit:

| Legacy state | New state |
|---|---|
| `integrated` | `succeeded` |
| `integration_conflict` | `failed` |
| `queued` | `interrupted` |
| `running` | `interrupted` |
| other terminal states | unchanged |

The rebuild temporarily disables foreign-key enforcement outside its transaction, copies jobs under stable identifiers, drops legacy stages, artifacts, and jobs tables, then runs `foreign_key_check` before committing and reenabling enforcement. Projects, events, contexts, and target health remain intact. Any copy or integrity failure rolls back without changing the existing schema.

Historical successful jobs remain readable. Historical unintegrated commits are not moved into the main repository and cannot be integrated through OpenMCP after upgrading.

Database migration does not mutate registered repositories. Historical worktree directories and `openmcp/*` branches remain for manual cleanup. Documentation provides cleanup commands, but no permanent legacy-worktree implementation remains.

## Documentation Changes

Update:

- `README.md`
- `AGENTS.md`
- MCP tool and resource references
- orchestration and workflow skills
- state-directory documentation
- architecture and lifecycle descriptions

Remove overlay setup, parent-chain guidance, stage output controls, worktree isolation, and integration instructions. Add an upgrade note explaining historical database conversion and optional legacy Git cleanup.

## Testing Strategy

Split `tests/test_orchestration.py` by responsibility:

- `test_scheduler.py`: project FIFO order, same-project serialization, cross-project concurrency, queued cancellation, shutdown
- `test_execution.py`: direct commits, no-change success, read cleanliness, target failures, cancellation resets, startup recovery, whole-job retry
- `test_database.py`: fresh schema, transactional migration, historical result collapse, state mapping, context preservation
- `test_workflows.py`: fixed names, prompt validation, commit-message rules
- `test_planning.py`: profile selection, immutable snapshots, plan parsing
- `test_server.py`: tool schemas, removed integration API, simplified job models

Keep existing focused tests for backends, processes, logging, smoke behavior, and live providers.

Tests use temporary Git repositories and fake drivers. Concurrency tests use events rather than timing assumptions.

## Acceptance Criteria

- Runtime code executes no `git worktree` command.
- Runtime code creates no OpenMCP branches.
- `overlays.py` and `workspaces.py` are removed.
- No stage, overlay, parent, branch, artifact, or integration concept remains publicly.
- Every workflow invokes one target execution sequence.
- Same-project jobs never overlap.
- Different-project jobs can overlap up to `max_jobs`.
- Successful implementations commit directly to the registered branch.
- Successful reviews and consultations leave Git state unchanged.
- Failed, cancelled, and interrupted started jobs restore their base commit.
- Existing dirty state is never reset during preflight failure.
- Registration and execution reject detached HEAD state.
- Legacy completed history remains readable after migration.
- Legacy unfinished jobs become interrupted.
- All offline tests pass.
- `uv run openmcp doctor` passes.
