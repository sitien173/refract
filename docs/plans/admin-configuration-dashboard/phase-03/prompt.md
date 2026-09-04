## Original User Request
Complete the OpenMCP admin configuration dashboard. Implement the React and FlowForge product-shell foundation through the existing Starlette daemon.

## Phase
Build the React and FlowForge foundation.

## Tasks
- task-1: Scaffold React, Vite, and frontend tests.
- task-2: Apply FlowForge tokens, typography, logo, and product shell.
- task-3: Add client routing and the dashboard API boundary.
- task-4: Serve and package stable production assets.

## Context
Phase 2 added `/dashboard/api` routes before the final root MCP mount. Add a Vite React SPA beneath `/dashboard/` without intercepting those APIs or `/mcp`. Current Vite documentation confirms `base: "/dashboard/"` prefixes built HTML assets correctly. Development uses Vite only. Production serves generated files from the Python package.

FlowForge sources:
- `/home/ngosi/.claude/skills/flowforge-design/colors_and_type.css`
- `/home/ngosi/.claude/skills/flowforge-design/fonts/LibreFranklin[wght].woff2`
- `/home/ngosi/.claude/skills/flowforge-design/fonts/LibreFranklin-Italic[wght].woff2`
- `/home/ngosi/.claude/skills/flowforge-design/assets/flowforge-logo.png`
- `/home/ngosi/.claude/skills/flowforge-design/ui_kits/product/`
- `/home/ngosi/.claude/skills/flowforge-design/ui_kits/account/`
Copy approved assets into frontend source. Import `colors_and_type.css` before custom styles. Use tokens, not raw brand colors.

## Files
- `.gitignore`
- `web/package.json`
- `web/package-lock.json`
- `web/vite.config.js`
- `web/index.html`
- `web/src/main.jsx`
- `web/src/App.jsx`
- `web/src/api.js`
- `web/src/components/AppShell.jsx`
- `web/src/components/Sidebar.jsx`
- `web/src/components/Topbar.jsx`
- `web/src/components/StatusBadge.jsx`
- `web/src/components/Alert.jsx`
- `web/src/styles/colors_and_type.css`
- `web/src/styles/app.css`
- `web/src/styles/fonts/LibreFranklin[wght].woff2`
- `web/src/styles/fonts/LibreFranklin-Italic[wght].woff2`
- `web/src/assets/flowforge-logo.png`
- `web/src/App.test.jsx`
- `web/src/test/setup.js`
- `src/openmcp/dashboard.py`
- `src/openmcp/dashboard_static/index.html`
- `src/openmcp/dashboard_static/assets/`
- `pyproject.toml`
- `tests/test_dashboard.py`
- `tests/test_smoke.py`

## Done When
- `/dashboard/` serves the React application.
- Direct dashboard routes return the SPA entry point.
- Dashboard API requests never receive the SPA fallback.
- `/mcp` behavior remains unchanged.
- The UI uses FlowForge CSS variables instead of raw brand colors.
- The shell uses a 200px sidebar and 64px top bar.
- Libre Franklin and the FlowForge logo load locally.
- Keyboard focus uses the FlowForge interaction-blue ring.
- No gradients, decorative blobs, emoji, or filled icon set appear.
- Green stays limited to actions, selection, and success. Blue stays limited to interaction and focus.
- Production assets are reproducible through `npm run build`.
- Every generated asset is included in the built wheel.
- `npm --prefix web ci`
- `npm --prefix web run test`
- `npm --prefix web run build`
- `uv run pytest tests/test_dashboard.py tests/test_smoke.py`
- `uv build`
- `python -c "import glob,zipfile; p=glob.glob('dist/openmcp-*.whl')[-1]; n=zipfile.ZipFile(p).namelist(); assert any(x.endswith('dashboard_static/index.html') for x in n); assert any('/dashboard_static/assets/' in x for x in n)"`
- `git diff --check`

## Consultation Findings
- Configure shared Hatch `artifacts = ["src/openmcp/dashboard_static/**"]` so plain `uv build` carries assets through the source distribution into the wheel.
- A missing frontend build must never break `create_application()` or `/mcp`. Register static routes conditionally and return a dashboard-specific 503 when assets are absent.
- Add an explicit `/dashboard/api/{path:path}` JSON 404 guard before SPA routes.
- Route order is API routes, API 404, static assets, `/dashboard`, dashboard deep-link fallback, then root MCP mount.
- Missing static assets return 404, never SPA HTML. Serve the SPA index with `Cache-Control: no-store`.
- Set Vite `base: "/dashboard/"`, an external `outDir`, `emptyOutDir: true`, and explicit asset naming patterns.
- Copy static Libre Franklin fallback files too, or remove their CSS URLs. Do not ship unresolved font requests.
- Use `vitest run` with jsdom and setup files. Tests must not enter watch mode.
- Cache the CSRF bootstrap token. On a forbidden mutation, re-bootstrap and retry exactly once.
- Do not add credentials or CORS behavior to fetch requests.
- Use `var(--layout-sidebar-width)` and `var(--space-4xl)` for shell dimensions. Do not override the supplied focus outline.
- Add Python coverage for SPA, missing assets, API typo JSON, missing static files, index caching, and unchanged MCP routing.
- Add frontend coverage for shell dimensions, CSRF headers and single retry, status semantics, and absence of raw colors or gradients.

## Additional Allowed Files
- `web/src/styles/fonts/LibreFranklin-Regular.woff2`
- `web/src/styles/fonts/LibreFranklin-Italic.woff2`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`. Keep one production Starlette process. Do not add
CORS. Keep SPA fallbacks beneath `/dashboard/`. Match FlowForge exactly.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
