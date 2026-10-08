# OpenMCP Admin Configuration Dashboard Plan

Design: `docs/plans/admin-configuration-dashboard/DESIGN.md`

This plan adds a React dashboard to the existing Starlette daemon. The dashboard
uses FlowForge styling, exposes configuration observability, and permits only
loopback-protected context-instruction mutations.

### Phase 1: Track configuration health and revisions

**Task Guide Input:** Add authoritative OpenMCP configuration health and revision
tracking. Hash loaded global configuration content, record successful and failed
reload attempts, preserve the last-known-good catalog, and distinguish daemon
health from configuration validity. Persist the configuration revision used by
each newly submitted job while preserving immutable execution-plan behavior and
backward compatibility for existing jobs. Do not add configuration-file writes,
approvals, rollback, or daemon restart behavior.

**Goal:** Every configuration load and new job has observable revision identity.

**Files:**
- Modify: `src/openmcp/config.py`
- Create: `src/openmcp/config_inspection.py`
- Modify: `src/openmcp/models.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `src/openmcp/database.py`
- Modify: `tests/test_config.py`
- Create: `tests/test_config_inspection.py`
- Create: `tests/test_runtime.py`
- Modify: `tests/test_database.py`

**Tasks:**
1. Model configuration source revisions and health snapshots.
2. Track global load attempts and last-known-good state.
3. Stamp new jobs with their resolved configuration revision.
4. Migrate existing databases without changing old job behavior.

**Acceptance Criteria:**
- A stable SHA-256 content hash identifies each global configuration revision.
- Health reports attempted time, successful time, path, modification time,
  revision, validity, and the latest error.
- Failed reloads preserve the last-known-good catalog and health evidence.
- Configuration failure remains distinguishable from daemon availability.
- New jobs persist their configuration revision.
- Retries retain their original execution plan and revision.
- Existing jobs expose an empty revision without migration failure.
- Database schema migration remains transactional and idempotent.

**Reviewer Checklist:**
- Hashing uses file bytes rather than normalized TOML output.
- Error reporting excludes unnecessary configuration content.
- Failed loads cannot replace the last-known-good catalog.
- Job execution continues using immutable plan snapshots.
- Migration preserves all existing projects, jobs, events, and contexts.
- Retry behavior never silently adopts a newer configuration.

**Verification Checks:**
- `uv run pytest tests/test_config.py tests/test_config_inspection.py tests/test_runtime.py tests/test_database.py`
- `uv run pytest`
- `uv build`
- `git diff --check`

**Commit:** `feat(config): track health and revisions`

### Phase 2: Expose safe dashboard APIs

**Task Guide Input:** Add dedicated Starlette dashboard APIs for OpenMCP
configuration observability. Expose overview status, configuration health,
runtime settings, targets, projects, project-resolved profiles, task-guidance
metadata, context instructions, and redacted job execution-plan details. Perform
profile resolution and source attribution on the backend. Add context-instruction
replace and clear endpoints protected by loopback checks, same-origin CSRF
headers, and expected-current-value comparison. Do not expose configuration-file
mutation through HTTP or MCP.

**Goal:** The React client receives complete, redacted dashboard data safely.

**Files:**
- Create: `src/openmcp/dashboard.py`
- Modify: `src/openmcp/models.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `src/openmcp/server.py`
- Create: `tests/test_dashboard.py`
- Modify: `tests/test_runtime.py`
- Modify: `tests/test_smoke.py`

**Tasks:**
1. Add structured dashboard response and error models.
2. Add read endpoints and backend profile source attribution.
3. Redact sensitive execution-plan fields from job responses.
4. Add loopback and CSRF-protected context mutation endpoints.

**Acceptance Criteria:**
- Dashboard routes live under `/dashboard/api`.
- Overview separates daemon and configuration health.
- Project responses show declared, inherited, effective, and source values.
- Target responses show health without provider credentials.
- Job responses show revision and safe plan details.
- System prompts and unrestricted backend arguments remain omitted.
- Context updates reject non-loopback requests.
- Context updates require a valid `X-OpenMCP-CSRF` header.
- Context updates reject stale expected values with HTTP 409.
- No new MCP mutation tool exists.

**Reviewer Checklist:**
- Route ordering cannot shadow the `/mcp` transport.
- API errors use stable JSON structures.
- Project configuration errors identify the affected source.
- Source attribution handles global, project, and inherited mappings.
- CSRF tokens use cryptographically secure randomness.
- Request-origin checks do not trust forwarded headers.
- Read endpoints omit unnecessary sensitive fields.

**Verification Checks:**
- `uv run pytest tests/test_dashboard.py tests/test_runtime.py tests/test_smoke.py`
- `uv run pytest`
- `tgrep -n "dashboard/api|X-OpenMCP-CSRF" src/openmcp tests -g '*.py'`
- `git diff --check`

