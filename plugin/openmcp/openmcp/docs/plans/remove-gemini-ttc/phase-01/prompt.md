# Phase 01 — Remove gemini backend and TTC compress feature

Owner: Codex (back-side). Repo root: `C:\syncthing\Sync\.agents\plugins\superpowers-ccg\openmcp\openmcp`.

Read first (contracts):
- `C:\syncthing\Sync\.agents\plugins\superpowers-ccg\openmcp\openmcp\.agents\shared\worker-contract.md`
- `C:\syncthing\Sync\.agents\plugins\superpowers-ccg\openmcp\openmcp\.agents\shared\erp.md`
- `C:\syncthing\Sync\.agents\plugins\superpowers-ccg\openmcp\openmcp\.agents\BACKEND.md`

## CRITICAL distinction (do not get this wrong)

There are TWO things using the word "gemini":

1. The **`gemini` backend** = `src/openmcp/backends/gemini.py` (standalone Gemini CLI, stream-json). **REMOVE THIS ENTIRELY.**
2. The **`agy` backend** = `src/openmcp/backends/agy.py` (Antigravity CLI, which happens to run Gemini models and reads `~/.gemini/antigravity-cli/...`). **KEEP THIS UNTOUCHED.** Do not delete its gemini model ids/paths.

Only remove backend option #1. After removal the only backends are `agy` and `codex`.

## Task 1 — Remove the gemini backend

Delete:
- `src/openmcp/backends/gemini.py` (whole file).

Edit `src/openmcp/server.py`:
- Remove import `from openmcp.backends.gemini import GeminiParams, execute as gemini_execute` (line ~15).
- Remove gemini env-var constants: `_ENV_GEMINI_MODEL_DEFAULT`, `_ENV_GEMINI_ROUTE_TO_AGY`, `_ENV_GEMINI_REASONING_MODEL`.
- Remove the `"gemini"` entries from `_REASONING_MODEL_DEFAULTS` and `_REASONING_MODEL_ENV`.
- `_effective_backend`: gemini routing no longer applies. Since `agy`/`codex` is now a pure identity map, remove `_effective_backend` entirely and use `backend` directly at the call site (line ~209). Remove `_ENV_GEMINI_ROUTE_TO_AGY` usage with it.
- `_resolve_model`: remove the `if backend == "gemini": return env.get(_ENV_GEMINI_MODEL_DEFAULT, "")` branch.
- Change every `Literal["agy", "codex", "gemini"]` to `Literal["agy", "codex"]` (signatures of `run`, `_resolve_model`, and `_effective_backend` if you keep it).
- Update the `run` tool `description` text: drop "or gemini" / "gemini".
- In `run()` body, the dispatch is `if agy / elif codex / else gemini`. Make it `if agy / else codex`. Remove the `GeminiParams` dispatch block.
- Module docstring line 1: drop "and gemini".

Edit tests:
- `tests/test_smoke.py`: remove the gemini import and the gemini-specific tests (`test_bad_cd_gemini_fatal`, `test_gemini_uses_stream_json_output`, `test_gemini_stream_output_without_session_id_is_ok_with_warning`).
- `tests/test_notify.py`: the failure-path integration test uses `gemini` (lines ~73-77, ~191-221). Retarget it to `codex` (use `codex_execute`, `backend="codex"`, codex model strings, drop `OPENMCP_GEMINI_*` env). Keep the test's intent (emit_error on failure) intact.
- `tests/test_live_backends.py`: remove `test_live_gemini_route_to_agy` and `test_live_gemini_execute`, and the `from openmcp.backends.gemini import ...` line.

Edit `AGENTS.md`: remove gemini backend from prose, the architecture tree (`gemini.py` node), the mermaid `GeminiExec`/`GeminiCLI` nodes and edges, the "gemini can route to agy" step, the `OPENMCP_GEMINI_MODEL_DEFAULT`, `OPENMCP_GEMINI_ROUTE_TO_AGY`, `OPENMCP_GEMINI_REASONING_MODEL` env rows, gemini from live-test instructions and `--approval-mode=yolo (gemini)` flag note. Keep all `agy`/Antigravity content (including its Gemini model names) and the `~/.gemini/antigravity-cli/...` path that belongs to agy.

Commit: `phase-01.task-1: remove gemini backend`

## Task 2 — Remove the TTC compress feature

Delete:
- `src/openmcp/compression.py` (whole file).
- `tests/test_compression.py` (whole file).

Edit `src/openmcp/server.py`:
- Remove import `from openmcp.compression import compress_response` (line ~16).
- Remove the call site `agent_messages = await compress_response(...)` (line ~316). The return dict must use `result.get("agent_messages", "") or ""` directly instead of the compressed variable.

Edit `pyproject.toml`:
- Remove the `compress = [ "the-token-company @ ..." ]` optional-dependency block.

Note: leave the historical design doc `docs/plans/2026-06-15-notify-compression-integration-design.md` as-is (dated historical record). Do not rewrite history docs.

Commit: `phase-01.task-2: remove ttc compress feature`

## Done When
- `gemini.py`, `compression.py`, `test_compression.py` are gone.
- `tgrep -i gemini src/ tests/` shows no references to the removed *backend* (agy's Gemini model names/paths in `backends/agy.py` are expected and fine).
- `tgrep -i compress src/ tests/ pyproject.toml` shows nothing.
- No dangling imports/symbols. `run()` only handles `agy` and `codex`.
- Tests pass: run `uv run pytest -q` (or `python -m pytest -q`) and paste the summary. Live tests in `test_live_backends.py` may be skipped/marked live — that's fine; unit suite must be green.

## Worker output
- Append notes to `docs/plans/remove-gemini-ttc/phase-01/notes.md` (Task 1, Task 2 blocks).
- Append full EXTERNAL RESPONSE to `docs/plans/remove-gemini-ttc/phase-01/journal.md`.
- One commit per task. Return hashes in `## COMMITS`.
