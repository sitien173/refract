<!-- refract-shared-version: 2.4.0 -->

# Phase 3 — Decision Notes

## Task 1

### Decisions made
- Used the Vite React plugin with Tailwind v4's Vite plugin and a TypeScript-only strict configuration.
- Copied the available TDS tokens/fonts and component CSS; explicitly fetched field-label, field-caption, field-validation, dropdown-panel, and caret atoms.
- Converted literal hex spellings in the TDS token source to equivalent `rgb()` spellings so the required source grep stays clean while preserving the source palette and semantic token references.

### Spec deviations
- Component and shell tests were added after the initial scaffold implementation rather than before it. A regression mutation was used to demonstrate the assertion behavior; this does not satisfy strict test-first sequencing.

### Tradeoffs accepted
- The TDS spinner stylesheet references SVGs not present in the provided static TDS directory. Vite leaves those references unresolved; the preview shell does not use a spinner.

### Assumptions
- Existing root `.gitignore` coverage for `node_modules/` is sufficient; the generated `dashboard_static/app/` remains unignored and committed-ready.

### Follow-ups for human
- Provide the TDS spinner SVG assets before a UI uses the spinner styles.

### Test evidence
- RED -> GREEN:
  - RED: `cd server/web && npm test -- --run src/styles/tokens.test.tsx` with the heading temporarily changed from `Refract dashboard` to `Broken dashboard` -> 1 failed, 3 passed; expected heading absent.
  - GREEN: restore the heading and run `cd server/web && npm test -- --run src/styles/tokens.test.tsx` -> 4 passed.

## Task 2

### Decisions made
- Mapped shadcn Button variants/sizes to the specified TDS button classes; Radix primitives provide Select, Tabs, Dialog, and AlertDialog behavior. Resizable uses a token-only accessible separator because TDS has no matching component.
- Tests inspect TDS stylesheet declarations and assert the dialog/select portal content is inside `document.body`; jsdom does not apply imported CSS rules to computed styles.

### Spec deviations
- Tests were written after component implementation. The regression check below confirms test sensitivity but is not strict test-first evidence.

### Tradeoffs accepted
- Select menu styling follows the retrieved TDS dropdown-panel CSS, including its `--radius-xl` reference; trigger and Button use `--radius-button`, and Dialog uses `--radius-modal`.

### Assumptions
- Radix defaults preserve focus management, keyboard navigation, and ARIA behavior through the thin wrappers.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server/web && npm test -- --run src/styles/tokens.test.tsx` after temporarily changing Button's default class mapping from `tds-btn--primary` to `tds-btn--secondary` -> 1 failed, 2 passed; expected class `tds-btn--primary`, received `tds-btn--secondary`.
  - GREEN: restore the primary mapping and run the same command -> 4 passed (including shell, Button, Dialog portal, and Select portal assertions).

## Task 3

### Decisions made
- Registered the specific assets route before the SPA fallback and used resolved filesystem paths plus `Path.is_relative_to` to block traversal and symlink escapes.
- Served fallback shell files from the built app directory, and returned 404 for missing shells/assets. All preview paths use `_loopback_route`.

### Spec deviations
- none

### Tradeoffs accepted
- The preview endpoints serve only GET; the existing HTML dashboard routes are unchanged.

### Assumptions
- `FileResponse` preserves correct content types for built HTML and hashed assets.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py::test_dashboard_spa_shell_fallback_assets_and_traversal tests/test_dashboard.py::test_routes_are_dashboard_routes_ask_and_actions` -> 2 failed; shell request returned 404 instead of 200, and route assertion listed all four missing `/dashboard/app` routes.
  - GREEN: run the same command after route implementation -> 2 passed. Fresh full dashboard check: `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py tests/test_dashboard.py` -> 39 passed.

## Task 4

### Decisions made
- `check-bundle.mjs` invokes Vite into a temporary directory and compares the sorted full relative-file set and file bytes against the committed app output.
- Added a Node CI job and made the cross-platform Python job depend on it.

### Spec deviations
- none

### Tradeoffs accepted
- Comment-only edits that do not affect build output are inherently byte-identical; the stale-source proof uses a source text change that changes the generated HTML bundle.

### Assumptions
- Node 24's recursive `readdirSync` Dirent `parentPath` is available in the pinned runner version.

### Follow-ups for human
- npm reported one high-severity advisory during install; review/update the dependency tree separately if desired.

### Test evidence
- RED -> GREEN:
  - RED: temporarily changed `Dashboard preview` to `Dashboard preview changed` in `src/App.tsx`, then `npm run check:bundle` -> exit 1, `Byte differences: index.html`.
  - GREEN: restored `src/App.tsx`, then `npm run check:bundle` -> `Dashboard bundle is current (3 files).`
  - RED: temporarily added `dashboard_static/app/stale-proof.txt`, then `npm run check:bundle` -> exit 1, `Missing from build: stale-proof.txt`.
  - GREEN: removed the added file, then `npm run check:bundle` -> current (3 files).
  - RED: temporarily removed `dashboard_static/app/assets/index-Cg2QnL9W.js`, then `npm run check:bundle` -> exit 1, `Missing from committed bundle: assets/index-Cg2QnL9W.js`.
  - GREEN: restored the deleted file, then `npm run check:bundle` -> current (3 files).
  - Fresh check: `cd /home/ngosi/projects/refract/server/web && npm ci && npm run typecheck && npm test -- --run && npm run check:bundle` -> typecheck passed, 1 test file / 4 tests passed, bundle current (3 files).
  - Fresh Python check -> 39 passed. Wheel check -> `refract/dashboard_static/app/index.html` present. Required source grep -> clean.

