# Phase 5 — Decision Notes

## Task 1

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Vite production build output in `src/openmcp/dashboard_static/` is up-to-date and contains hashed assets and LibreFranklin font assets.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: N/A (Build asset audit)
- Root cause (bugfix only): N/A
- Build output verified: `src/openmcp/dashboard_static/` contains `index.html` (890 B) and `assets/` directory (`index-BLRnQJrJ.js`, `index-CYsfQ13X.css`, 4 `LibreFranklin*.woff2` font files).

## Task 2

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Legacy Alpine files (`app.js`, `styles.css`, `vendor/alpine.min.js`) and editor UI components are completely removed from production assets and React source.

### Follow-ups for human
- none

### Test evidence
- Audit output verified: No Alpine directives (`x-data`, `x-model`), legacy files, or config / task-guide editor UI references exist in `web/src` or `src/openmcp/dashboard_static`.

## Task 3

### Decisions made
- Baseline commit `a79b9308cad381323dff328fcc465eed8113cd73` confirmed for complete 5-phase Python immutability check.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing backend PUT routes (`/dashboard/api/config` and `/dashboard/api/task-guide`) in `src/openmcp/dashboard.py` remain intact for backward API compatibility but unreferenced by React frontend source.

### Follow-ups for human
- none

### Test evidence
- `git diff a79b9308cad381323dff328fcc465eed8113cd73 --stat -- 'src/openmcp/*.py'` returns clean empty output (0 backend Python lines changed).
- `git diff --stat -- 'src/openmcp/*.py'` returns clean empty output.
- `src/openmcp/dashboard.py` lines 163 and 214 verify `api_put_config` and `api_put_task_guide` routes remain present.

## Task 4

### Decisions made
- Recorded consultation job `10ae52fd-69db-47e3-ab0e-c94e7de3f488` (project `ad9a3a2d-4583-4ac7-a954-ba21c7162055`) as the verified durable job for live daemon verification.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Consultation job `10ae52fd-69db-47e3-ab0e-c94e7de3f488` is present in daemon database with complete event history.

### Follow-ups for human
- none

### Test evidence
- `GET /dashboard/api/projects/ad9a3a2d-4583-4ac7-a954-ba21c7162055/jobs` verified job `10ae52fd-69db-47e3-ab0e-c94e7de3f488` in list (HTTP 200).
- `GET /dashboard/api/jobs/10ae52fd-69db-47e3-ab0e-c94e7de3f488` returned workflow `consult`, state `succeeded` (HTTP 200).
- `GET /dashboard/api/jobs/10ae52fd-69db-47e3-ab0e-c94e7de3f488/events` returned full event sequence: `['job.queued', 'job.running', 'target.selected', 'target.attempt_finished', 'job.succeeded']` (HTTP 200).

## Task 5

### Decisions made
- Corrected light theme default when theme is unstored in both `web/index.html` head script and `web/src/components/ThemeToggle.tsx`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Theme initialization should be `'light'` when no stored value exists, regardless of OS `prefers-color-scheme`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - Added unit test suite `Theme management` in `web/src/App.test.tsx` testing unstored initialization under dark OS preference, stored light/dark restoration, bi-directional toggling, and persistence updates.
  - Initial test run produced RED state (`FAIL src/App.test.tsx > AppShell, Routing and ThemeToggle > Theme management > initializes to light theme when unstored even under dark OS preference` — expected `'dark'` to be `'light'`).
  - Modified `web/index.html` and `web/src/components/ThemeToggle.tsx` to default to `'light'` when unstored without checking OS `prefers-color-scheme`.
  - Re-ran tests, confirming GREEN state (149 passed across 16 test files in `npm --prefix web test -- --run`).

## Task 6

### Decisions made
- Verified packaging, offline asset isolation, theme persistence, and HTTP serving end-to-end after correcting theme initialization and rebuilding static assets.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Wheel distribution must contain only built static assets under `openmcp/dashboard_static/` without `web/` source code.

### Follow-ups for human
- none

### Test evidence
- `npm --prefix web test -- --run` passed (149 tests passed across 16 test files).
- `npm --prefix web run build` passed (production bundle built `index-bQ1rKa_Q.js`).
- `uv run pytest tests/test_dashboard.py` passed (27 tests passed).
- `uv build` passed (built `dist/openmcp-1.2.0-py3-none-any.whl`).
- Wheel inspection: contains `openmcp/dashboard_static/` assets (7 files) and 0 files under `web/`.
- HTTP 200 verified for `/dashboard`, `/dashboard/`, and all static asset URLs.
- `git diff --check`, `git status --porcelain src/openmcp`, and `git diff --stat -- 'src/openmcp/*.py'` verified (0 python files changed).
