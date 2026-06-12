---
description: Interactively configure the OPENMCP_* environment variables and save them to ~/.openmcp/.env.
---

Configure the OpenMCP backend environment for this plugin and write it to `~/.openmcp/.env`.

Steps:
1. Read the existing `~/.openmcp/.env` if it exists; use any current values as defaults.
2. Collect a value for each variable below (offer the listed default; skip blanks).
3. Write `~/.openmcp/.env` with `KEY=value` lines (create `~/.openmcp/` if missing). Do not commit it.
4. Report the final file path and the keys written.

| Variable | Purpose | Default |
|---|---|---|
| `OPENMCP_CODEX_MODEL_DEFAULT` | Default model when `backend="codex"` | empty |
| `OPENMCP_GEMINI_MODEL_DEFAULT` | Default model when `backend="gemini"` | empty |
| `OPENMCP_AGY_MODEL_DEFAULT` | Default model when `backend="agy"` | empty |
| `OPENMCP_CODEX_PROFILE_DEFAULT` | Default Codex profile | `mcp_execution` |
| `OPENMCP_CODEX_REASONING_MODEL` | Codex model used when `reasoning` is set | empty |
| `OPENMCP_GEMINI_REASONING_MODEL` | Gemini model used when `reasoning` is set | empty |
| `OPENMCP_AGY_REASONING_MODEL` | Base agy model used when `reasoning` is set | empty |
| `OPENMCP_GEMINI_ROUTE_TO_AGY` | Route `backend="gemini"` calls to `agy` | `false` |
| `OPENMCP_LOG_FILE` | OpenMCP log file path | `~/.openmcp/openmcp.log` |
| `OPENMCP_LOG_LEVEL` | OpenMCP log level | `INFO` |
