## User Request
Implement plan `job-failover-metadata` (client-routed failover, job result metadata, 3-state circuit breaker). This is Phase 1 of 5.

## Phase
Both test suites pass, and every backend returns a `usage` dict parsed from real captured CLI output.

## Tasks
- task-1: Find the root cause of the flaky web test `src/screens/ProjectDetail.test.jsx > ProjectDetail screen > opens profile editor to create a project override and submits payload with project revision` and fix it. Apply systematic debugging: reproduce, establish the cause with evidence, then fix. No longer timeouts, no retries. Fix the test or the component under test, whichever holds the root cause. Record the cause in `notes.md`. At baseline it failed in 3 of 3 runs, and the first run also failed 2 more tests; make the whole web suite pass 3 consecutive runs.
- task-2: Run each of `claude`, `codex`, `pi`, and `agy` once with a trivial prompt such as `Reply with OK`, using the same structured-output flags the backend module in `server/src/refract/backends/` passes today. Save the raw stdout as JSONL under `server/tests/fixtures/usage/{claude,codex,pi,agy}.jsonl`. Redact session IDs, account identifiers, paths under `$HOME`, and any token- or key-like values; keep event structure and usage numbers intact. Record each exact command in `notes.md`. If a CLI cannot run, stop and report BLOCKED for that backend rather than hand-writing a fixture.
- task-3: Add `usage: dict[str, int | str | None]` defaulting to an empty dict to `BackendResult` (`server/src/refract/backends/__init__.py`) and `DriverResult` (`server/src/refract/drivers.py`), and pass it through `drivers._normalize`. Keys: `model_name`, `input_tokens`, `output_tokens`, `cached_input_tokens`, `context_window_max`, `context_window_used`.
- task-4: In each backend module, parse those keys from the event fields that actually appear in its fixture. A key absent from the fixture stays `None`. Missing or malformed usage must never raise and never change `outcome` or `error_class`. Record a backend-by-key table of verified field paths, or `absent`, in `notes.md`.

## Context
- Design: `docs/plans/job-failover-metadata/DESIGN.md` (sections "Result" and "Testing / Step 0").
- `BackendResult` fields today: `outcome`, `SESSION_ID`, `agent_messages`, `error`, `error_class`. `DriverResult` fields: `outcome`, `session_id`, `text`, `error`, `error_code`. Both are dataclasses; `_normalize` maps `BackendResult` to `DriverResult`.
- Backend stream parsing lives in `server/src/refract/backends/{claude,codex,pi,agy}.py`; tests in `server/tests/test_streaming_backends.py`.
- Web tests run with vitest in `server/web`.

## Files
- `server/web/src/screens/ProjectDetail.test.jsx`, or the component under test if the root cause is in product code
- `server/tests/fixtures/usage/claude.jsonl` (create)
- `server/tests/fixtures/usage/codex.jsonl` (create)
- `server/tests/fixtures/usage/pi.jsonl` (create)
- `server/tests/fixtures/usage/agy.jsonl` (create)
- `server/src/refract/backends/__init__.py`
- `server/src/refract/backends/claude.py`
- `server/src/refract/backends/codex.py`
- `server/src/refract/backends/pi.py`
- `server/src/refract/backends/agy.py`
- `server/src/refract/drivers.py`
- `server/tests/test_streaming_backends.py`
- `docs/plans/job-failover-metadata/phase-01/notes.md` and `journal.md`

## Done When
- `npx vitest run` passes three consecutive runs.
- Four fixture files exist and contain no unredacted session ID, `$HOME` path, or credential.
- Each backend test parses its fixture into the expected `usage` values; a fixture with usage keys removed yields `None` for those keys without raising.
- `DriverResult.usage` carries the parsed dict for all four backends.
- `notes.md` holds a backend-by-key table of verified field paths.
- `cd /home/ngosi/projects/refract/server/web && npx vitest run && npx vitest run && npx vitest run`
- `cd /home/ngosi/projects/refract/server && uv run pytest -q tests/test_streaming_backends.py`
- `cd /home/ngosi/projects/refract/server && uv run pytest -q`

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md

- Edit only the files listed above. Do not touch any other file under `docs/plans/`.
- No Git operations: no commit, reset, restore, stash, or clean.
- Do not read or copy secrets or files under `~/.refract`. Never write credentials into fixtures.
- No parser may read a field name absent from its fixture.
- Test first: write the failing parser test before the parser code.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
