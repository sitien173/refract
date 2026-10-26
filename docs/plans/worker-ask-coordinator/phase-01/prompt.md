## User Request
Let a running worker ask the coordinator a question and continue the same job
with the answer. Workers will run `refract ask "<question>"`, which calls a
loopback HTTP route on the Refract daemon. Full design:
`/home/ngosi/projects/refract/docs/plans/worker-ask-coordinator/DESIGN.md`.

## Phase
Phase 1 of 3: server-side ask channel. A worker subprocess receives the ask
env vars, and an HTTP client holding a valid job token can post a question
that blocks until an in-process answer call or the timeout. No MCP tool
changes in this phase; `job_answer` and `job_wait` changes are Phase 2. The
`refract ask` CLI is Phase 3.

## Tasks
- task-1: Create `server/src/refract/ask.py`: an in-memory registry that issues a `secrets`-generated token bound to a job ID, revokes it, holds at most one pending question per job, delivers an answer, and releases a waiter on timeout or cancel with the exact text `No answer from coordinator; use your best judgment or end with BLOCKED.`
- task-2: Add `ask_timeout_s` to `DaemonConfig` in `config.py` with a positive integer default and validation that rejects booleans, non-integers, and values below 1, following the existing `timeout_s` validation style.
- task-3: Add `POST /ask` in `dashboard.py` via the existing `_loopback_route`. Body `{"token": str, "question": str}`. 200 with `{"answer": str}` on answer or timeout; 403 for unknown, revoked, or wrong-job token; 409 when a question is already pending; 400 for a malformed body or empty question. The wait must not block the event loop.
- task-4: In the execution path, issue a token when a job attempt starts and revoke it when the attempt ends, including on failure and cancel. Pass `REFRACT_ASK_URL` (`http://<daemon host>:<daemon port>/ask`) and `REFRACT_ASK_TOKEN` to the worker subprocess by merging them into the inherited `os.environ` at `subprocess.Popen`. Cancelling a job releases any pending ask with the no-answer text.

## Context
- `server/src/refract/backends/__init__.py:12` `BackendParams` holds per-run inputs; add an env mapping field there.
- `server/src/refract/drivers.py:274` builds `BackendParams`.
- `server/src/refract/backends/_shell.py:153` is the only `subprocess.Popen`; `_shell.py:213` builds kwargs for the stream helper from `params`. Each backend in `backends/{codex,claude,agy,pi}.py` wraps `stream_shell_command_lines` with its own keyword list; thread the env argument through each.
- `server/src/refract/execution.py:84` `execute` and `:155` `_execute_attempt` run one attempt and own the cancel event.
- `server/src/refract/dashboard.py:461` `_loopback_route` guards loopback-only routes; `DashboardState.runtime` at `dashboard.py:61` gives routes access to the runtime.
- `server/src/refract/runtime.py:64` `Runtime` owns job lifecycle and `cancel` at `:417`. The registry instance should be owned by `Runtime` so Phase 2 can add `job_answer` and `job_wait` wake-ups.
- `server/src/refract/config.py:78` `DaemonConfig`; `host` and `port` fields give the daemon address.
- DB schema stays v15. Do not add tables or columns.

## Files
- `server/src/refract/ask.py` (create)
- `server/src/refract/config.py`
- `server/src/refract/dashboard.py`
- `server/src/refract/backends/__init__.py`
- `server/src/refract/backends/_shell.py`
- `server/src/refract/backends/codex.py`
- `server/src/refract/backends/claude.py`
- `server/src/refract/backends/agy.py`
- `server/src/refract/backends/pi.py`
- `server/src/refract/drivers.py`
- `server/src/refract/execution.py`
- `server/src/refract/runtime.py`
- `server/tests/test_ask.py` (create)
- `server/tests/test_dashboard.py`
- `server/tests/test_config.py`
- `docs/plans/worker-ask-coordinator/phase-01/notes.md`
- `docs/plans/worker-ask-coordinator/phase-01/journal.md`

Out of scope: any other file, `~/.refract/`, credentials, `server.py` MCP tools, `cli.py`.

## Done When
- A test proves the worker subprocess environment contains `REFRACT_ASK_URL` and `REFRACT_ASK_TOKEN`, and that the token value is absent from stream events and log records.
- Tests cover: valid token answered, wrong-job token 403, revoked token 403, second pending question 409, timeout returns the no-answer text, cancel releases with the no-answer text, token revoked after the attempt ends.
- Config tests cover the `ask_timeout_s` default and invalid values.
- The MCP tool list is unchanged.
- `cd /home/ngosi/projects/refract/server && uv run pytest -q` passes.
- `cd /home/ngosi/projects/refract && bash plugin/tests/run.sh` passes.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
- Use test-driven development: write each failing test first, then the code.
- No new dependencies. Standard library and existing dependencies only.
- Never log, emit, or return the token except in the subprocess env.
- Compare tokens with `secrets.compare_digest`.
- Match existing code style; do not refactor unrelated code.
- Do not run git commands that change state: no commit, reset, stash, checkout, or clean.

## Remaining Review Fixes

Fix cycle 2 is limited to these findings:

1. Bound each ask below the finite worker workflow timeout. Account for time already elapsed before a late question. Preserve workflow `timeout_s=0` as unlimited. Keep configured ask timeout as the upper bound. Test normal and late questions, short finite timeouts, and unlimited workflows.
2. Revoke the job token immediately during Runtime cancellation, releasing any pending request with the exact no-answer text. Prove the cancelled token cannot register another question before worker termination.
3. Reject non-ASCII unknown tokens and wrong-job identifiers as authentication failures, never uncaught `TypeError`. The route must return 403. Keep constant-time token comparisons.
4. Replace the ID-keyed BackendParams environment map with a normal dataclass `env` field excluded from repr. Update the exact field set assertion in `server/tests/test_smoke.py`, now explicitly allowed for this fix. Preserve env propagation and token secrecy.

Diagnose and write failing regressions first. Append exact RED and GREEN evidence to notes. Rerun both complete verification commands. Do not change the MCP tool list or CLI. Do not mutate Git. Append ERP to the journal.

## User-authorized Fix Cycle 3

The user authorized one additional fix cycle. This supersedes the completed Fix 2 batch above.

Remaining blocker: strict UTF-8 encoding of JSON authentication identifiers raises `UnicodeEncodeError` on escaped lone surrogates instead of HTTP 403. Reproduce with the real ASGI route for a surrogate token and a surrogate wrong-job identifier. Add failing regression tests first. Reject unsupported authentication identifiers safely while preserving constant-time comparisons for valid token candidates. Keep the fix minimal.

Allowed changes for this cycle only:
- `server/src/refract/ask.py`
- `server/tests/test_dashboard.py`
- `server/tests/test_ask.py` if needed
- this phase's `notes.md` and `journal.md`

All existing dirty changes belong to prior Phase 1 implementation and must be preserved. Do not redo Fix 2 or modify other files. Record reproduction, root cause, exact RED and GREEN commands and outcomes. Rerun both complete verification commands. Do not mutate Git or handover. Return ERP and append it to the journal.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
