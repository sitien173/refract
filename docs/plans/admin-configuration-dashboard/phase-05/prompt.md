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

## Consultation Findings
- Read instructions from `context_instructions.instructions`. Use exactly the built-in workflows `consult`, `implement`, `other`, and `review`, unioned with returned instruction keys. Add a backend contract check preventing drift.
- On 409, preserve the draft. Show `unchanged`, `recovery`, and `current`. Retry using `current` as the new expected value without another GET.
- Apply successful mutation responses immediately. Manual refresh must supersede any in-flight poll.
- Add a DELETE client path. Every DELETE body includes `expected_current`. Share concurrent CSRF bootstrap work and retry forbidden mutations only for the structured retryable code.
- Keep CSRF values module-private and header-only. Never render raw error payloads.
- Reuse query polling. Stop when every displayed job is terminal. Handle hidden tabs, unmounts, and terminal transitions without queued ticks.
- Scope Jobs to a selected project. Add jobs and job-detail routes with query persistence and popstate support.
- Build an accessible portal modal with role, naming, initial focus, focus trap, Escape close, safe scrim handling, and focus restoration. Use the FlowForge 660px minimum-width token.
- Keep a persistent polite live region. Use assertive alerts for errors and conflicts.
- Explicitly render only allow-listed execution-plan keys. Empty revisions and plans get specific unavailable states. Never render hidden arguments or system prompts.
- Use outlined red destructive styling. Never use filled red or primary green for clear actions.
- Add focused tests for nested instruction envelopes, workflow set, expected values, DELETE, confirmation, conflicts, focus, CSRF containment, single bootstrap, terminal polling, redaction, revision states, and documentation boundaries.

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's `notes.md` and `journal.md`. Reuse the existing FlowForge components, API client, and server-redacted job shape. Do not expose or reconstruct hidden job input. Do not add remote administration, CORS, credentials behavior, or another production process. Keep destructive actions visually secondary.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
