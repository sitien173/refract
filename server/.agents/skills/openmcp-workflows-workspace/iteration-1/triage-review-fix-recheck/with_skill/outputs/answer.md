# triage workflow

Reusable three-stage pipeline. Install at `.openmcp/workflows/triage.yaml`.

## Stage graph (dependency order)

1. `review` (read, route `sentinel`) - inspects the request, lists required changes.
2. `fix` (write, route `forge`, needs `review`) - implements the change using the
   review findings, then commits.
3. `verify` (read, route `sentinel`, needs `fix`) - verifies the committed fix.

## Read vs write

- `review` and `verify` are `read` (no commits, disposable worktrees).
- `fix` is the only `write` stage, so the write chain is trivially ordered.

## Inputs

- `prompt` (string, required) - the request to triage.
- `commit_message` (string, optional) - message for the fix commit.

## Result stage

`verify` is the sole terminal stage, so `result_stage` is inferred; it is set
explicitly for clarity.

## Data flow

- `fix` reads `${stages.review.text}` (review is in its `needs`).
- `verify` reads `${stages.fix.commit}` (fix is in its `needs`).

## Validation notes

Passes loader rules: `version: 1`, name matches the regex, single write stage,
no read fanout, acyclic graph, and every `${stages.*}` reference names a stage in
that stage's `needs`.
