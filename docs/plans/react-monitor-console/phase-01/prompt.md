## Original User Request

Execute the `react-monitor-console` folder plan. Complete only Phase 1.

## Phase

Deliver the React 19, Vite, TypeScript Flowforge application shell.

## Tasks

- task-1: Scaffold `web/` with the planned runtime and development dependencies.
- task-2: Configure production output and the development API proxy.
- task-3: Vendor Flowforge tokens, Libre Franklin fonts, and used Lucide SVGs.
- task-4: Build the responsive shell and persistent light/dark theme toggle.
- task-5: Generate the committed production dashboard build.

## Context

The existing FastMCP route serves `src/openmcp/dashboard_static/index.html`.
Its assets mount maps `/dashboard/assets/<path>` to
`src/openmcp/dashboard_static/<path>`. Use Vite base
`/dashboard/assets/`, output directory `../src/openmcp/dashboard_static`, and
`emptyOutDir: true`. Proxy `/dashboard/api` only during development.

Current Vite documentation confirms React TypeScript uses
`@vitejs/plugin-react`. It also confirms `emptyOutDir` is required when forcing
cleanup outside Vite's root.

Flowforge sources:

- `/home/ngosi/.codex/skills/flowforge-design/colors_and_type.css`
- `/home/ngosi/.codex/skills/flowforge-design/fonts/`
- `/home/ngosi/.codex/skills/flowforge-design/ui_kits/product/`

Use Flowforge tokens, not raw palette values. Keep all runtime assets local.
Use only needed Lucide stroke SVGs. No CDN references.

## Files

- `web/package.json`
- `web/package-lock.json`
- `web/tsconfig.json`
- `web/vite.config.ts`
- `web/index.html`
- `web/src/main.tsx`
- `web/src/App.tsx`
- `web/src/styles/colors_and_type.css`
- `web/src/styles/app.module.css`
- `web/src/fonts/*.woff2`
- `web/src/assets/icons/*.svg`
- `web/src/components/AppShell.tsx`
- `web/src/components/Sidebar.tsx`
- `web/src/components/TopBar.tsx`
- `web/src/components/ThemeToggle.tsx`
- `src/openmcp/dashboard_static/`
- `docs/plans/react-monitor-console/phase-01/notes.md`
- `docs/plans/react-monitor-console/phase-01/journal.md`

## Done When

- The shell uses a 200px sidebar and 64px top bar.
- The theme toggle sets `data-theme` and persists in `localStorage`.
- Fonts, icons, scripts, and styles load without external network requests.
- Generated asset URLs use `/dashboard/assets/`.
- Prior Alpine dashboard files are absent after the build.
- Backend Python files remain unchanged.
- `npm --prefix web install`
- `npm --prefix web run build`
- `test -f src/openmcp/dashboard_static/index.html`
- `test -d src/openmcp/dashboard_static/assets`
- `test ! -e src/openmcp/dashboard_static/app.js`
- `test ! -e src/openmcp/dashboard_static/styles.css`
- `test ! -e src/openmcp/dashboard_static/vendor/alpine.min.js`
- `! tgrep 'https?://|//unpkg|fonts.googleapis' web/src src/openmcp/dashboard_static -n`
- `git diff --exit-code -- 'src/openmcp/*.py'`

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
