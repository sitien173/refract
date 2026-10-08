# Plan: Initialize New Agy Sessions as Projects

Design: [DESIGN.md](DESIGN.md)

Closes `B-001` by adding documented project initialization to new agy
sessions while preserving resumed conversation behavior.

---

### Phase 1: Initialize new agy sessions and preserve resume

**Task Guide Input:** Fix the Python agy backend adapter so new headless
Antigravity CLI sessions initialize project context. Add `--new-project` only
when `AgyParams.SESSION_ID` is empty. Resumed sessions must continue using
`--conversation <id>` without `--new-project`. Add regression coverage for both
command forms while preserving target argument, log file, and prompt ordering.
Use test-driven development and avoid unrelated refactoring.

**Goal:** New agy sessions load project context without changing resumed
sessions.

**Files:**
- Modify: `src/openmcp/backends/agy.py`
- Modify: `tests/test_smoke.py`

**Tasks:**
1. Add failing command-capture coverage for new and resumed sessions.
2. Conditionally add `--new-project` for new sessions only.
3. Run focused and full non-live regression checks.

**Acceptance Criteria:**
- A new session command contains `--new-project` exactly once.
- A resumed session omits `--new-project`.
- A resumed session contains `--conversation <SESSION_ID>`.
- Target arguments remain before OpenMCP transport arguments.
- `--print` and the prompt remain the final two arguments.
- Existing non-live tests pass.

**Reviewer Checklist:**
- The condition uses only `SESSION_ID` presence.
- `--new-project` cannot combine with `--conversation`.
- Continuations inherit resumed-session behavior unchanged.
- No target configuration or public API changes were added.
- Tests assert argv behavior rather than implementation details.

**Verification Checks:**
- `uv run pytest tests/test_smoke.py -k agy -q`
- `uv run pytest -q`

**Commit:** `fix(agy): initialize new sessions as projects`
