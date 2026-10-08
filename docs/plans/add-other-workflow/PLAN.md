# Add the `other` Built-in Workflow Plan

Design: `docs/plans/add-other-workflow/DESIGN.md`

This plan adds one explicit workflow route. It preserves existing profiles and
requires operators to map `other` before using it.

### Phase 1: Add explicit `other` routing

**Task Guide Input:** Add `other` as the fourth fixed built-in workflow. Expose
it through validation and MCP discovery. Allow profile declarations to map it
explicitly. Preserve existing profiles that omit it. Such profiles must fail
only when an `other` job is submitted. Persist `other` through execution plans,
jobs, and context roles. Update doctor guidance, tests, and README examples.
Do not add fallback routing, dynamic workflow names, or migrations.

**Profile:** `Resolve at execution`

**Goal:** `other` routes like every fixed workflow.

**Files:**
- Modify: `src/openmcp/workflows.py`
- Modify: `src/openmcp/server.py`
- Modify: `tests/orchestration_helpers.py`
- Modify: `tests/test_workflows.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_planning.py`
- Modify: `tests/test_execution.py`
- Modify: `tests/test_server.py`
- Modify: `README.md`

**Tasks:**
1. Add `other` to fixed validation and discovery.
2. Cover explicit and missing profile mappings.
3. Prove plan, job, and context-role persistence.
4. Update doctor guidance and public documentation.

**Acceptance Criteria:**
- `BUILTIN_WORKFLOWS` equals `("consult", "implement", "other", "review")`.
- `get_workflow("other")` returns `"other"`.
- Unknown workflow names remain rejected.
- Profile declarations accept an `other` key.
- Existing profiles without `other` still load.
- Submitting `other` through an unmapped profile fails clearly.
- Mapped `other` jobs resolve and execute normally.
- Execution plans serialize and parse `other`.
- Job records and context history retain the `other` role.
- The workflows MCP resource exposes `other`.
- Doctor guidance checks all four workflows.
- README examples include an explicit `other` mapping.
- No database migration or fallback routing is added.

**Reviewer Checklist:**
- Existing workflow behavior remains unchanged.
- Existing three-workflow configurations remain valid.
- `other` never silently selects another workflow mapping.
- Profile inheritance handles `other` generically.
- Immutable plans preserve `other`.
- Context sessions remain separated by workflow role.
- Discovery and doctor guidance stay synchronized.
- External hard-coded clients remain documented as follow-up scope.

**Verification Checks:**
- `uv run pytest tests/test_workflows.py tests/test_config.py tests/test_planning.py tests/test_execution.py tests/test_server.py`
- `uv run pytest`
- `uv build`
- `tgrep -n "\"other\"|other =" src/openmcp tests README.md -g "*.py" -g "*.md"`
- `tgrep -F "implement, review, and consult" src/openmcp tests README.md -n`
- Expect no stale three-workflow guidance.
- `git diff --check`

**Commit:** `feat(workflows): add other workflow`