**Commit:** `feat(api): expose dashboard configuration data`

### Phase 3: Build the React and FlowForge foundation

**Task Guide Input:** Add a Vite-bundled React dashboard served by the existing
Starlette application. Create the product shell, routing, API client, loading and
error foundations, and FlowForge design tokens. Copy the approved FlowForge
Libre Franklin fonts and logo into frontend source assets. Build production
assets into the Python package with stable dashboard URLs. Preserve the MCP
transport and avoid adding a separate production server or runtime dependency.

**Goal:** `/dashboard/` loads a packaged FlowForge React application.

**Files:**
- Modify: `.gitignore`
- Create: `web/package.json`
- Create: `web/package-lock.json`
- Create: `web/vite.config.js`
- Create: `web/index.html`
- Create: `web/src/main.jsx`
- Create: `web/src/App.jsx`
- Create: `web/src/api.js`
- Create: `web/src/components/AppShell.jsx`
- Create: `web/src/components/Sidebar.jsx`
- Create: `web/src/components/Topbar.jsx`
- Create: `web/src/components/StatusBadge.jsx`
- Create: `web/src/components/Alert.jsx`
- Create: `web/src/styles/colors_and_type.css`
- Create: `web/src/styles/app.css`
- Create: `web/src/styles/fonts/LibreFranklin[wght].woff2`
- Create: `web/src/styles/fonts/LibreFranklin-Italic[wght].woff2`
- Create: `web/src/assets/flowforge-logo.png`
- Create: `web/src/App.test.jsx`
- Create: `web/src/test/setup.js`
- Modify: `src/openmcp/dashboard.py`
- Create: `src/openmcp/dashboard_static/index.html`
- Create: `src/openmcp/dashboard_static/assets/app.js`
- Create: `src/openmcp/dashboard_static/assets/app.css`
- Modify: `pyproject.toml`

**Tasks:**
1. Scaffold React, Vite, and frontend tests.
2. Apply FlowForge tokens, typography, logo, and product shell.
3. Add client routing and the typed API boundary.
4. Serve and package stable production assets.

**Acceptance Criteria:**
- `/dashboard/` serves the React application.
- Direct dashboard routes return the SPA entry point.
- `/mcp` behavior remains unchanged.
- The UI uses FlowForge CSS variables instead of raw brand colors.
- The shell uses the 200px sidebar and 64px top bar.
- Libre Franklin and the FlowForge logo load locally.
- Keyboard focus uses the FlowForge interaction-blue ring.
- Production assets are included in the built wheel.
- Development uses Vite without introducing another production process.

**Reviewer Checklist:**
- No gradients, decorative blobs, emoji, or filled icon set appear.
- Green remains limited to actions, selections, and success.
- Blue remains limited to interaction and focus.
- Route fallbacks never intercept dashboard API requests.
- Asset paths work beneath `/dashboard/`.
- Generated assets are reproducible from `npm run build`.
- Python packaging includes every generated asset.

**Verification Checks:**
- `npm --prefix web ci`
- `npm --prefix web run test`
- `npm --prefix web run build`
- `uv run pytest tests/test_dashboard.py tests/test_smoke.py`
- `uv build`
- `python -c "import glob,zipfile; p=glob.glob('dist/openmcp-*.whl')[-1]; n=zipfile.ZipFile(p).namelist(); assert any(x.endswith('dashboard_static/index.html') for x in n); assert any('/dashboard_static/assets/' in x for x in n)"`
- `git diff --check`

**Commit:** `feat(dashboard): add react flowforge shell`

### Phase 4: Add configuration observability views

**Task Guide Input:** Implement the FlowForge React views for OpenMCP overview,
projects, project effective configuration, profile resolution, targets, runtime
settings, and configuration health. Use dense data grids, tabs, status badges,
alerts, and docked inspectors. Show live, restart-required, editable, and
repository-sourced classifications. Preserve declared and effective values,
source attribution, horizontal table scrolling, loading stability, and
accessible keyboard behavior.

**Goal:** Operators can understand current OpenMCP routing and configuration.

**Files:**
- Create: `web/src/components/DataGrid.jsx`
- Create: `web/src/components/PageHeader.jsx`
- Create: `web/src/components/TabbedPanel.jsx`
- Create: `web/src/components/Inspector.jsx`
- Create: `web/src/components/LoadingRows.jsx`
- Create: `web/src/screens/Overview.jsx`
- Create: `web/src/screens/Projects.jsx`
- Create: `web/src/screens/ProjectDetail.jsx`
- Create: `web/src/screens/Targets.jsx`
- Create: `web/src/screens/RuntimeSettings.jsx`
- Create: `web/src/screens/ConfigHealth.jsx`
- Create: `web/src/hooks/useDashboardQuery.js`
- Modify: `web/src/App.jsx`
- Modify: `web/src/styles/app.css`
- Create: `web/src/screens/Overview.test.jsx`
- Create: `web/src/screens/ProjectDetail.test.jsx`
- Create: `web/src/screens/ConfigHealth.test.jsx`

