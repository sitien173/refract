# openmcp — Unified MCP Server (Design)

Date: 2026-05-21
Status: CONFIRMED (design)
Sources: cross-validated via Codex + Gemini (retry policy narrow question)

## Goal

Merge `agymcp` and `codexmcp` into a single FastMCP server, `openmcp`, exposing **one tool** that dispatches to either backend via an explicit `backend` field. Add retry-on-error with exponential backoff and SESSION_ID continuity.

## Non-goals

- No auto-routing between backends.
- No streaming output to caller (stays collected, same as today).
- No changes to existing `agymcp` / `codexmcp` packages (kept as legacy entry points during transition).

## Package Layout

```
C:/Users/ngosi/.mcp-servers/openmcp/
├── agymcp/        (untouched, legacy)
├── codexmcp/      (untouched, legacy)
└── openmcp/       NEW
    ├── pyproject.toml
    └── src/openmcp/
        ├── __init__.py
        ├── cli.py            # entry: `openmcp` → server.run()
        ├── server.py         # FastMCP, one @mcp.tool `run`
        ├── retry.py          # classify + retry loop
        └── backends/
            ├── __init__.py
            ├── agy.py        # extracted from agymcp/server.py
            └── codex.py      # extracted from codexmcp/server.py
```

## Tool Signature

```python
run(
  backend: Literal["agy", "codex"],
  PROMPT: str,
  cd: Path,
  SESSION_ID: str = "",
  model: str = "",                  # → agy MODEL or codex --model
  profile: str = "mcp-execution",   # codex only, ignored for agy
  max_retries: int = 1,             # 0 disables; per-call override
  retry_base_ms: int = 1000,
) -> dict
```

Return shape:
- Success: `{success: True, SESSION_ID, agent_messages, attempts}`
- Failure: `{success: False, error, attempts}`

## Backend Modules

Each backend exposes one async function `execute(params) -> BackendResult` with fields:
- `outcome`: `OK | RETRYABLE | FATAL`
- `SESSION_ID`, `agent_messages`, `error`, `error_class`

- `agy.py`: keeps winpty / log-tail / model-patch logic verbatim from `agymcp/server.py`.
- `codex.py`: keeps JSON-line streaming logic verbatim from `codexmcp/server.py`.

Behavior inside backends is unchanged — they only add error classification.

## Error Classification

| Condition | Class |
|---|---|
| `cd` missing, CLI not on PATH | FATAL |
| Invalid model/profile, auth errors | FATAL |
| JSON decode at frame level (codex) | FATAL |
| Subprocess timeout, `Reconnecting...`, model rate limit / 5xx | RETRYABLE |
| No `agent_messages` returned | RETRYABLE (once) |
| No `SESSION_ID` but `agent_messages` present | OK with warning, no retry |

## Retry Loop (`retry.py`)

- Wraps backend call. On `RETRYABLE` → sleep `retry_base_ms * 2^attempt` ± 20% jitter, capped at 8000ms.
- Reuses `SESSION_ID` returned by a partial attempt to preserve agent context.
- Between attempts: ensure child process tree is dead (Windows `taskkill /F /T` fallback for PTY orphans). Discard partial stream buffers.
- Returns final result with `attempts` count for telemetry.

## Defaults Rationale

- `max_retries=1` (2 total attempts): conservative; both Codex and Gemini cross-validation agreed. Higher values are explicit per-call.
- Exponential backoff 1s base, ×2, cap 8s, ±20% jitter: catches transient blips without long stalls.
- `SESSION_ID` reuse is default-on because both CLIs are stateful and fresh sessions fragment agent memory.

## Success Criteria

1. `openmcp` installs via `uv pip install -e ./openmcp` and exposes `openmcp` CLI.
2. `run(backend="agy", ...)` and `run(backend="codex", ...)` reproduce current standalone tool behavior.
3. Simulated transient error retries up to `max_retries` and recovers when the underlying issue clears.
4. Fatal error (bad `cd`) returns immediately with `attempts=1`.
5. `SESSION_ID` from attempt 1 is passed into attempt 2 when retrying.

## Cross-Validation Summary

- **Convergent (Codex + Gemini):** reuse SESSION_ID across retries, per-call config with server defaults, careful PTY/buffer cleanup, fatal: CLI/path/auth; retryable: timeout/reconnect/rate-limit.
- **Reconciled divergences:**
  - JSON decode → FATAL (Gemini's stance; existing code already tolerates non-JSON log noise separately).
  - Default `max_retries=1` (between Codex 1 and Gemini 2).
  - Backoff base 1s (between Codex 500ms and Gemini 2s).
  - Missing `SESSION_ID` with messages → success-with-warning (Codex's stance).
