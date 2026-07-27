# Workflow Capability Simplification Plan

Design: `docs/plans/workflow-capability-simplification/DESIGN.md`

This plan removes redundant capability metadata. Fixed workflow routing remains
the stable public contract. Phase 1 simplifies core routing and immutable plans.
Phase 2 updates public models, configuration surfaces, and the dashboard.

### Phase 1: Simplify workflow and target routing

**Task Guide Input:** Remove target capability metadata from OpenMCP's core
configuration and execution-plan model. Keep only the fixed `consult`,
`implement`, and `review` workflow strings. Reject unknown workflow keys during
profile configuration loading. Preserve target selection, retries, immutable
plans, context roles, and read-only target policy. Existing serialized plans
containing capability fields must remain parseable.

**Profile:** `Resolve at execution`

**Goal:** Fixed workflows route targets without capability metadata.

**Files:**
- Modify: `src/openmcp/workflows.py`
- Modify: `src/openmcp/config.py`
- Modify: `src/openmcp/planning.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `tests/test_workflows.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_planning.py`
- Modify: `tests/test_execution.py`
- Modify: `tests/orchestration_helpers.py`

**Tasks:**
1. Replace `WorkflowDefinition` with validated workflow strings.
2. Remove target capabilities from configuration and plan snapshots.
3. Reject unknown profile workflow keys during loading.
4. Update core fixtures and workflow-routing tests.

**Acceptance Criteria:**
- `BUILTIN_WORKFLOWS` remains unchanged.
- Unknown submitted workflow names remain rejected.
- Unknown profile workflow keys fail configuration loading.
- Every built-in workflow still resolves configured targets.
- New execution plans contain no capabilities.
- Legacy execution plans containing capabilities still parse.
- Target selection and retry behavior remain unchanged.
- No database migration is introduced.

**Reviewer Checklist:**
- Workflow strings remain durable context roles.
- Fixed workflow discovery remains compatible.
- No dynamic workflow registry is introduced.
- Capability removal does not alter read-only policy.
- Old queued jobs remain executable.
- No unrelated target validation is added.

**Verification Checks:**
- `uv run pytest tests/test_workflows.py tests/test_config.py tests/test_planning.py tests/test_execution.py`
- `tgrep -n "WorkflowDefinition|_BUILTIN_WORKFLOW_CAPABILITIES|capabilities" src/openmcp/workflows.py src/openmcp/config.py src/openmcp/planning.py src/openmcp/runtime.py`
- `git diff --check`

**Commit:** `refactor(workflows): remove target capabilities`

### Phase 2: Remove capabilities from public surfaces

**Task Guide Input:** Complete target capability removal across OpenMCP's public
models, dashboard APIs, configuration writer, React monitor, tests, generated
assets, and documentation. Target responses and config responses must omit the
field. A config PUT must remove retained legacy capability keys. Preserve all
remaining target health, capacity, and model presentation.

**Profile:** `Resolve at execution`

**Goal:** No supported public surface exposes target capabilities.

**Files:**
- Modify: `src/openmcp/models.py`
- Modify: `src/openmcp/execution.py`
- Modify: `src/openmcp/dashboard.py`
- Modify: `src/openmcp/config_writer.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_logging.py`
- Modify: `tests/test_dashboard.py`
- Modify: `web/src/lib/types.ts`
- Modify: `web/src/lib/api.test.ts`
- Modify: `web/src/views/Targets.tsx`
- Modify: `web/src/views/Targets.test.tsx`
- Modify: `web/src/views/Overview.test.tsx`
- Modify: `README.md`
- Modify: `src/openmcp/dashboard_static/index.html`
- Replace: `src/openmcp/dashboard_static/assets/`

**Tasks:**
1. Remove capabilities from target and config responses.
2. Strip legacy keys while preserving unrelated target data.
3. Remove the dashboard field, column, and fixtures.
4. Rebuild assets and update public documentation.

**Acceptance Criteria:**
- MCP and dashboard target responses omit capabilities.
- Dashboard config responses omit capabilities.
- Config PUT removes retained target capability keys.
- Existing TOML files containing capabilities still load.
- The Targets view retains all remaining columns.
- Generated assets match current web sources.
- README examples contain no capability declarations.
- Full Python and web suites pass.

**Reviewer Checklist:**
- Public Python and TypeScript models remain synchronized.
- Config writes preserve unrelated target comments and keys.
- Only the obsolete capability column disappears.
- Generated assets contain the rebuilt application.
- Target health and capacity rendering remains unchanged.
- The fixed workflows resource remains unchanged.

**Verification Checks:**
- `uv run pytest tests/test_server.py tests/test_logging.py tests/test_dashboard.py`
- `npm --prefix web test -- --run`
- `npm --prefix web run build`
- `uv run pytest`
- `uv build`
- `tgrep -w "capabilities" src/openmcp web/src tests README.md -g "*.py" -g "*.ts" -g "*.tsx" -g "*.md"`
- Expect only compatibility removal and legacy-fixture matches.
- `git diff --check`

**Commit:** `refactor(api): remove capability surfaces`
