# Plan: notify + response-compression integration for openmcp

**Design:** `docs/plans/2026-06-15-notify-compression-integration-design.md`
**Created:** 2026-06-15
**Backend-only Python MCP server** → every phase is back-side → **Codex** owner.
Single-side, clear scope, low blast radius → **skip Cross-Validation**.

## Routing summary

| Phase | Owner | Reason |
|---|---|---|
| 1 — Notifications | `codex` | back-side: server/MCP lifecycle hooks |
| 2 — Response compression | `codex` | back-side: server/MCP output pipeline |

Both phases are **test-first** (`test-driven-development`): failing test before
production code, RED→GREEN recorded in `notes.md`. Both features are strictly
best-effort — they must never alter the existing `run()` contract when disabled
(default env). A regression test (defaults → byte-identical behaviour) guards this
in each phase.

---

### Phase 1: Worker lifecycle notifications

**Owner:** `codex`

**Goal:** `run()` emits best-effort notifications via `py-notify-system` on worker
start, each retryable attempt, success, and final error — gated by `OPENMCP_NOTIFY_*`
env, no-op when disabled or when the optional dependency is absent.

**Files:**
- Create: `src/openmcp/notify.py`
- Create: `tests/test_notify.py`
- Modify: `src/openmcp/server.py` (call `emit_start` / `emit_finish` / `emit_error` in `run()`)
- Modify: `src/openmcp/retry.py` (call `emit_attempt_failed` per retryable attempt)
- Modify: `pyproject.toml` (add `notify` optional extra)

**Tasks:**
1. Write `tests/test_notify.py` first (RED): mocked `notify_system.notify`, assert
   each `emit_*` sends expected `status`/`title`/`context`; disabled → never called;
   `notify()` raising → swallowed; import-missing → no-op; dispatch via `asyncio.to_thread`.
2. Implement `src/openmcp/notify.py`: lazy import + `_AVAILABLE` guard, `_effective_env`
   reads, `emit_start/emit_attempt_failed/emit_finish/emit_error`, each wrapped in
   try/except (log-only, re-raise `CancelledError`), blocking `notify()` via
   `asyncio.to_thread`.
3. Hook `server.py::run()` (start before dispatch; finish/error after result, on the
   pre-compression result state) and `retry.py::run_with_retry()` (attempt-failed per
   retryable attempt before backoff). Add `notify` extra to `pyproject.toml`.
4. Add `run()`-level integration assertions (monkeypatched backend `execute`): success
   → start+finish; retryable-then-OK → attempt_failed per retry + finish; final failure
   → error; defaults (disabled) → behaviour byte-identical to today.

**Acceptance Criteria:**
- Notifications fire on all four events when `OPENMCP_NOTIFY_ENABLED` truthy.
- `context` carries `{backend, session_id, model, attempts}`.
- Disabled / import-missing / `notify()` raising never affects the `run()` payload or raises.
- `notify()` invoked off the event loop (`asyncio.to_thread`).

**Reviewer Checklist:**
- Test-first evidence (RED→GREEN) recorded in `notes.md`.
- `CancelledError` re-raised, not swallowed (matches existing `run()` handling).
- No change to `run()` return shape; default-env regression test passes.
- `pyproject.toml` extra installs `py-notify-system` from the git URL.
- Edge cases: empty/missing env, all channels off, `notify_system` extra absent.

**Integration Checks:**
- `uv run pytest tests/test_notify.py -v`
- `uv run pytest` (full offline suite — no regressions)

---

### Phase 2: ERP-aware response compression

**Owner:** `codex`

**Goal:** `run()` compresses the worker's `agent_messages` via
`the-token-company-python` before returning, ERP-aware (only `## SUMMARY` and
`## NOTES` prose compressed; all other ERP structure verbatim), gated by
`OPENMCP_COMPRESS_RESPONSE` + `OPENMCP_TTC_API_KEY`, strictly best-effort.

**Files:**
- Create: `src/openmcp/compression.py`
- Create: `tests/test_compression.py`
- Modify: `src/openmcp/server.py` (await `compress_response(agent_messages, env)` before return dict)
- Modify: `pyproject.toml` (add `compress` optional extra)

**Tasks:**
1. Write `tests/test_compression.py` first (RED): mocked `AsyncTheTokenCompany`;
   ERP block → SUMMARY/NOTES prose replaced, META/table/COMMITS/SPEC/NEXT/completion
   line byte-identical; no ERP → whole string compressed once; disabled / no key /
   import-missing → input unchanged & `compress()` never called; TTC raises → verbatim;
   timeout exceeded → verbatim; malformed/truncated ERP → no corruption; empty text → skipped.
2. Implement `src/openmcp/compression.py`: `async compress_response(text, env)`, gate
   order (enabled → key → import → non-empty), ERP parser splicing only SUMMARY/NOTES
   prose, `asyncio.wait_for(..., OPENMCP_TTC_TIMEOUT_S)`, all exceptions → original text,
   `CancelledError` re-raised, env-driven `model`/`aggressiveness`.
3. Hook `server.py::run()`: `agent_messages = await compress_response(agent_messages, effective_env)`
   immediately before the return dict (after notify finish/error). Add `compress` extra
   to `pyproject.toml`.
4. Add `run()`-level integration assertion: successful run passes `agent_messages`
   through `compress_response`; defaults (disabled) → behaviour byte-identical to today.

**Acceptance Criteria:**
- With an ERP block, only SUMMARY/NOTES prose is compressed; every coordinator-scanned
  element (headers, FILES MODIFIED table, COMMITS hashes, completion line) is unchanged.
- Disabled / no key / import-missing / TTC error / timeout → original text returned, never a failure.
- Prompt is never compressed; only the returned `agent_messages` is touched.

**Reviewer Checklist:**
- Test-first evidence (RED→GREEN) recorded in `notes.md`.
- Best-effort proven: every TTC failure path returns the original string (tests cover each).
- ERP parser defensive against malformed/truncated blocks (no corruption, worst case = no savings).
- `CancelledError` re-raised; compression never converts success → failure.
- Default-env regression test passes; `run()` return shape unchanged.

**Integration Checks:**
- `uv run pytest tests/test_compression.py -v`
- `uv run pytest` (full offline suite — no regressions)

---

## Done When (whole plan)

- `uv run pytest` green with both features defaulting to off (no behavioural change).
- Both features verified working when enabled via env (covered by mocked unit tests).
- `pyproject.toml` exposes `notify` and `compress` optional extras.
