<!-- refract-shared-version: 1.2.0 -->

# Phase 1 — Decision Notes


## Task 1

### Decisions made
- none

### Spec deviations
- Added targets_unavailable to approved_errors list.
- tool-contract.md defines targets_unavailable as an approved error.
- test-contracts.sh lines 50 to 59 enforce exact set equality.
- Without targets_unavailable, contract test assertion fails deterministically.
- Expected set includes targets_unavailable from tool-contract.md.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: bash plugin/tests/run.sh failed initially.
- AssertionError: {job:summary, result:{text, error, next_offset}}.
- AssertionError: approved_errors set equality failed missing targets_unavailable.
- With changes, bash plugin/tests/run.sh exits 0.
- All session-start and contract tests passed.
- Root cause (bugfix only): none

## Task 2

### Decisions made
- No product code changed.
- Updated server/web/src/integration/dashboard-flow.test.jsx test assertions.
- Added waitFor enabled assertion before clicking buttons.
- Wrapped getJobOutput spy assertion inside waitFor block.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: npx vitest run src/integration/dashboard-flow.test.jsx passed.
- All 8 integration dashboard flow tests pass.
- Root cause (bugfix only): Dialog submit buttons render disabled initially.
- Asynchronous form state changes enable submit buttons.
- Tests clicked buttons before React state settled.
- Disabled DOM buttons drop click events silently.
- Spies on API submission were never called.
- In addition, getJobOutput fired asynchronously in effects.
- Synchronous assertions on getJobOutput ran too early.
- Waiting for button enablement resolved test flakiness.
- No product code was changed.
