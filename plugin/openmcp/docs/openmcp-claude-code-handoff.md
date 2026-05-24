# openmcp — Claude Code Handoff

Self-contained pickup guide for any Claude Code session adopting `openmcp`. Read this first if you've never used the new server.

## TL;DR

`openmcp` is a single FastMCP server that replaces `agymcp` and `codexmcp`. It exposes **one tool**, `run`, which dispatches to either backend via a `backend` field. It adds retry-with-backoff and `SESSION_ID` continuity. Legacy `agymcp` and `codexmcp` packages still exist but should be retired from MCP client configs.

## What's New vs. Legacy

| | `agymcp` / `codexmcp` (legacy) | `openmcp` (new) |
|---|---|---|
| Tools | Two servers, one tool each (`agy`, `codex`) | One server, one tool (`run`) |
| Backend selection | Tool name | `backend: "agy" \| "codex"` field |
| Retry on transient errors | No | Yes (`max_retries`, exponential backoff + jitter, SESSION_ID forwarded) |
| Response verbosity | Always full | `debug` flag (default off = token-light) |
| Error classification | Ad-hoc | Normalized `BackendResult.outcome` (OK / RETRYABLE / FATAL) |

## Tool: `run`

```python
run(
  backend: Literal["agy", "codex"],
  PROMPT: str,
  cd: Path,
  SESSION_ID: str = "",          # resume prior backend conversation
  model: str = "",               # agy MODEL / codex --model
  profile: str = "mcp-execution",# codex only, ignored for agy
  max_retries: int = 1,          # 2 total attempts on RETRYABLE outcomes
  retry_base_ms: int = 1000,     # backoff = min(base * 2^attempt, 8000) ± 20% jitter
  debug: bool = False,           # response verbosity
) -> dict
```

### Response shapes

**`debug=False` (default, token-light) — always exactly 3 keys:**
```json
{ "success": true,  "SESSION_ID": "abc-123", "error": "" }
{ "success": false, "SESSION_ID": "",         "error": "The workspace root directory ... does not exist." }
```

**`debug=True` — full payload (use when you actually need to read agent output inline):**
```json
{
  "success": true,
  "SESSION_ID": "abc-123",
  "agent_messages": "...",
  "attempts": 2,
  "warning": "no SESSION_ID"   // optional, only when applicable
}
```

### When to pass `debug=True`

Set `debug=True` only if your orchestrator needs the full `agent_messages` payload inline in the tool reply. If the worker is already writing its own response file (e.g. `responses/phase-N.md` in superpowers-ccg workflows), leave `debug=False` — duplicating agent output in the tool reply burns tokens.

## Installation

`uvx` is the recommended path — no venv to manage, no editable install, runs the published entrypoint directly from a source you point it at.

### Option A — `uvx` from GitHub (recommended)

The Python package lives at `openmcp/` inside the repo, so pass `subdirectory=openmcp`:

```bash
uvx --from "git+https://github.com/sitien173/openmcp.git#subdirectory=openmcp" openmcp --help
```

Pin to a specific commit or tag for reproducibility:

```bash
uvx --from "git+https://github.com/sitien173/openmcp.git@<sha-or-tag>#subdirectory=openmcp" openmcp
```

### Option B — `uvx` from a local checkout

```bash
uvx --from ./openmcp openmcp
```

### Option C — editable install (dev)

Only if you're modifying the source.

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -e "./openmcp[dev]"
.venv/Scripts/python.exe -m pytest openmcp/tests -x
```

## MCP Client Configuration

Replace both legacy entries with a single `openmcp` entry. The `uvx` form keeps the client config portable — no absolute venv path.

### Example (Claude Code `~/.mcp.json` or equivalent)

```json
{
  "mcpServers": {
    "openmcp": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/sitien173/openmcp.git#subdirectory=openmcp",
        "openmcp"
      ],
      "env": {}
    }
  }
}
```

Local-checkout variant:

```json
{
  "mcpServers": {
    "openmcp": {
      "command": "uvx",
      "args": ["--from", "C:/Users/ngosi/.mcp-servers/openmcp/openmcp", "openmcp"],
      "env": {}
    }
  }
}
```

`uvx` resolves dependencies on first launch and caches them; subsequent starts are fast. On Windows, `uvx` (from `uv`) must be on PATH — install via `winget install astral-sh.uv` or `pipx install uv`.

After updating the config:
1. Reconnect MCP in Claude Code (`/mcp` or `/reload-plugins`).
2. Confirm the tool `mcp__openmcp__run` is present.
3. Delete or comment out the `agymcp` / `codexmcp` entries — they're now redundant.

## Migration Cheatsheet

| Old call | New call |
|---|---|
| `mcp__agymcp__agy(PROMPT=..., cd=...)` | `mcp__openmcp__run(backend="agy", PROMPT=..., cd=...)` |
| `mcp__codexmcp__codex(PROMPT=..., cd=..., profile="mcp-execution")` | `mcp__openmcp__run(backend="codex", PROMPT=..., cd=..., profile="mcp-execution")` |

`SESSION_ID` field name is unchanged. `MODEL` (agy) is now lowercase `model` to match codex; this is a breaking rename — update any callers.

## Behavior Details

- **Retry trigger** — only `BackendResult.outcome == "RETRYABLE"` (subprocess timeout, transient reconnect, model rate limit / 5xx, missing `agent_messages`). FATAL outcomes (bad `cd`, CLI missing, auth, JSON decode at frame level, invalid model/profile) return immediately with `attempts == 1`.
- **SESSION_ID forwarding on retry** — if attempt N returned a non-empty `SESSION_ID`, attempt N+1 reuses it so the underlying CLI resumes the same conversation rather than starting fresh.
- **Backoff** — `min(retry_base_ms * 2**attempt, 8000)` ms ± 20% jitter; applied between attempts, not before attempt 1.
- **Backends transport-agnostic** — `openmcp.backends.agy.execute` and `openmcp.backends.codex.execute` import no FastMCP; you can call them directly from Python without the MCP layer.

## Source Map

```
openmcp/
├── pyproject.toml
└── src/openmcp/
    ├── __init__.py
    ├── cli.py             # entry: `openmcp` → mcp.run(transport="stdio")
    ├── server.py          # FastMCP + the @mcp.tool `run` dispatcher
    ├── retry.py           # run_with_retry(execute_fn, params, max_retries, retry_base_ms)
    └── backends/
        ├── __init__.py    # BackendResult dataclass
        ├── agy.py         # AgyParams + execute (winpty/log-tail extracted from agymcp)
        └── codex.py       # CodexParams + execute (JSON-line stream extracted from codexmcp)
```

## Reference Documents

- Design: `docs/plans/2026-05-21-openmcp-unified-server-design.md`
- Implementation plan: `docs/plans/2026-05-21-openmcp-unified-server/PLAN.md` + `PHASE-{1,2,3}.md`
- Validation report: `docs/plans/2026-05-21-openmcp-unified-server/validation-report.md`
- `debug` flag design: `docs/plans/2026-05-21-openmcp-debug-flag-design.md`

## Known Gaps

- Live `agy` / `codex` CLI happy-path was not exercised in CI — only stubbed retry/fatal and real bad-`cd` FATAL. First real call from Claude Code is the smoke test.
- No streaming output to the MCP caller (collected reply, same as legacy).
- No auto-routing between backends; caller picks `backend` explicitly.