**Tasks:**
1. Build reusable dense operational components.
2. Add overview, projects, targets, and runtime views.
3. Add effective profile resolution and source inspection.
4. Add configuration-health and recovery states.

**Acceptance Criteria:**
- Overview links summary values to filtered views.
- Project tables show alias, root, profile, activity, and health.
- Effective configuration distinguishes declarations and inheritance.
- Profile views show parent, workflows, targets, attempts, and timeouts.
- Targets show backend, model, isolation, concurrency, activity, and health.
- Runtime settings group live and restart-required values.
- Invalid configuration stays visible beside a running daemon state.
- Tables use 44px headers and 56px rows.
- Narrow layouts scroll tables instead of converting them into cards.

**Reviewer Checklist:**
- The frontend never recomputes profile inheritance.
- Repository and global sources remain visibly distinct.
- Status always pairs color, icon, and label.
- Empty and error states provide specific recovery actions.
- Refresh failures preserve previously loaded data.
- All interactive rows use correct pointer and keyboard behavior.

**Verification Checks:**
- `npm --prefix web run test`
- `npm --prefix web run build`
- `uv run pytest tests/test_dashboard.py`
- `git diff --check`

**Commit:** `feat(dashboard): show resolved configuration`

### Phase 5: Add context editing and job traceability

**Task Guide Input:** Complete the OpenMCP React dashboard with context-instruction
editing, job revision traceability, status polling, conflict recovery, and
accessibility coverage. Use the FlowForge 660px modal for add, edit, and clear
actions. Send the bootstrap CSRF token and expected current value on mutations.
Show that context changes affect future jobs only. Display redacted execution
plans and configuration revisions for jobs. Update public documentation and
verify packaged production behavior.

**Goal:** Operators safely edit context instructions and trace job configuration.

**Files:**
- Create: `web/src/components/Modal.jsx`
- Create: `web/src/components/ContextInstructionEditor.jsx`
- Create: `web/src/screens/ContextInstructions.jsx`
- Create: `web/src/screens/Jobs.jsx`
- Create: `web/src/screens/JobDetail.jsx`
- Create: `web/src/hooks/usePolling.js`
- Modify: `web/src/api.js`
- Modify: `web/src/App.jsx`
- Modify: `web/src/screens/ProjectDetail.jsx`
- Modify: `web/src/styles/app.css`
- Create: `web/src/screens/ContextInstructions.test.jsx`
- Create: `web/src/screens/Jobs.test.jsx`
- Create: `web/src/integration/dashboard-flow.test.jsx`
- Modify: `tests/test_dashboard.py`
- Modify: `README.md`

**Tasks:**
1. Add CSRF-protected context add, edit, and clear flows.
2. Add job revision and redacted execution-plan views.
3. Add polling, stale-value conflict recovery, and announcements.
4. Document dashboard access, scope, and security boundaries.

**Acceptance Criteria:**
- Context edits require explicit confirmation.
- Clear uses an outlined destructive action.
- Stale edits receive a refresh-and-retry workflow.
- Successful changes state that only future jobs are affected.
- Active jobs poll every five seconds and stop when terminal.
- Job details show revision identity or unavailable status.
- Job details never show system prompts or unrestricted arguments.
- Async changes announce status through an accessible live region.
- Keyboard users can complete the full edit workflow.
- README documents `/dashboard/`, loopback scope, and read-only boundaries.

**Reviewer Checklist:**
- CSRF tokens never enter URLs or logs.
- The UI cannot submit file-managed configuration changes.
- Polling stops after unmount and terminal states.
- Modal focus enters, remains trapped, and returns correctly.
- Destructive clearing remains visually secondary.
- Job plan redaction matches backend guarantees.
- Documentation does not imply remote administration support.

**Verification Checks:**
- `npm --prefix web run test`
- `npm --prefix web run build`
- `uv run pytest tests/test_dashboard.py tests/test_runtime.py tests/test_database.py`
- `uv run pytest`
- `uv build`
- `python -c "import glob,zipfile; p=glob.glob('dist/openmcp-*.whl')[-1]; n=zipfile.ZipFile(p).namelist(); assert any(x.endswith('dashboard_static/index.html') for x in n)"`
- `git diff --check`

**Commit:** `feat(dashboard): manage context instructions`
