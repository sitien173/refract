<!-- ccg-shared-version: 12.0.0 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Updated both marketplace lookups to resolve the repository-root marketplace from the plugin directory's parent.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `plugin/tests/test-contracts.sh` initially failed because the relocated root marketplace did not yet exist; after moving it and setting `source` to `./plugin`, the test passed (`contract tests passed`).

## Task 2

### Decisions made
- Kept the server workflow's existing OS/Python matrix and steps while setting job-level command working directory and the lockfile cache glob.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- `plugin/tests/run.sh` passed after moving/configuring the workflow files (`session-start tests passed`, `contract tests passed`, plugin validation passed).

## Task 3

### Decisions made
- Preserved the existing `*.sh text eol=lf` attribute rule at repository root.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- `plugin/tests/run.sh` passed after moving `LICENSE` and `.gitattributes`.

## Task 4

### Decisions made
- Consolidated and deduplicated ignore patterns into comment-grouped root rules, omitting the specified legacy directories and lockfile.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- `claude plugin validate .` passed and reported the root marketplace.
- `plugin/tests/run.sh` passed.
- `cd server && uv sync --all-extras --frozen && uv run pytest`: 546 passed, 3 deselected.
- `cd server/web && npm test`: 203 passed.
- `git ls-files plugin/.claude-plugin/marketplace.json plugin/.gitignore server/.gitignore server/.claude plugin/.github server/.github` printed nothing.
- `git status --porcelain --ignored server/.venv server/web/node_modules` showed both paths ignored (`!!`).
- Diff inspection showed the expected phase paths plus the pre-existing modification to `docs/plans/refract-monorepo/.handover.md` (present before this work and left untouched).
