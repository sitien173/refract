# Phase 1 — Decision Notes

## Task 1
### Decisions made
- Scaffolded web app using React 19, TypeScript, React Router 7, TanStack React Query, Vite 6, and Vitest.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- Node.js and npm versions on host support ES2022 and React 19 JSX runtime.
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: Initial scaffolding `npm --prefix web install` completed cleanly adding 168 packages.

## Task 2
### Decisions made
- Configured Vite with `base: '/dashboard/assets/'`, `outDir: '../src/openmcp/dashboard_static'`, `emptyOutDir: true`, and development server proxy for `/dashboard/api` to `http://127.0.0.1:8765`.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- `import.meta.url` path resolution guarantees relative location independent of current working directory.
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: `npm --prefix web run build` outputs index.html and assets/ directly into `src/openmcp/dashboard_static/`.

## Task 3
### Decisions made
- Vendored Flowforge design tokens in `colors_and_type.css` with updated relative font paths (`../fonts/`), Libre Franklin woff2 fonts, OFL license, and Lucide SVG icons with ISC license.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- All runtime assets are strictly local with zero external CDN dependencies.
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: `! tgrep 'unpkg|fonts\.googleapis|fonts\.gstatic|url\([^)]*https?://' web/src src/openmcp/dashboard_static -n` returned zero matches.

## Task 4
### Decisions made
- Built `AppShell`, `Sidebar` (200px width), `TopBar` (64px height), and `ThemeToggle` (`data-theme` attribute + `localStorage` persistence).
- Embedded inline theme script in `index.html` head to prevent light theme flash before React mount.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- CSS module styling handles narrow-screen adaptation cleanly without JS state overhead.
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: Vitest tests in `web/src/App.test.tsx` verified sidebar navigation links and theme toggle functionality.

## Task 5
### Decisions made
- Updated `tests/test_dashboard.py` to test the Vite asset structure (`/dashboard/assets/assets/*`) instead of legacy Alpine files.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- `dashboard_static/assets/*.js` matches Vite production build output.
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: `uv run pytest tests/test_dashboard.py -k 'dashboard_static'` passed 2/2 tests (and 27/27 total dashboard tests).

## Task 6
### Decisions made
- Generated production build into `src/openmcp/dashboard_static/` and confirmed complete removal of legacy Alpine dashboard assets.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- Production asset files are committed to repository output directory.
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: Verification checks for file existence, asset pathing, no external network calls, clean pytest runs, and unchanged Python backend passed.
