<!-- refract-shared-version: 2.4.0 -->

# Phase 5 — Decision Notes

## Task 1

### Decisions made
- Register `/dashboard/assets` explicitly as an asset request so even the bare asset prefix returns 404 instead of the SPA shell.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- `/dashboard/{path}` is the shell fallback only after API and asset routes have been registered.

### Follow-ups for human
- Coordinator performs manual browser acceptance and records the TDS Rule 10 checklist.

### Test evidence
- RED -> GREEN:
  - RED: `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard.py tests/test_dashboard_api.py` -> 4 failures exposed old route table, legacy preview routing, 503 deep links, and unmatched new asset paths (29 passed).
  - GREEN: same command -> 33 passed.
  - Additional RED: `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard.py::test_dashboard_assets_are_not_shell_fallback` -> expected 404 for `/dashboard/assets`, received shell 200.
  - Additional GREEN: `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard.py tests/test_dashboard_api.py` -> 33 passed after registering the exact asset-prefix route.
- Root cause (bugfix only): The catch-all shell route previously had no special asset-prefix route and swallowed `/dashboard/assets`.

## Task 1b

### Decisions made
- Retained `_api_json_response`/`_api_error` separately from `_json_response`/`_error`: API errors have distinct default `unchanged` text and API responses guarantee `Cache-Control: no-store`; folding them would require per-call defaults and risk changing `/ask` response shapes.
- Set Vitest `maxWorkers: 2` to cap resource usage and reduce load-dependent test timing variance.

### Spec deviations
- none

### Tradeoffs accepted
- The two JSON helper pairs remain intentionally distinct to preserve their different response contracts.

### Assumptions
- Hashed filenames are served by the generated `assets/` tree and can use immutable caching.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: initial shell/asset verification in `tests/test_dashboard_api.py` failed before reaching headers because preview URLs did not resolve (503 at the new shell path); the dedicated asset-prefix RED above caught the 200 fallback.
  - GREEN: `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard.py tests/test_dashboard_api.py` -> 33 passed, including no-cache shell, immutable asset cache, and nosniff assertions.
  - GREEN: `cd server/web && npm ci && npm run typecheck && npm test -- --run` -> typecheck passed; 17 files and 83 tests passed. `vite.config.ts` sets `maxWorkers: 2`.
- Root cause (bugfix only): none

## Task 2

### Decisions made
- Documented route families in the Unreleased entry, including all newly introduced JSON/action/asset routes and the removed HTML output route; named the SPA-served pages.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing Unreleased history for older removed API routes remains relevant and was retained.

### Follow-ups for human
- Coordinator to append manual acceptance observations and TDS Rule 10 results; manual browser acceptance was out of worker scope.

### Test evidence
- RED -> GREEN:
  - RED: `git show HEAD:README.md | grep -q '^## Dashboard$'` -> no dashboard section existed at phase base; Unreleased changelog lacked the required new route list.
  - GREEN: `rg -n 'GET /dashboard/api/jobs|GET /dashboard/api/targets|POST /dashboard/api/jobs|GET /dashboard/assets|GET /dashboard/jobs/\{job_id\}/output|server-rendered HTML pages' CHANGELOG.md` -> confirms required added and removed routes are documented; README now contains dashboard routes, behavior, actions, and rebuild commands.
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Rebuilt the committed Vite output after changing `base` to `/dashboard/`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- No manual browser acceptance is performed by the implementer, per phase role boundary.

### Follow-ups for human
- Coordinator must complete manual browser acceptance and TDS Rule 10 checklist.

### Test evidence
- RED -> GREEN:
  - RED: not applicable; rebuilding generated artifacts is not a behavioral change.
  - GREEN: `cd server/web && npm run build && npm run check:bundle` -> build succeeded; bundle check reports current (3 files).
  - Final frontend verification: `cd server/web && npm run typecheck && npm test -- --run && npm run check:bundle` -> typecheck passed; 17 files, 83 tests passed; bundle current (3 files).
  - Final backend verification: `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider` -> 798 passed, 15 deselected. One earlier run had an unrelated concurrent SQLite WAL race (`test_probe_claim_is_atomic_and_failure_cooldown_caps`); clean rerun passed.
  - Wheel and source checks: wheel built with `dashboard_static/app/index.html` and no `dashboard_static/tds/`; source greps found no `_POLL_SCRIPT`, `_stylesheet`, `dashboard_static/tds`, or `dashboard/app` references.
