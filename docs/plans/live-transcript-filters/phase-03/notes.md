<!-- ccg-shared-version: 10.6.0 -->

# Phase 3 — Decision Notes

## Task 1

### Decisions made
- Rebuild once from the dirty working tree because current assets omit Phase 2 filters.
- Protect dirty frontend source using pre-build and post-build SHA-256 checks.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Pre-build assets: index-CEkAVloK.css, index-CLuS4yuS.js.
- Protected source hashes:
  - web/src/components/JobDetails.jsx: ca371d980820be85a55644bea9e369cbbb51997e8dec423db688ff0fc2e9eec2
  - web/src/components/JobDetails.test.jsx: da5284cc8b891a7736e6cd57c50b635a6ec6877dfef5e7fb880a1957b04804bd
  - web/src/components/JobTranscript.jsx: 0159f1bdb4824fa54fdfaf267ec6a2f0e05238c8a74c35e07e8685d55fb08337
  - web/src/components/JobTranscript.test.jsx: 0765c63094ae3a7b0109d86d69b1a0ebef20ee8695de32bdcab567b99c2c5a55
  - web/src/styles/app.css: 8a5010e683914109eb9c7ef8ef0dc7088c1ae69c4326c00860abb07e040879b9

## Task 2

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- npm --prefix web run build passed. Generated index-D-nShQgS.js (364.33 kB) and index--OvfbQj5.css (46.35 kB).

## Task 3

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Post-build source hashes match pre-build exactly:
  - web/src/components/JobDetails.jsx: ca371d980820be85a55644bea9e369cbbb51997e8dec423db688ff0fc2e9eec2
  - web/src/components/JobDetails.test.jsx: da5284cc8b891a7736e6cd57c50b635a6ec6877dfef5e7fb880a1957b04804bd
  - web/src/components/JobTranscript.jsx: 0159f1bdb4824fa54fdfaf267ec6a2f0e05238c8a74c35e07e8685d55fb08337
  - web/src/components/JobTranscript.test.jsx: 0765c63094ae3a7b0109d86d69b1a0ebef20ee8695de32bdcab567b99c2c5a55
  - web/src/styles/app.css: 8a5010e683914109eb9c7ef8ef0dc7088c1ae69c4326c00860abb07e040879b9

## Task 4

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- src/openmcp/dashboard_static/index.html references only /dashboard/assets/index-D-nShQgS.js and /dashboard/assets/index--OvfbQj5.css.

## Task 5

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Stale assets index-CEkAVloK.css, index-CLuS4yuS.js, index-Ct0hUlIi.css, and index-C6wl6AwB.js absent from output directory.

## Task 6

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Generated JS contains filter strings, Prompt Details strings, and missing-payload strings.
- Generated CSS contains filter selectors, Prompt Details selectors, and card selectors.

## Task 7

### Decisions made
- Coordinator owns daemon restart and browser verification.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Backend: uv run pytest -q passed (402 passed, 3 deselected in 19.76s).
- Frontend: npm --prefix web test -- --poolOptions.threads.maxThreads=2 passed (18 files, 196 passed in 20.39s).
- git diff --check passed with zero errors.

## Task 8

### Decisions made
- Browser verification used the restarted daemon and requested real deep link.
- Command disclosure was not fabricated without a normalized Command event.

### Spec deviations
- The selected historical job contains no normalized Command event.

### Tradeoffs accepted
- Browser Command rendering is supported by component tests, not live route data.

### Assumptions
- The `/favicon.ico` 404 is unrelated baseline browser noise.

### Follow-ups for human
- none

### Test evidence
- Desktop route loaded current generated assets successfully.
- Narrow verification used a 390 by 844 viewport.
- Defaults, role filtering, cross-group empty state, Reset filters, Thinking opt-in,
  native Tool disclosures, missing-payload copy, and follow-live pause passed.
- Captured raw tool input and output rendered as inert disclosure text.
- Security-exclusion terms were absent from rendered transcript content.

## Task 9

### Decisions made
- Coordinator retained Git staging, commit, and review ownership.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Fresh coordinator build produced the same generated asset names.
- Fresh backend suite passed 402 tests with 3 deselected.
- Fresh frontend suite passed 196 tests across 18 files.
- Protected source hashes remained unchanged.
