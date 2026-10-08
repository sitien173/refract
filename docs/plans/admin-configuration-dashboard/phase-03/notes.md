<!-- ccg-shared-version: 10.2.0 -->

# Phase 3 — Decision Notes

## Task 1

### Decisions made
- Reconciled the existing React package metadata and added Vite, Vitest, jsdom, and Testing Library configuration.
- Production builds use an explicit hashed asset naming policy and an external Python-package output directory.

### Spec deviations
- none

### Tradeoffs accepted
- The foundation uses lightweight client-side history routing rather than adding a router dependency.

### Assumptions
- The existing locked npm dependency graph is authoritative.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Initial frontend test collection failed because `web/src/App.jsx` was absent; after scaffolding, `npm --prefix web run test` passed.

## Task 2

### Decisions made
- Copied the approved FlowForge token stylesheet, Libre Franklin variable/fallback fonts, and logo into frontend source assets.
- Built a semantic product shell with token-based 200px sidebar and 64px top bar dimensions.

### Spec deviations
- none

### Tradeoffs accepted
- Foundation screens use CSS-built line markers instead of adding an icon package or filled icon set.

### Assumptions
- The supplied FlowForge token stylesheet is the source of truth for all brand colors and focus behavior.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Shell rendering coverage passed in Vitest; production CSS imports FlowForge tokens before custom styles and contains no raw application brand colors or gradients.

## Task 3

### Decisions made
- Added a small API boundary that parses stable JSON errors and keeps CSRF state private to the module.
- Mutating requests bootstrap a token and retry exactly once after a 403; no credentials or CORS options are added.

### Spec deviations
- none

### Tradeoffs accepted
- Initial screens are deliberately read-only; later phases can add views against the established API boundary.

### Assumptions
- Browser same-origin behavior supplies the Origin header without client-side CORS configuration.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Frontend test suite passed with 1 test; API client build and module transformation completed successfully.

## Task 4

### Decisions made
- Static dashboard routes are registered before the root MCP mount, with an explicit API typo guard ahead of SPA fallback routes.
- Missing frontend builds fail only dashboard index requests with a dashboard-specific 503; missing static assets return 404.
- SPA index responses are `no-store`, while Vite output is copied into the package and included through Hatch sdist/wheel artifacts.

### Spec deviations
- none

### Tradeoffs accepted
- Static asset serving is conditional at application construction so `/mcp` remains available when frontend assets are absent.

### Assumptions
- The frontend is built before packaging; generated `src/openmcp/dashboard_static` files are package artifacts rather than source modules.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Python static/API fallback coverage passed with 64 tests, full pytest passed with 310 passed and 3 deselected, `npm ci --offline`, Vitest, Vite build, `uv build`, wheel asset assertions, `tgrep`, and `git diff --check` passed.

## Review Fix — Frontend coverage gap

### Decisions made
- Expanded `App.test.jsx` with focused assertions for FlowForge token dimensions, marker-plus-label status semantics, raw-color/gradient absence, and CSRF bootstrap retry behavior.

### Spec deviations
- none

### Tradeoffs accepted
- CSS source assertions read the checked-in token and application styles directly so the tests verify design-system usage rather than browser layout implementation details.

### Assumptions
- A two-request mutation retry after the initial bootstrap and forbidden response is exactly one retry, with no third mutation attempt.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: The new CSS coverage first failed because the Vite `?raw` import was empty and then because a transformed module URL was not a file URL; filesystem-backed style assertions resolved this, and Vitest passed with 5 tests including the exact CSRF retry assertions.

## Review Fix — Asset namespace fallback

### Decisions made
- Added an exact `/dashboard/assets` 404 route before the `/dashboard/{path:path}` SPA deep-link fallback.

### Spec deviations
- none

### Tradeoffs accepted
- The exact namespace returns a plain 404 response, matching missing individual assets and preventing accidental SPA HTML delivery.

### Assumptions
- `/dashboard/assets/` remains handled by the conditional static-assets route or missing-asset route.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Regression coverage now checks `/dashboard/assets` without a trailing path alongside missing files; affected Python dashboard/smoke tests passed with 64 tests and `git diff --check` passed.
