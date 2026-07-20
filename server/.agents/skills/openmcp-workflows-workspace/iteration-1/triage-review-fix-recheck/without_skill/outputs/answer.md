# triage workflow

A three-stage OpenMCP workflow: `review` -> `fix` -> `verify`.

## Stage graph (dependency order)

1. **review** (`mode: read`, `route: sentinel`) - inspects the request and lists
   the concrete required changes. Read-only, runs in a disposable worktree, cannot
   commit.
2. **fix** (`mode: write`, `route: forge`, `needs: [review]`) - implements the
   change, incorporating the reviewer's findings via `${stages.review.text}`, then
   commits in the job's primary worktree.
3. **verify** (`mode: read`, `route: sentinel`, `needs: [fix]`) - a second reviewer
   confirms the fix addresses the request and the listed changes, consuming both
   `${stages.review.text}` and `${stages.fix.text}`.

## Read vs write

- `review` and `verify` are `read` (no commits).
- `fix` is the only `write` stage, so the "write stages form one ordered chain"
  rule is trivially satisfied.

## Inputs

- `prompt` (string, required) - the request to triage.
- `commit_message` (string, optional) - available to the write stage when committing.

## Result stage

`verify` is the sole terminal stage (nothing depends on it), so `result_stage`
would be inferred; it is set explicitly to `verify` for clarity.

## Data flow

- `fix` references `review` (listed in its `needs`).
- `verify` references both `fix` (direct `needs`) and `review` (transitive via
  `fix`), so both variable references are valid under the loader's dependency rule.

## Install

Copy `triage.yaml` to `<project>/.openmcp/workflows/triage.yaml` and commit it. It
becomes selectable as the `triage` workflow on the next submission (no restart).
