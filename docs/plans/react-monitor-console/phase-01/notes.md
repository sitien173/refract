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
- Removed unused SVG icons (`alert-triangle.svg`, `check-circle.svg`, `x-circle.svg`) so every vendored icon is referenced in source.
- Cleaned trailing whitespace in `web/src/fonts/OFL.txt`.
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
- Removed React Router components (`BrowserRouter`, `NavLink`, `Routes`, `Route`) from `web/src` for Phase 1 static shell compliance; kept package installed for future phases.
- Rendered accessible static buttons in `Sidebar` with brand link pointing strictly to `/dashboard`.
- Applied Flowforge `--color-navigation-container` surface for selected nav state and `--color-surface` border token rules.
- Guarded `localStorage` reads and writes in `ThemeToggle` with `try/catch`.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- CSS module styling handles narrow-screen adaptation cleanly without JS state overhead.
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: `! tgrep 'BrowserRouter|NavLink|<Routes|<Route' web/src -n` returned zero matches. Vitest tests in `web/src/App.test.tsx` verified static buttons and guarded theme persistence.

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
- RED -> GREEN: Verification checks for file existence, asset pathing, no external network calls, clean pytest runs, no router components, zero whitespace errors, and unchanged Python backend passed.

## Task 7
### Decisions made
- Deleted `web/src/vite-env.d.ts` and added `"types": ["vite/client"]` to `web/tsconfig.json` to keep imports typed within allowed files.
- Converted dead `<button>` controls in `web/src/components/Sidebar.tsx` to noninteractive `<ul>`/`<li>` semantic list items with `aria-current="page"` for Overview.
- Removed custom letter-spacing tracking on `.brandBadge` and removed all `cursor: pointer` rules in `web/src/styles/app.module.css`.
- Rebuilt production assets into `src/openmcp/dashboard_static/` and updated `web/src/App.test.tsx` for list item structure.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- None.
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: `test ! -e web/src/vite-env.d.ts`, `! tgrep -F 'letter-spacing' web/src/styles/app.module.css -n`, `! tgrep -F 'cursor: pointer' web/src/styles/app.module.css -n`, `npm --prefix web test -- --run`, `npm --prefix web run build`, `uv run pytest tests/test_dashboard.py -k 'dashboard_static'`, and `git diff --check` all passed cleanly.

## Task 8
### Decisions made
- Replaced `<img>` SVG elements in `Sidebar.tsx` with `<span>` elements using CSS mask (`maskImage` / `WebkitMaskImage` / `--icon-url`) and `background-color: currentColor`.
- Guaranteed sidebar icons inherit text `currentColor` across both light and dark themes without adding new dependencies or modifying SVG path data.
- Added characterization test in `App.test.tsx` verifying sidebar icons render as CSS masks using the inheriting path.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- none
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: `npm --prefix web test -- --run`, `npm --prefix web run build`, `uv run pytest tests/test_dashboard.py -k 'dashboard_static'`, and `git diff --check` all passed cleanly.
