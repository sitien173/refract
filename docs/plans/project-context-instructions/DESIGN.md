# Project Context Instructions

## Purpose

Let an MCP client set a project-level system prompt and worker context
instruction before submitting a job, and have the backend worker receive it
through its own harness CLI context mechanism rather than through the job
prompt.

## Harness research

Verified on 2026-08-28 against codex 0.150.1, claude 2.1.220, pi 0.84.2, and the
installed Antigravity CLI.

| Harness | Project files read on a fresh session | Merge semantics | System-prompt flag |
|---|---|---|---|
| `codex` | Walks the Git root down to `--cd`. Per directory it reads at most one of `AGENTS.override.md`, `AGENTS.md`, `project_doc_fallback_filenames`. Also reads `~/.codex/AGENTS.md`. | Shadowing within a directory, concatenation across directories. Total size capped by `project_doc_max_bytes`. | None |
| `pi` | Per directory, the first hit of `AGENTS.override.md`, `AGENTS.md`, `AGENTS.MD`, `CLAUDE.md`, `CLAUDE.MD`. Suppressed entirely by `--no-context-files`. | Shadowing within a directory. | `--system-prompt`, repeatable `--append-system-prompt` |
| `claude` | `<root>/CLAUDE.md`, `<root>/.claude/CLAUDE.md`, `<root>/CLAUDE.local.md`, `<root>/.claude/rules/*.md`. Suppressed by `--safe-mode`. `.claude/CLAUDE.md` and `CLAUDE.local.md` are gated on `--setting-sources` including `projectSettings` and `localSettings`. | Additive. | `--system-prompt`, `--append-system-prompt` |
| `agy` | `GEMINI.md` and `AGENTS.md`, and only when the directory is a known agy project. `.agents/rules/*.md` is plugin-scoped and is not read as project context. | Additive. | None in `--print` mode |

Verified by running each harness in a temporary repository containing distinct
marker tokens in `AGENTS.md`, `GEMINI.md`, and `.agents/rules/openmcp.md`, then
asking the harness to list the tokens it had been instructed to include.

Three consequences drive the design. `AGENTS.override.md` is a shadowing slot in
both codex and pi, so writing it at the project root suppresses the repository's
own root `AGENTS.md` for those workers. No single filename is read by all four
harnesses. Agy loads no project context at all until the directory is a known
agy project, and the current adapter never passes `--new-project`.

## Decisions

- Name the tool `context_init(project_id, workflow, instruction)`.
- Scope one instruction per `(project_id, workflow)` pair.
- Treat an empty `instruction` as a clear of that pair.
- Persist instructions in the OpenMCP database, not on disk.
- Materialize the harness artifact in `TargetExecutor`, immediately before the
  harness launch, and remove it in a `finally` block.
- Never shadow the repository's own context files.
- Never modify a file that Git tracks. Generated files are always created fresh.
- Refuse the job when a target file exists and is tracked by Git.
- Exclude generated files through `$GIT_COMMON_DIR/info/exclude`.
- Do not modify `.gitignore`.

## Injection mechanism

The mechanism is chosen per backend so injection is always additive.

| Backend | Mechanism | Files written |
|---|---|---|
| `claude` | `--append-system-prompt <instruction>` | none |
| `pi` | `--append-system-prompt <instruction>` | none |
| `codex` | `AGENTS.override.md` at the project root, containing the instruction followed by the repository's own root `AGENTS.md` inlined verbatim | 1 |
| `agy` | `GEMINI.md` at the project root, containing the instruction only | 1 |

`--append-system-prompt` survives `--safe-mode` on claude and
`--no-context-files` on pi, so isolated targets still receive the instruction.

The composed codex file preserves project guidance that `AGENTS.override.md`
would otherwise shadow. When the repository has no root `AGENTS.md`, the
generated file contains the instruction only. Nested `AGENTS.md` files below the
root are unaffected, because codex still reads them at their own directory
level. When a worker edits `AGENTS.md` during a job, the composed file stays at
the content captured at launch for the remainder of that job.

The agy file needs no composition, because agy reads `GEMINI.md` and `AGENTS.md`
additively. A generated `GEMINI.md` therefore adds the instruction without
suppressing the repository's own `AGENTS.md`.

Appending a managed block into an existing tracked `GEMINI.md` or `AGENTS.md`
and stripping it afterwards was considered and rejected. Git exclusion does not
apply to tracked files, the tree goes dirty mid-job so the Coordinator
misattributes the block to the worker, a worker running under `--yolo` can
commit the block into history, and a crash or cancellation between append and
strip leaves a tracked file modified.

