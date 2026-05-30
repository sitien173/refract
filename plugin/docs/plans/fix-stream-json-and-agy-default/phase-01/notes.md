## Task 1
- Updated openmcp/openmcp/src/openmcp/backends/gemini.py to force --output-format stream-json, accept result as turn completion, parse stdout as guarded JSONL only, capture session id from init, collect assistant message content, break on result, and remove legacy gemini session-id fallback helpers/constants.
- Updated openmcp/openmcp/tests/test_smoke.py gemini assertions to validate stream-json behavior and retryable classification when assistant output exists but no session id is emitted.
- Ran python -m pytest -x -q in openmcp/openmcp via activated .venv; run stopped at pre-existing codex import error: ImportError: cannot import name '_profile_exists' from openmcp.backends.codex.

## Task 2
- Updated openmcp/openmcp/src/openmcp/backends/codex.py to run codex exec --json, parse stdout JSONL with guarded json.loads(...), capture thread.started.thread_id as primary session id, and collect item.completed.item.text for agent_message fallback output.
- Updated session resolution precedence to prefer JSONL-derived session id before regex/session-file fallbacks, while keeping session-file and params.SESSION_ID defensive fallbacks.
- Added _profile_exists in codex backend to restore existing smoke-test import/behavior for codex profile config probing.
- Updated openmcp/openmcp/tests/test_smoke.py codex stream test to assert JSON-mode command usage and JSON event parsing path.
- Ran python -m pytest -x -q in openmcp/openmcp: 34 passed, 4 deselected.

## Task 3
- Updated openmcp/openmcp/src/openmcp/server.py _resolve_model() so backend == "agy" returns "" when no explicit model and no reasoning are provided.
- Updated openmcp/openmcp/tests/test_smoke.py agy-default assertions to reflect that agy no longer consumes OPENMCP_AGY_MODEL_DEFAULT in non-reasoning calls, including gemini->agy routing.
- Ran python -m pytest -x -q in openmcp/openmcp: 34 passed, 4 deselected.