- Root cause (bugfix only): none

## Coordinator acceptance

Environment: isolated `refract serve --port 8799` with `REFRACT_HOME=/tmp/refract-accept`, built from checkpoint `1b0805e4`. Browser: Brave attached via `playwright-cli --extension=brave`. The live daemon on 8765 was not touched.

### Observed results
- `/dashboard` renders the console. PASS.
- Deep link `/dashboard/jobs/{id}` opens the job detail. PASS.
- `/dashboard/targets` renders configuration status and per-target backend, model, and health as labeled content, not raw JSON. PASS.
- Action states: failed job shows Cancel disabled and Retry enabled; running job shows Cancel and Answer enabled and Retry disabled. PASS.
- Retry via UI on `dff318c4` created `8effdcc7`, navigated to it, and announced "Retry started". PASS.
- Answer via UI on `eb654e59`: dialog operated by keyboard only with focus, Enter, Escape, and reopen; typed draft survived polling; submit announced "Answer sent"; job reached `succeeded`. PASS.
- Cancel via UI on `b91f8b0e`: AlertDialog opened with initial focus on "Keep job"; "Confirm cancellation" closed the dialog, announced "Cancellation requested", and the API reported `cancelled`. PASS.
- Transcript: 16 output events rendered as 2 grouped items, a completed Bash tool row and an Assistant message. PASS.
- Live updates within 2 s: PASS. Second session with the Brave tab visible, `document.hidden` false, on job `b6a84310` making one shell call every ~7 s. An in-page probe polled the output API every 200 ms and watched the transcript text every 50 ms. 6 new events rendered with lags of 779, 314, 957, 761, 699, and 148 ms. Maximum 957 ms.
- Keyboard navigation of the job list: PASS. With focus on a list item, Tab moved to the next job button; Enter opened `/dashboard/jobs/dd9ce588-...`, rendered its detail, and set `aria-current` on that item.
- Keyboard resize of the split pane: PASS. The separator is focusable with `tabindex=0`; ArrowLeft changed `aria-valuenow` from 35 to 20.
- Keyboard navigation of tabs: NOT APPLICABLE. No view renders `components/ui/tabs.tsx`.
- First-session note: Brave was occluded for the cancel check, so Playwright pointer clicks timed out; that flow was driven through DOM `click()`. Keyboard focus in the dialog was checked as observed above.
- Not a defect: a deep link showing "Loading job…" indefinitely was traced to `document.hidden` being true. Polling resumes when the tab becomes visible.

### TDS Rule 10 self-check
- Page background uses `--surface-neutral-01` or `--surface-neutral-02`: PASS. Computed body background `rgb(244, 246, 244)` equals `--surface-neutral-02` `#f4f6f4`.
- Zero hardcoded hex colors: PASS. No hex in `server/web/src` outside vendored `src/styles/tds/` and tests.
- All component classes use `tds-` prefix: PASS. All console buttons carry `tds-btn` classes; select triggers carry `tds-select__trigger tds-select__trigger--md`.
- All backgrounds use `--surface-*` tokens: PASS. shadcn bridge maps `--background` to `--surface-neutral-01` in `src/styles/globals.css`.
- All text colors use `--text-*` tokens: PASS. Bridge maps foreground variables to `--text-*`; no hex in source.
- Buttons use `tds-btn tds-btn--{size} tds-btn--{variant}`: PASS.
- Buttons have `var(--interactive-default)` background via component CSS: PASS. `--primary` maps to `--interactive-default` `#004c45`.
- Form fields have `tds-field-label` labels: PASS. 5 labels for 5 filter and search fields.
- Token definitions are included: PASS. Loaded from `src/styles/tds/` before the bridge; SPA equivalent of the `<style>` block.
- Component CSS is included: PASS. Fetched TDS component CSS lives under `src/styles/tds/`.
- No `.dark` or `@custom-variant dark` in source: PASS.