## Lifecycle

1. The client calls `context_init` with a project, a workflow, and instruction
   text. The runtime stores the row and returns the stored state.
2. The client submits a job. `ExecutionPlan` snapshots the instruction at
   submission time, so a later `context_init` never changes a queued job.
3. `TargetExecutor` resolves the backend, then either appends the CLI flag or
   writes the file and registers the Git exclusion.
4. The harness runs and loads the instruction through its own discovery.
5. `TargetExecutor` removes any generated file in a `finally` block, including
   on cancellation, timeout, and failure.

`ProjectScheduler` runs at most one job per project at a time
(`scheduler.py:104-136`, the `_active_projects` guard), so two jobs in one
project can never contend for the same generated path.

## Git exclusion

Generated paths are appended once to `$GIT_COMMON_DIR/info/exclude` inside a
delimited managed block. Verified behavior:

- `$GIT_COMMON_DIR/info/exclude` is honored in the main checkout and in every
  linked worktree.
- `.git/worktrees/<name>/info/exclude` is not read by Git. Per-worktree exclude
  files do not exist.

One write therefore covers every worktree of the repository, is never tracked,
and requires no commit. The block is written before the first materialization
and left in place afterwards, so a crash between write and cleanup still leaves
the leftover file invisible to `git status` and to `git add -A` run by a worker.

The daemon sweeps leftover generated paths for a project at startup and before
the first job of a project, removing only files it recognizes by its own header
marker.

## Errors

| Condition | Behavior |
|---|---|
| Unknown `project_id` | `context_init` raises, matching `task_guide`. |
| Unknown `workflow` | `context_init` raises through `get_workflow`. |
| Target path exists and is tracked by Git | Job fails `REQUEST_FATAL`, error names the path. No file is written or removed. |
| Target path exists, untracked, carries the managed marker | Overwritten. Treated as a leftover. |
| Target path exists, untracked, no marker | Job fails `REQUEST_FATAL`. Foreign file, not ours to move. |
| Exclude file not writable | Job fails `REQUEST_FATAL` before any file is written. |
| Project root is not a Git repository | Skip exclusion, still materialize, log a warning. |

## Discovery

Add `openmcp://projects/{project_id}/context_instructions` returning the stored
instruction per workflow, matching the existing project profiles resource.

## Data

Add a `context_instructions` table keyed on `(project_id, workflow)` with the
instruction text and an updated timestamp, cascading on project delete. This is
schema version 7. Existing rows and records are unaffected, and the table is
created empty, so no data migration is required.

## Non-goals

- Instruction content templating or variable substitution.
- Per-target or per-model instructions.
- User-level or global instructions outside a project.
- Editing the repository's own `AGENTS.md`, `CLAUDE.md`, or `GEMINI.md`, or any
  other file Git tracks.
- Editing `.gitignore` or any tracked file.
- Committing, staging, or otherwise touching Git history.

## Open item: agy project registration

Agy loads project context only when the working directory is a known agy
project. The current adapter passes `--dangerously-skip-permissions`,
`--log-file`, `--conversation`, and `--print`, but never `--new-project`
(`agy.py:164-176`). A generated `GEMINI.md` is therefore ignored on the first
job in a repository that agy has not seen before.

This is a pre-existing gap rather than one this feature introduces, and it needs
a decision before the agy path ships. Adding `--new-project` to the adapter is
the obvious fix, but it changes adapter behavior for every agy job, not only
those carrying an instruction. Treat it as a separate scoped change.

## Testing

- Store, replace, and clear an instruction per workflow.
- Reject an unknown project and an unknown workflow.
- Snapshot the instruction into the execution plan at submission.
- Compile `--append-system-prompt` for claude and pi, including isolated
  targets.
- Compose the codex file with and without a repository root `AGENTS.md`.
- Generate the agy `GEMINI.md` and confirm a sibling `AGENTS.md` still loads.
- Remove generated files after success, failure, timeout, and cancellation.
- Refuse a job when the target path is tracked by Git.
- Refuse a job when an untracked foreign file occupies the target path.
- Overwrite a leftover file carrying the managed marker.
- Verify the exclude block hides the generated path in the main checkout and in
  a linked worktree.
- Verify the exclude block is written once and not duplicated.
- Verify no instruction leaves the working tree changed after a job.
