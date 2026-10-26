# Worker Ask Coordinator Plan

**Design:** `docs/plans/worker-ask-coordinator/DESIGN.md`
**Base:** `refs/plans/worker-ask-coordinator/base`
**Commit:** `feat(server): let workers ask the coordinator mid-job via refract ask`

Baseline at `base`: `uv run pytest -q` in `server/` reports 584 passed,
3 deselected; `bash plugin/tests/run.sh` passes with 3 warnings.

### Phase 1: Server-side ask channel

**Task Guide Input:** Non-UI server implementation in the Python Refract
daemon. Add a per-job ask token registry and single pending-question state, a
loopback `POST /ask` HTTP route that blocks until answered or timed out, an
`ask_timeout_s` daemon config field, and injection of `REFRACT_ASK_URL` and
`REFRACT_ASK_TOKEN` into every worker subprocess environment. Server tests
only; no MCP tool changes in this phase.
**Goal:** A worker subprocess receives ask env vars, and an HTTP client holding
a valid job token can post a question that blocks until an in-process answer
call or the timeout.
**Files:**
- Create: `server/src/refract/ask.py`
- Modify: `server/src/refract/config.py`
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/src/refract/backends/__init__.py`
- Modify: `server/src/refract/backends/_shell.py`
- Modify: `server/src/refract/execution.py`
- Modify: `server/src/refract/runtime.py`
- Create: `server/tests/test_ask.py`
- Modify: `server/tests/test_dashboard.py`
- Modify: `server/tests/test_config.py`
**Tasks:**
1. In `ask.py`, implement an in-memory registry: issue a random token bound
   to a job ID at job start, revoke it at job end, hold at most one pending
   question per job, deliver an answer, release on timeout or cancel with the
   fixed no-answer message from the design.
2. Add `ask_timeout_s` to `DaemonConfig` with a positive integer default and
   validation in `config.py`.
3. Add `POST /ask` in `dashboard.py` using `_loopback_route`. Return 403 for an
   unknown, revoked, or wrong-job token and 409 for a second pending question.
4. Issue and revoke tokens in the execution path, and pass both env vars to
   `subprocess.Popen` in `backends/_shell.py` by merging into the inherited
   environment.
**Acceptance Criteria:**
- A test proves the worker subprocess environment contains both env vars and
  the token is absent from stream events and log records.
- Tests cover valid token, wrong-job token, revoked token, 409 on a second
  question, answer delivery, timeout message, and release on cancel.
- No change to the MCP tool list; DB schema stays v15.
**Reviewer Checklist:**
- Token generated with `secrets`, compared in constant time, never logged.
- Route is loopback-only through the existing guard.
- Ask timeout is checked against the workflow `timeout_s` so it cannot
  outlive the subprocess silently.
- Blocking wait in the route does not block the event loop.
**Verification Checks:**
- `cd server && uv run pytest -q`
- `bash plugin/tests/run.sh`

### Phase 2: Coordinator MCP contract

**Task Guide Input:** Non-UI server implementation in the Python Refract
daemon and its contract docs. Add the MCP tool `job_answer(job_id, answer)`,
make `job_wait` return early while a job is running and has a pending
question with a `result.pending_question` field `{question_id, text}`, and
update every place that pins the tool list to seven tools.
**Goal:** A coordinator sees pending questions through `job_wait` and answers
them through `job_answer`.
**Files:**
- Modify: `server/src/refract/server.py`
- Modify: `server/src/refract/runtime.py`
- Modify: `server/src/refract/ask.py`
- Modify: `server/tests/test_server.py`
- Modify: `server/tests/test_mcp_schema_contract.py`
- Modify: `plugin/tests/test-contracts.sh`
- Modify: `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`
- Modify: `README.md`
- Modify: `server/README.md`
**Tasks:**
1. Add `job_answer` to `server.py` and `Runtime`, returning `invalid_state`
   when no question is pending or the job is terminal.
2. Make `Runtime.wait` and `job_wait` wake on a new pending question and
   return the running job with `result.pending_question`; keep all existing
   terminal and timeout behavior unchanged.
3. Update the seven-tool assertions and docs to eight tools and document
   `pending_question` and `job_answer`.
**Acceptance Criteria:**
- Tests show `job_wait` returning early with `pending_question`, and a
  `job_answer` call releasing the blocked ask with the given text.
- Tests show both `invalid_state` cases.
- `plugin/tests/test-contracts.sh` asserts the eight-tool list.
- Responses stay within the existing size bounds.
**Reviewer Checklist:**
- No regression in nonterminal `job_wait` semantics for jobs without a
  question.
- Answer text is treated as data and size-bounded.
- Docs and tests name the same tool list.
**Verification Checks:**
- `cd server && uv run pytest -q`
- `bash plugin/tests/run.sh`

### Phase 3: Worker command and coordinator workflow

**Task Guide Input:** Non-UI implementation across the Refract CLI, shared
worker contract, and coordinator skill. Add the `refract ask` subcommand that
reads the env vars, posts the question, blocks, and prints the answer; tell
workers when to use it; teach the coordinator skill to answer
`pending_question` via `job_answer`; add live-marked per-backend probes that
resolve the design's sandbox and env passthrough open questions.
**Goal:** Workers on all four backends can run `refract ask`, and the
coordinator workflow answers them.
**Files:**
- Modify: `server/src/refract/cli.py`
- Modify: `server/tests/test_smoke.py`
- Modify: `server/tests/test_live_backends.py`
- Modify: `server/CLI_ARGUMENTS.md`
- Modify: `plugin/shared/worker-contract.md`
- Modify: `plugin/skills/coordinating-multi-model-work/SKILL.md`
**Tasks:**
1. Add the `ask` subcommand in `cli.py`: non-zero exit with a clear message
   when env vars are missing or the server is unreachable; print the answer or
   no-answer message otherwise. Use only the standard library for HTTP.
2. Add a short worker-contract section on when to run `refract ask` and to
   fall back to `BLOCKED` when it fails.
3. Add a Gate 2 rule in the coordinator skill: on `pending_question`, answer
   with `job_answer`, then call `job_wait` again.
4. Add `live`-marked tests in `test_live_backends.py`, one per backend on a
   normal and a `read_only` target, that check env passthrough and loopback
   reachability; record per-backend results in `server/CLI_ARGUMENTS.md`.
**Acceptance Criteria:**
- CLI tests cover missing env, unreachable server, answer, and timeout.
- Live probe results for codex, claude, agy, and pi are recorded, including
  any backend that must fall back to `BLOCKED`.
- The coordinator skill and worker contract describe the same flow.
**Reviewer Checklist:**
- The worker-contract text cannot cause workers to ask for routine decisions
  the plan already answers.
- No token or URL is written into prompts.
- Live tests are excluded from the default run by the existing `live` marker.
**Verification Checks:**
- `cd server && uv run pytest -q`
- `bash plugin/tests/run.sh`
