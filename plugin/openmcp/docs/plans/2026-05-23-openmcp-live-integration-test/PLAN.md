# Plan: Live agy + codex integration test

## Context

`docs/plans/2026-05-21-openmcp-unified-server/.handover.md` recorded one explicit gap:

> Live agy/codex CLI calls deferred to user — only stubbed retry/fatal + real bad-cd FATAL tested.

This plan fills that gap. Single phase, owner Codex (back-side: server-side pytest +
subprocess plumbing).

## Decisions confirmed

- Gating: pytest marker `live`. Default `pytest` skips via `addopts = "-m 'not live'"`.
- Backends covered: both `agy` and `codex`.

## Phase 1 — Live integration test

**Owner:** `codex`

**Files:**
- Modify: `openmcp/pyproject.toml`
- Create: `openmcp/tests/test_live_backends.py`

**Tasks:**
1. Register `live` marker + default `-m 'not live'` in `[tool.pytest.ini_options]`.
2. Add `openmcp/tests/test_live_backends.py` with two `@pytest.mark.live @pytest.mark.asyncio` tests calling `agy_execute` / `codex_execute` with a PONG prompt. On `outcome=="FATAL"` with `error_class in {"missing_cli","bad_cd"}` → `pytest.skip`; other FATAL → assertion failure.
3. Verify: from `openmcp/`, `pytest -q` (default run skips live), `pytest -m live -v` (skip-on-missing-CLI or pass on real env).

**Acceptance:**
- `pytest -q` from `openmcp/` → existing tests pass; 2 live deselected; no `PytestUnknownMarkWarning`.
- `pytest -m live -v` → 2 passed or 2 skipped with `missing_cli`/`bad_cd` skip reason.

**Reviewer checklist:**
- Marker registered (no warning).
- `addopts` quoted correctly in TOML.
- Live tests skip cleanly when CLI is absent.
- `cd=Path.cwd()` — no hardcoded paths.
- No new dependencies.

## Verification

```
cd C:/syncthing/Sync/.mcp-servers/openmcp/openmcp
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m pytest -m live -v
```
