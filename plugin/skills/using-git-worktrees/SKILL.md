---
name: using-git-worktrees
description: "Use when starting feature work that should not touch the current checkout, before executing an implementation plan, or when the user asks for a worktree or isolated workspace. Detects existing isolation, then prefers a native worktree tool, then falls back to git worktree."
---

# Using Git Worktrees

## Role

This skill owns workspace isolation. It ends with a ready workspace on an
attached branch. `coordinating-multi-model-work` owns everything after that,
including OpenMCP registration.

Order of preference: detect existing isolation, then use a native worktree
tool, then fall back to `git worktree`. Never fight the harness.

## Constraints

- Create at most one worktree per request.
- Use absolute paths for every command after creation.
- Write ignore rules only to `$(git rev-parse --git-common-dir)/info/exclude`.
  A committed `.gitignore` imposes one contributor's layout on everyone.
- Install dependencies and run tests with the project's own documented
  commands. When none can be found, ask.

## Step 0: Detect Existing Isolation

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
BRANCH=$(git branch --show-current)
# Prints a path only inside a submodule. Treat a submodule as a normal repo.
git rev-parse --show-superproject-working-tree 2>/dev/null
```

| Result | Action |
|---|---|
| `GIT_DIR != GIT_COMMON`, not a submodule, on a branch | Report "Already isolated at `<path>` on `<branch>`." Go to Step 2. |
| Same, detached HEAD | Report it. Ask the user for a branch name, because coordination needs an attached branch. Go to Step 2. |
| `GIT_DIR == GIT_COMMON`, or a submodule | Normal checkout. Continue below. |

In a normal checkout, honor any worktree preference already declared in the
user's instructions. Otherwise ask once:

> "Would you like me to set up an isolated worktree? It protects your current
> branch from changes."

If the user declines, work in place and go to Step 2.

## Step 1: Create the Workspace

### 1a. Native tool

With consent given, use a native worktree tool when one exists: a tool such as
`EnterWorktree` or `WorktreeCreate`, a `/worktree` command, or a `--worktree`
flag. Native tools own placement, branching, and cleanup. Running
`git worktree add` beside one creates state the harness cannot see or manage.
Then go to Step 2.

### 1b. Git fallback

Use this only when no native tool exists.

**Branch name.** Derive a kebab-case name from the task, or from the plan slug
when one exists. Confirm it with the user. When the branch already exists,
ask whether to reuse it or pick another name.

**Directory.** Take the first rung that matches:

1. A worktree directory declared in the user's instructions.
2. An existing `.worktrees/` at the project root.
3. An existing `worktrees/` at the project root.
4. Default: `.worktrees/` at the project root.

**Ignore check.** A project-local directory must be ignored before creation:

```bash
git check-ignore -q "$LOCATION"
```

When it is not ignored, append it to the exclude file named in Constraints.

**Create:**

```bash
git worktree add "$LOCATION/$BRANCH_NAME" -b "$BRANCH_NAME"
```

On a permission or sandbox error, tell the user the sandbox blocked worktree
creation, then run Steps 2 and 3 in the current directory.

## Step 2: Project Setup

Find the project's documented setup command in the README, a Makefile, or
package scripts. When none is documented, select by lockfile:

| File present | Command |
|---|---|
| `package-lock.json` | `npm ci` |
| `pnpm-lock.yaml` | `pnpm install --frozen-lockfile` |
| `yarn.lock` | `yarn install` |
| `uv.lock` | `uv sync` |
| `poetry.lock` | `poetry install` |
| `requirements.txt` only | `pip install -r requirements.txt` |
| `Cargo.toml` | `cargo build` |
| `go.mod` | `go mod download` |

Several package managers or no match: ask the user. No manifest at all: skip
setup.

## Step 3: Verify Clean Baseline

Run the project's documented test command: a `test` script, a `test` make
target, or the README instruction. When none is found, ask.

- **Tests fail:** report the failures and ask whether to proceed or
  investigate. Proceeding past a red baseline is the user's call.
- **Tests pass:** report ready.

## Step 4: Hand Off

When the work is coordinated, return to the Coordinator's setup. It registers
this worktree root with OpenMCP, so the worktree gets its own `project_id` and
job queue. Plan anchors under `refs/plans/` live in the shared `.git` directory
and resolve from every worktree. In `untracked` plan mode, a new worktree starts
without `docs/plans/`; copy the plan directory in before resuming there.
`.git/info/exclude` is shared, so the copy stays excluded.

**Symlinked `docs`.** In worktree mode, check whether `docs` is a symlink to the
shared checkout's `docs`:

```bash
test -L <worktree path>/docs && readlink -f <worktree path>/docs
```

When it is, the Write/Edit tool refuses to create plan files under `docs/plans/<slug>/`.
Do not retry Write/Edit. Create/Update `PLAN.md`, `.handover.md`, and the phase prompt through
the shell into `docs/plans/<slug>/` of the shared checkout, using the resolved
path above.

## Output Format

```text
# WORKSPACE
- Path: <absolute path>
- Branch: <name> | detached, branch pending
- Isolation: existing | native tool | git fallback | in place
- Setup: <command> -> <result> | skipped
- Baseline: <command> -> <N passed, M failed> | not run - <reason>
```
