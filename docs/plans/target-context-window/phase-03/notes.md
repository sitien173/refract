# Phase 3 Decision Notes

Append one task block per bundled notes template. Record actual RED/GREEN evidence.

## Task 1

### Decisions made
- Used visible label "Context window capacity" with id `target-context-window`, `min="1"`, `step="1"`, and `aria-describedby="target-context-window-help"`.
- Validated `contextWindow` via strict digits check `/^\d+$/`, safe integer check `Number.isSafeInteger`, and positive check `num > 0`. Empty input trims to `null`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  RED: `npx vitest run src/screens/Targets.test.jsx src/components/ConfigEditorSafety.test.jsx` failed with 10 failed tests (missing `contextWindow: null` in create target payload, missing context capacity input and label, unhandled integer create, unhandled blank clearing, unhandled validation rejections, unhandled draft preservation, and unhandled conflict reload).
  GREEN: `npx vitest run src/screens/Targets.test.jsx src/components/ConfigEditorSafety.test.jsx` passed with 41 passed tests across 2 files.
- Root cause (bugfix only): - none

## Task 2

### Decisions made
- Show the cumulative estimate explanation only when the server marks `context_used_tokens` as `estimated`; provider-reported context usage remains unqualified by this caption.
- Render remaining percentage as unavailable when capacity or context usage is missing, rather than implying 100% remaining.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `cd server/web && npm test -- --run src/components/JobDetails.test.jsx -t 'Estimated context explanation'` initially failed 2 assertions: expected estimate caption absent and erroneous 100% rendered with unknown usage. After `JobDetails.jsx` changes, same command passed (4 passed, 35 skipped).
- Task regression: `cd server/web && npm test -- --run src/screens/Targets.test.jsx src/components/ConfigEditorSafety.test.jsx` passed 41 tests across 2 files.
- Root cause (bugfix only): Unknown context usage did not prevent a supplied remaining percentage from displaying; estimated context had no explanatory caption.

## Task 3

### Decisions made
- Documented optional global target TOML capacity, clearing semantics, configured-capacity precedence, provider usage precedence, qualified cumulative fallback, cache handling, estimation limitations, and historical telemetry persistence.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- `cd server && uv run pytest -q`: 1250 passed, 23 skipped, 15 deselected.
- `cd server/web && npm test`: 286 passed across 22 files.
- `cd server/web && npm run build -- --outDir /tmp/refract-target-context-window-baseline`: exit 0; output isolated to `/tmp`; tracked packaged assets unchanged (working tree contains no packaged asset changes).
- `git diff --check`: passed.
- Root cause (bugfix only): - none

## Task 4 — Coordinator spec-cycle repairs

### Decisions made
- Explain cumulative usage only when context-used has a non-null value, source `derived`, and quality `estimated`; retain the estimated badge for provider observations with estimated quality.
- Render remaining percentage according to the server measurement when capacity is known, without an extra frontend usage-null check.
- Hydrate capacity from public `contextWindow` only; do not accept the internal spelling as an alias.
- Added edit submission coverage asserting an integer `contextWindow` payload.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Before rendering fixes, `cd server/web && npm test -- --run src/components/JobDetails.test.jsx -t 'provider snapshot|provider percentage|capacity is known'` showed the inappropriate estimate caption and suppressed provider percentage. After fixes, `cd server/web && npm test -- --run src/components/JobDetails.test.jsx -t 'Estimated context explanation'` passed 5 selected tests.
- RED -> GREEN: Added edit integer submission coverage. Initial run exposed an assertion type mismatch (`toHaveValue('64000')` against numeric input); corrected to number and `cd server/web && npm test -- --run src/screens/Targets.test.jsx -t 'submits integer contextWindow when editing'` passed.
- Fresh full checks after repairs: `cd server && uv run pytest -q`: 1250 passed, 23 skipped, 15 deselected; `cd server/web && npm test`: 288 passed across 22 files; `cd server/web && npm run build -- --outDir /tmp/refract-target-context-window-baseline`: exit 0, isolated output; no tracked packaged asset modifications. `git diff --check` passed.
- These are the accepted fresh checks for the repair cycle; previous cycle results are not relied upon as acceptance evidence.
- Root cause (bugfix only): Estimate caption checked quality without source; frontend usage-null guard masked server-reported percentage; hydration recognized undocumented `context_window` alias.

## Task 5 — Cycle 2 dirty-draft regression test

### Decisions made
- Replaced the ineffective parent rerender with a direct `TargetEditor` rerender carrying a changed target and revision while the capacity draft is dirty.
- The strengthened test verifies the draft remains visible and the subsequent update uses that draft with the original protected revision.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN characterization: `cd server/web && npm test -- --run src/screens/Targets.test.jsx -t 'preserves dirty contextWindow draft when target and revision props refresh'` passed with the normal editor guard. Temporarily disabling that guard made the same test fail because refreshed capacity `99000` replaced draft `80000`; restored production file unchanged and reran successfully.
- Fresh full checks: `cd server && uv run pytest -q`: 1250 passed, 23 skipped, 15 deselected; `cd server/web && npm test`: 288 passed across 22 files; `cd server/web && npm run build -- --outDir /tmp/refract-target-context-window-baseline`: exit 0, isolated output; tracked packaged assets unchanged. `git diff --check` passed.
- Root cause (bugfix only): Existing test rerendered the parent without changed editor props or waiting for a refresh, so it did not exercise dirty-draft protection.