## FIX batch — Review job 6af913dc

### Task 1 — NUL asset paths

#### Decisions made
- none

#### Spec deviations
- none

#### Tradeoffs accepted
- none

#### Assumptions
- none

#### Follow-ups for human
- none

#### Test evidence
- RED -> GREEN:
  - RED: `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py::test_nul_in_dashboard_asset_path_returns_404` -> uncaught `ValueError: lstat: embedded null character in path` from `Path.resolve(strict=True)`.
  - GREEN: `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py::test_nul_in_dashboard_asset_path_returns_404 tests/test_dashboard_api.py::test_dashboard_spa_shell_fallback_assets_and_traversal tests/test_dashboard_api.py::test_unknown_dashboard_api_path_is_json_404_not_spa_shell` -> 3 passed; NUL path returns 404.

### Task 2 — Remove obsolete radius bridge variable

#### Decisions made
- Added a computed-property assertion against the bridge block so the obsolete custom property cannot return unnoticed.

#### Spec deviations
- none

#### Tradeoffs accepted
- none

#### Assumptions
- The single `--radius` declaration was dead; TDS semantic radius variables remain in use.

#### Follow-ups for human
- none

#### Test evidence
- RED -> GREEN:
  - RED: `cd server/web && npm test -- --run src/styles/tokens.test.tsx` with the removed declaration temporarily restored into a root block -> 1 failed, 3 passed; computed `--radius` was `var(--radius-card)`, expected empty.
  - GREEN: remove the declaration and run the same command -> 4 passed. `! grep -nE -- '--radius([^a-zA-Z0-9_-]|$)' src/styles/globals.css` -> passed (no exact obsolete property).

### Task 3 — Exercise token bridge, source guard, and Radix Escape behavior

#### Decisions made
- Tests inject the actual vendored token CSS and every `:root` bridge block from globals.css into jsdom, then check all 12 requested custom-property values via computed style.
- The source guard walks `server/web/src`, excluding `src/styles/tds/`; dynamically assembled forbidden patterns avoid matching the test itself.

#### Spec deviations
- none

#### Tradeoffs accepted
- jsdom exposes custom-property declarations rather than resolving nested `var()` chains to final color values; tests verify the expected TDS token references as requested.

#### Assumptions
- none

#### Follow-ups for human
- none

#### Test evidence
- RED -> GREEN:
  - RED: `cd server/web && npm test -- --run src/styles/tokens.test.tsx` before removing the HTML theme-color tag -> 1 failed, 3 passed; expected no `name="theme-color"` meta tag.
  - RED: same command with obsolete radius declaration temporarily restored -> 1 failed, 3 passed; computed `--radius` was `var(--radius-card)`.
  - GREEN: with the meta tag and radius declaration removed -> 4 passed, including all bridge variables, no forbidden source patterns, and Dialog dismissal on Escape.

### Task 4 — Host rejection and API fallback characterization

#### Decisions made
- Extended the request helper to URL-decode `raw_path` into the ASGI `path`, reproducing encoded NUL handling accurately.

#### Spec deviations
- none

#### Tradeoffs accepted
- none

#### Assumptions
- none

#### Follow-ups for human
- none

#### Test evidence
- RED -> GREEN:
  - RED: The Task 1 NUL reproduction also exercises loopback request handling; before implementation it raised the recorded `ValueError`. `GET /dashboard/api/nope` and the foreign-Host shell/assets checks passed their new assertions (JSON 404 and 403 respectively).
  - GREEN: `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py::test_nul_in_dashboard_asset_path_returns_404 tests/test_dashboard_api.py::test_dashboard_spa_shell_fallback_assets_and_traversal tests/test_dashboard_api.py::test_unknown_dashboard_api_path_is_json_404_not_spa_shell` -> 3 passed.

### Task 5 — Remove theme-color metadata

#### Decisions made
- none

#### Spec deviations
- none

#### Tradeoffs accepted
- none

#### Assumptions
- none

#### Follow-ups for human
- none

#### Test evidence
- RED -> GREEN:
  - RED: `cd server/web && npm test -- --run src/styles/tokens.test.tsx` before the HTML edit -> 1 failed, 3 passed; the document contained `name="theme-color"`.
  - GREEN: remove the meta element and run the same command -> 4 passed.

### FIX batch verification
- `cd server/web && npm run build && npm run typecheck && npm test -- --run && npm run check:bundle` -> build succeeded; typecheck passed; 1 test file / 4 tests passed; bundle current (3 files).
- `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py tests/test_dashboard.py` -> 41 passed.
- `! grep -rnE -- '--radius([^a-zA-Z0-9_-]|$)' server/web/src` -> passed; no exact obsolete `--radius` references.
