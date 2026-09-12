<!-- ccg-shared-version: 10.6.0 -->

# Phase 3 — Decision Notes

## Task 1

### Decisions made
- Built production static assets using Vite (`npm --prefix web run build`) targeting `src/openmcp/dashboard_static`.
- Replaced previous hashed assets (`index-B6uytRJM.js`, `index-BF-D9UdR.css`) with clean builds (`index-C6wl6AwB.js`, `index-Ct0hUlIi.css`) via `emptyOutDir: true`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Verification gate: `npm --prefix web test` passed (176 tests across 18 test files) prior to packaging build.
- Root cause (bugfix only): n/a

## Task 2

### Decisions made
- Validated generated asset references in `index.html` via Python script to ensure all referenced files exist on disk and no dangling references exist.
- Produced clean independent verification build in `/tmp/openmcp-dashboard-build` and confirmed exact deterministic parity via `diff -qr`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Verification gate: `npm --prefix web test` passed (176 tests) after one timing-sensitive rerun. The preceding run failed two unrelated dirty-draft tests.
- `uv run pytest -q` passed (390 passed, 3 deselected).
- `git diff --check` passed cleanly.
- `diff -qr /tmp/openmcp-dashboard-build src/openmcp/dashboard_static` confirmed exact parity.
- Referenced asset checks confirmed all bundles exist.
- Root cause (bugfix only): n/a

## Task 3

### Decisions made
- Executed Playwright verification against `http://127.0.0.1:8765/dashboard/projects/ad9a3a2d-4583-4ac7-a954-ba21c7162055/jobs/a41dab52-ca27-4139-b982-f990eaab4de8`.
- Verified chronological assistant and tool ordering, readable typography, collapsed tool rows, pointer disclosure, native Enter disclosure, and status presentation.
- Verified expanded rows remeasure without overlap.
- Verified upward wheel navigation pauses following.
- Verified Jump to live restores following.
- Verified desktop at 1440x900 and narrow layout at 375x667.
- Verified transcript content remains horizontally contained.
- The historical route exposes unavailable payload placeholders because its details predate Phase 1 persistence.
- Browser console output contained only the unrelated `favicon.ico` 404.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Historical jobs prior to Phase 1 show "Input not available" and "Output not available" placeholders as designed.

### Follow-ups for human
- none

### Test evidence
- Playwright passed transcript checks at desktop and narrow viewport dimensions.
- Mounted transcript rows had zero measured overlaps after pointer and keyboard expansion.
- The transcript panel stayed within the narrow viewport.
- Existing document-level overflow came from the tab strip, not transcript content.
- Root cause (bugfix only): n/a
