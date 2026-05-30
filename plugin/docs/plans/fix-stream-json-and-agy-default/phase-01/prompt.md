# Phase 1 — Fix gemini/codex stream-json + agy default-model behavior

You are the Codex worker. Edit three files in the openmcp package:

- `C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp/src/openmcp/backends/gemini.py`
- `C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp/src/openmcp/backends/codex.py`
- `C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp/src/openmcp/server.py`

## Background

Investigation (already complete — do not redo) found:

1. `gemini.py` parses stdout as JSONL (expects `type=="turn.completed"`, reads `session_id` from JSON events) but never passes `--output-format stream-json` to the gemini CLI. So gemini emits plain text, no session id is captured, and the four fallbacks (`history.jsonl`, `pb_signature`, `recent_conversation_file`, prior `params.SESSION_ID`) all fail because `gemini --prompt` headless mode doesn't write to those locations. Result: every gemini run logs `WARNING gemini: no session id found via stdout/history/pb/params` even though `outcome=OK`.
2. `codex.py` runs `codex exec` in plain-text mode and scans `~/.codex/sessions/*.jsonl` to recover the session id. `codex exec --json` gives the session id directly via the `thread.started` event.
3. `server.py:_resolve_model` injects `OPENMCP_AGY_MODEL_DEFAULT` into agy's `model` param when caller passes none. `_patch_model` in agy.py then writes that into `~/.gemini/antigravity-cli/settings.json`. User wants agy to respect whatever `settings.json` already has when no explicit model and no reasoning is requested. Patching is only desired for explicit `model` param or `reasoning` mode.

## Verified CLI event shapes (do not re-verify)

`gemini --output-format stream-json --prompt "..."` emits, one JSON object per line, with non-JSON noise lines interleaved (banners, warnings, deprecation notices):

```
{"type":"init","timestamp":"...","session_id":"<uuid>","model":"gemini-2.5-flash"}
{"type":"message","timestamp":"...","role":"user","content":"..."}
{"type":"message","timestamp":"...","role":"assistant","content":"...","delta":true}
{"type":"result","timestamp":"...","status":"success"|"error","stats":{...}}
```

`codex exec --json -- "..."` emits, one JSON object per line, with leading non-JSON noise (`"Reading additional input from stdin..."` etc.):

```
{"type":"thread.started","thread_id":"<uuid>"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"..."}}
{"type":"turn.completed","usage":{...}}
```

`thread_id` is the codex session id used by `codex exec resume <id>`.

## Changes required

### Task 1 — gemini.py

1. Add `"--output-format", "stream-json"` to the cmd list in `execute()`.
2. Update `is_turn_completed` to return True for `type in {"turn.completed", "result"}`.
3. Rewrite the stdout-handling loop in `execute()` so:
   - Every line is tried as JSON via `json.loads`; on `JSONDecodeError`, log at DEBUG level and skip the line (do **not** treat non-JSON noise as `agent_messages`). The `_DEPRECATED_PROMPT_WARNING` short-circuit and the plain `session id:` regex matcher become dead code under stream-json — remove them.
   - On JSON parse: capture `session_id` from `init` event; for `type=="message"` with `role=="assistant"`, append `content` to `agent_messages`; on `type=="result"` break.
4. Delete `_extract_session_id_from_history`, `_extract_session_id_from_pb_signature`, `_extract_session_id_from_recent_conversation_file`, `_CONVERSATIONS_PATH`, `_UUID_PATTERN`, `_SESSION_ID_STDOUT_RE` — and the post-loop fallback chain that calls them. After the loop, if `session_id` is still empty, fall back to `params.SESSION_ID` only; otherwise log a single info line. Drop the `gemini: no session id found via stdout/history/pb/params` warning entirely (the init event makes it impossible in practice; if it ever fires, classify as `RETRYABLE` via `_classify` instead of `OK`).

### Task 2 — codex.py

1. Add `"--json"` to the `cmd` list in `execute()` (after `--yolo`/`--skip-git-repo-check`, before `-o`).
2. After running the subprocess, parse `stdout_lines` JSONL with per-line try/except `JSONDecodeError`:
   - On `type=="thread.started"` → capture `thread_id` as primary session id.
   - On `type=="item.completed"` where `item.type=="agent_message"` → append `item.text` to a new local `parsed_agent_messages` string.
3. Adjust `_resolve_session_id` (or replace inline) so the JSONL-derived id takes priority over the `_extract_session_id_from_stdout` regex and the session-file scan. Keep `params.SESSION_ID` as final fallback. The session-file scan (`_extract_session_id_from_latest_session`) can stay as a defensive fallback but is no longer the primary path.
4. Keep the `--output-last-message` file as the primary `agent_messages` source (it's the cleanest). Use `parsed_agent_messages` as a fallback before falling back to raw `stdout_text`.

### Task 3 — server.py

In `_resolve_model`, change the `backend == "agy"` branch so that when caller passed no explicit `model` AND no `reasoning` is set, the function returns `""` (don't read `OPENMCP_AGY_MODEL_DEFAULT`). Keep the reasoning branch as-is (still reads `OPENMCP_AGY_REASONING_MODEL`). Result: agy with no caller-supplied model + no reasoning → settings.json untouched; with reasoning or explicit model → settings.json patched as today.

## Constraints

- Single-quoted Windows paths in this prompt are absolute. Pass them as-is.
- Do not add new dependencies. Do not refactor adjacent code. Do not "improve" the existing retry / classify logic.
- Match existing style (typing, dataclass with slots, module-level `log = get_logger(...)`).
- Wrap **every** `json.loads(stripped)` call site with `try/except json.JSONDecodeError`. Lines that fail to parse become DEBUG-level log entries, never raise, never become agent_messages.
- Keep behavior for empty input, timeout, unexpected exception paths unchanged.
- Update any tests in `openmcp/openmcp/tests/` that break — but do not invent new tests for the new event-shape parsing unless an existing test file already covers similar territory. Run the existing test suite before committing each task.

## Done When

- `cd C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp && python -m pytest -x -q` passes.
- gemini.py cmd contains `--output-format stream-json`.
- codex.py cmd contains `--json`.
- server.py `_resolve_model` agy branch returns `""` when neither caller-model nor reasoning is provided.
- Per-line JSON decode in both backends is guarded; no `JSONDecodeError` can propagate out of the stdout-handling loop.
- One commit per task (3 commits total), prefix `phase-1.task-<N>: <summary>`.

## Notes & journal

- Append `## Task <N>` blocks to `docs/plans/fix-stream-json-and-agy-default/phase-01/notes.md` after each task.
- Append the full `# EXTERNAL RESPONSE` block to `docs/plans/fix-stream-json-and-agy-default/phase-01/journal.md` before emitting the completion line.
