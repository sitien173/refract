<!-- refract-shared-version: 2.4.0 -->

# Phase 4 — Decision Notes

## Task 1

### Decisions made
- Executed `npm test` and `npm run build` in `server/web`.
- Confirmed fresh build regenerates `server/src/refract/dashboard_static`.
- Verified removal of stale base assets (`flowforge-logo-C2NBaI57.png`, `index-Dmt_vjdw.js`, `index-N_5a6zmM.css`, and old fonts).
- Verified build output reproducibility with identical SHA256 sums across subsequent builds.

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
  - RED: `cd server/web && ! ls ../src/refract/dashboard_static/assets | grep -E 'Dmt_vjdw|N_5a6zmM|flowforge'` -> exit code 1 (`index-Dmt_vjdw.js`, `index-N_5a6zmM.css`, `flowforge-logo-C2NBaI57.png` present)
  - GREEN: `cd server/web && ! ls ../src/refract/dashboard_static/assets | grep -E 'Dmt_vjdw|N_5a6zmM|flowforge'` -> exit code 0; `cd server/web && h() { find ../src/refract/dashboard_static -type f | sort | xargs sha256sum | sha256sum; } && npm run build >/dev/null && a=$(h) && npm run build >/dev/null && [ "$a" = "$(h)" ]` -> exit code 0; `cd server/web && npm test` -> 14 passed (14), 98 passed (98)
- Root cause (bugfix only): none

## Task 2

### Decisions made
- Rewrote `server/README.md` dashboard sections (`Admin Configuration Dashboard` and `Dashboard Management`) as read-only views: Live console (job feed, transcript, inspector), Projects, Targets and profiles, Diagnostics, Runtime, along with kept GET routes, polling intervals, and SSE streaming behavior.
- Documented that configuration changes go through `~/.refract/config.toml` and `.refract/config.toml`.
- Updated `README.md` mentions to reflect the read-only dashboard.
- Verified absence of forbidden dashboard editing, CSRF, and If-Match references in `server/README.md`.

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
  - RED: `! grep -nEi 'csrf|if-match|edit.*dashboard|dashboard.*edit' server/README.md` -> exit code 1 (matches on CSRF, If-Match, editable targets/profiles/overrides, and target editor inputs)
  - GREEN: `! grep -nEi 'csrf|if-match|edit.*dashboard|dashboard.*edit' server/README.md` -> exit code 0; `cd server && uv run --no-sync pytest -v tests/test_dashboard.py -k "test_readme_documents_dashboard_boundaries"` -> 1 passed
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Consulted coordinator via `refract ask` regarding heading style; used `## Unreleased - 2026-11-03` placed above `## 2.4.0 - 2026-10-29` without bumping package versions.
- Formatted breaking entry with leading `Breaking:` bullet describing the read-only console on React 19 and Vite.
- Enumerated all 19 removed routes by method and path against base commit `38f97c55`.
- Documented removal of CSRF and If-Match mechanisms and removal of the `tomlkit` dependency.

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
  - RED: Route diff audit -> 19 removed routes in `38f97c55` were missing from `CHANGELOG.md`
  - GREEN: All 19 removed routes listed with method and path in `CHANGELOG.md`; `cd server && uv run --no-sync pytest -q` -> 1201 passed, 23 skipped, 15 deselected; `git diff --check` -> exit code 0
- Root cause (bugfix only): none
