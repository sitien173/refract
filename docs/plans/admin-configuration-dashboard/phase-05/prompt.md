## Original User Request
Complete the OpenMCP admin configuration dashboard. Add safe context editing and job traceability to the existing React and FlowForge dashboard.

## Phase
Add context editing and job traceability.

## Tasks
- task-1: Add CSRF-protected context add, edit, and clear flows.
- task-2: Add job revision and redacted execution-plan views.
- task-3: Add polling, stale-value conflict recovery, and announcements.
- task-4: Document dashboard access, scope, and security boundaries.

## Context
Phases 1 through 4 added revision-stamped jobs, safe dashboard APIs, the packaged React shell, and configuration observability screens. Complete the dashboard using only the existing context mutation and job APIs. Context instructions are the only editable configuration surface. File-managed daemon, target, profile, task-guide, and routing settings remain read-only.

## Files
- `web/src/components/Modal.jsx`
- `web/src/components/ContextInstructionEditor.jsx`
- `web/src/screens/ContextInstructions.jsx`
- `web/src/screens/Jobs.jsx`
- `web/src/screens/JobDetail.jsx`
- `web/src/hooks/usePolling.js`
- `web/src/api.js`
- `web/src/App.jsx`
- `web/src/screens/ProjectDetail.jsx`
- `web/src/styles/app.css`
- `web/src/screens/ContextInstructions.test.jsx`
- `web/src/screens/Jobs.test.jsx`
- `web/src/integration/dashboard-flow.test.jsx`
- `tests/test_dashboard.py`
- `README.md`
- `src/openmcp/dashboard_static/index.html`
- `src/openmcp/dashboard_static/assets/`

## Done When
- Context add, edit, and clear use the existing CSRF boundary.
- Every mutation sends the expected current value.
- Context edits require explicit confirmation.
- Clear uses an outlined destructive action.
- Conflicts provide refresh-and-retry recovery.
- Successful changes state that only future jobs are affected.
- Active jobs poll every five seconds and stop when terminal.
- Job details show configuration revision or unavailable status.
- Job details show only backend-redacted execution-plan fields.
- Job details never show system prompts or unrestricted arguments.
- Async changes announce status through an accessible live region.
- Keyboard users can complete the full edit workflow.
- Modal focus enters, remains trapped, and returns correctly.
- Polling stops after unmount and terminal states.
- CSRF tokens never enter URLs, logs, or visible UI.
- The UI cannot submit file-managed configuration changes.
- README documents `/dashboard/`, loopback scope, editable context instructions, read-only file-managed configuration, and no remote administration support.
- Production assets are rebuilt and packaged.
- `npm --prefix web run test`
- `npm --prefix web run build`
- `uv run pytest tests/test_dashboard.py tests/test_runtime.py tests/test_database.py`
- `uv run pytest`
- `uv build`
- `python -c "import glob,zipfile; p=glob.glob('dist/openmcp-*.whl')[-1]; n=zipfile.ZipFile(p).namelist(); assert any(x.endswith('dashboard_static/index.html') for x in n)"`
- `git diff --check`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's `notes.md` and `journal.md`. Reuse the existing FlowForge components, API client, and server-redacted job shape. Do not expose or reconstruct hidden job input. Do not add remote administration, CORS, credentials behavior, or another production process. Keep destructive actions visually secondary.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
