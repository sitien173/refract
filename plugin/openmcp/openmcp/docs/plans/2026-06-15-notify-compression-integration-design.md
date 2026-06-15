# Design: notify + response-compression integration for openmcp

**Date:** 2026-06-15
**Status:** Confirmed (brainstorming) — ready for implementation planning
**Scope:** Two new best-effort integrations in the openmcp MCP server's `run()` flow.

## Goal

1. **Notifications** — emit worker lifecycle notifications (start, each retryable
   attempt, success, final error) via
   [`py-notify-system`](https://github.com/sitien173/py-notify-system).
2. **Response compression** — compress the worker's *response* (not the prompt)
   with [`the-token-company-python`](https://github.com/TheTokenCompany/the-token-company-python)
   to save tokens, while preserving the ERP (`# EXTERNAL RESPONSE`) contract the
   coordinator scans.

## Confirmed decisions

| Decision | Choice |
|---|---|
| Compression scope | **Response only** (prompt is never altered) |
| ERP handling | **Compress prose sections only** — SUMMARY + NOTES prose compressed; META, FILES MODIFIED, COMMITS, SPEC COMPLIANCE, NEXT, and the completion line stay verbatim |
| Control surface | **Env-global only** (`OPENMCP_*`); `run()` tool signature unchanged |
| Notify events | **All:** start, each retryable attempt, success, final error |
| Failure posture | Both features strictly **best-effort** — never break a run |

## Key constraint

TTC compression is **lossy** (it strips wording it deems redundant) and there is
**no decompress step**. The worker receives nothing compressed; the coordinator
receives a lossily compressed response. Therefore compression must be **ERP-aware**:
only free-text prose (SUMMARY, NOTES) is compressed; all coordinator-critical
structure (section headers, the `| Action | Path | Change |` table, commit hashes,
file paths, `Phase N completed…` completion line) passes through byte-identical.

## Library APIs (verified)

**py-notify-system** (`notify_system`):
```python
from notify_system import notify
notify("msg", status="task_complete", title="CI",
       context={...}, desktop=True, webhook=False, sound=False)
# also: Config, Notification, NotificationClient
```
Sync API; webhook uses httpx, sound uses playsound (may block). Channels degrade
gracefully if optional extras absent.

**the-token-company-python** (`thetokencompany`):
```python
from thetokencompany import TheTokenCompany, AsyncTheTokenCompany, protect
client = TheTokenCompany(api_key="...")
result = client.compress(text, model="bear-1.2", aggressiveness=0.7)
result.output            # compressed text
result.tokens_saved
result.compression_ratio
# AsyncTheTokenCompany: async context manager, await client.compress(...)
# protect("marker") shields text from compression
```

---

## Section 1 — Architecture & module layout

Two new self-contained, **best-effort** modules under `src/openmcp/`, plus minimal
hook calls in existing code. Neither feature can break a worker run — both no-op on
disabled / misconfigured / error.

**`src/openmcp/notify.py`** — thin wrapper over `notify_system`.
- Reads `OPENMCP_NOTIFY_*` env via the existing `_effective_env()` precedence.
- Public API: `emit_start(...)`, `emit_attempt_failed(...)`, `emit_finish(...)`, `emit_error(...)`.
- `notify_system.notify()` is sync and may block (webhook/sound), so calls are
  dispatched through `asyncio.to_thread(...)` inside try/except that only logs.
- Import failure (extra not installed) or `OPENMCP_NOTIFY_ENABLED` falsy → every
  function no-ops.

**`src/openmcp/compression.py`** — ERP-aware response compressor.
- `async compress_response(text, env) -> str`. Uses `AsyncTheTokenCompany`.
- Disabled / no API key / import failure → returns `text` unchanged.
- ERP-aware: if text contains `# EXTERNAL RESPONSE`, compress **only** the prose
  under `## SUMMARY` and `## NOTES`; all other lines pass through verbatim. No ERP
  block → compress whole text as free prose.
- Any exception/timeout → return original `text` (log warning).

**Hook points (existing files):**
- `server.py::run()` — `emit_start` before dispatch; `emit_finish`/`emit_error`
  after result; `await compress_response(...)` on `agent_messages` just before the
  return dict.
- `retry.py::run_with_retry()` — `emit_attempt_failed(...)` on each retryable
  attempt before backoff sleep.

---

## Section 2 — Data flow

**Outbound (notify, no payload mutation):**
```
run(PROMPT, backend, …)
  └─ _effective_env()
  └─ emit_start(backend, model, session)         # status="task_started"
  └─ run_with_retry(execute_fn, params)
        ├─ attempt 1 → RETRYABLE → emit_attempt_failed(attempt, error)  # status="task_retry"
        ├─ backoff sleep
        ├─ attempt 2 → OK
        └─ returns {success, SESSION_ID, agent_messages, attempts}
  └─ success? emit_finish(attempts)               # status="task_complete"
     else      emit_error(error, attempts)        # status="task_error"
```
Prompt is never altered. Notifications are fire-and-forget; failures swallowed.

**Inbound (compression, mutates only returned text):**
```
result = run_with_retry(...)
agent_messages = result["agent_messages"]
agent_messages = await compress_response(agent_messages, env)   # NEW
return {success, SESSION_ID, agent_messages, error}
```

`compress_response` logic:
1. Gate: enabled + api key + non-empty text, else return as-is.
2. Split on `# EXTERNAL RESPONSE`. Absent → one `compress()` on the whole string.
3. Present → walk by `## ` headers; collect SUMMARY and NOTES prose bodies only;
   compress each body; splice back. Everything else reassembled untouched.
4. Any exception → return original untouched string.

`env` is resolved once in `run()` (already `effective_env`) and passed to
`compress_response`. `run_with_retry` stays unchanged for compression (only its
notify hook touches it).

---

## Section 3 — Configuration (env vars)

All via `_effective_env()` precedence (process env → `~/.openmcp/.env` → plugin
config). Truthy parsing reuses `_env_truthy()` (`1/true/yes/on`).

**Notifications:**

| Var | Default | Meaning |
|---|---|---|
| `OPENMCP_NOTIFY_ENABLED` | `false` | Master switch; falsy → all emit_* no-op |
| `OPENMCP_NOTIFY_TITLE` | `openmcp` | Title passed to `notify()` |
| `OPENMCP_NOTIFY_DESKTOP` | `true` | `desktop=` toggle |
| `OPENMCP_NOTIFY_SOUND` | `false` | `sound=` toggle |
| `OPENMCP_NOTIFY_WEBHOOK` | `false` | `webhook=` toggle |

`context=` auto-populated with `{backend, session_id, model, attempts}`.
`notify_system`'s own config file governs webhook endpoints, sounds, dedup.

**Compression:**

| Var | Default | Meaning |
|---|---|---|
| `OPENMCP_COMPRESS_RESPONSE` | `false` | Master switch |
| `OPENMCP_TTC_API_KEY` | — | Required; absent → no-op |
| `OPENMCP_TTC_MODEL` | `bear-1.2` | `model=` for `compress()` |
| `OPENMCP_TTC_AGGRESSIVENESS` | `0.5` | `aggressiveness=` (bad value → default) |
| `OPENMCP_TTC_TIMEOUT_S` | `10` | Cap on compression call; exceed → verbatim |

**Dependencies** (`pyproject.toml`) — optional extras so base install stays lean
and imports degrade gracefully:
```toml
[project.optional-dependencies]
notify = ["py-notify-system @ git+https://github.com/sitien173/py-notify-system.git"]
compress = ["thetokencompany @ git+https://github.com/TheTokenCompany/the-token-company-python.git"]
```
(If `thetokencompany` is on PyPI, use a version spec instead of the git URL —
verify at implementation time.)

---

## Section 4 — Error handling & edge cases

Both features **strictly best-effort** — failures invisible to the worker contract.

**Notifications:**
- Every `emit_*` in `try/except Exception` logging at `warning`; never propagates.
- Lazy import; `ImportError` → `_AVAILABLE = False`, all emits no-op (logged once).
- `notify()` via `asyncio.to_thread` so slow webhook/sound can't stall the loop.
- `asyncio.CancelledError` re-raised, never swallowed (matches `run()`).

**Compression:**
- Gate order: enabled → key present → import OK → non-empty text. Any fail → verbatim.
- Wrapped in `asyncio.wait_for(..., OPENMCP_TTC_TIMEOUT_S)`; `TimeoutError` → verbatim.
- Any TTC exception (auth/rate-limit/network) → verbatim. Never turns success into failure.
- ERP parser defensive: missing/malformed/truncated SUMMARY/NOTES → affected region
  untouched. Worst case = no savings, never corruption.
- Empty/whitespace agent_messages → skipped.
- `CancelledError` re-raised.

**Interaction edge cases:**
- Notify fires on the pre-compression result state; compression no-op never changes
  what a notification reports.
- Compression runs on all successful responses including non-ERP free prose
  (ad-hoc Q&A, cross-validation) — safe since they carry no structural contract.

---

## Section 5 — Testing

All offline, mocked (consistent with `test_smoke.py`). Add `tests/test_notify.py`,
`tests/test_compression.py`, plus `run()`-level integration assertions.
`conftest.py` home-dir/env isolation prevents real config leakage.

**Compression (`compress_response`):**
- ERP block in → SUMMARY/NOTES prose replaced with mocked output; META, table,
  COMMITS hashes, SPEC COMPLIANCE, NEXT, completion line byte-identical.
- No ERP block → whole string passed to `compress()` once.
- Disabled / no key / import-missing → input unchanged, `compress()` never called.
- TTC raises → input unchanged.
- Timeout exceeded → input unchanged.
- Malformed/truncated ERP → no corruption, structure preserved.
- Empty agent_messages → skipped.

**Notify (`emit_*`):**
- Each emit calls mocked `notify()` with expected `status`/`title`/`context`.
- Disabled → `notify()` never called.
- `notify()` raising → swallowed, caller unaffected.
- Import-missing → no-op.
- Dispatched via `asyncio.to_thread`.

**`run()` integration (monkeypatch backend `execute`):**
- Success → `emit_start` + `emit_finish`; `agent_messages` passed through `compress_response`.
- Retryable-then-OK → `emit_attempt_failed` per retry, then `emit_finish`.
- Final failure → `emit_error`; `error`/`SESSION_ID` payload unchanged.
- Both disabled (default env) → behaviour byte-identical to today (regression guard).
