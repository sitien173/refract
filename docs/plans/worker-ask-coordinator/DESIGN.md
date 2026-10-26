# Worker Ask Coordinator Design

**Status:** Confirmed 2026-10-26
**Consultation:** skipped - three consult attempts failed on two targets; user then waived consultation

## Purpose

Let a running worker ask the coordinator a question and continue the same job
with the answer. This replaces most `BLOCKED` round trips, which currently end
the job and require a resumed job.

## Users and Success Criteria

Users: worker agents on the codex, claude, agy, and pi backends; the
coordinator model that answers.

Success criteria:

- On each of the four backends, a worker runs `refract ask "<question>"`.
- `job_wait` returns early with the pending question.
- The coordinator calls `job_answer(job_id, answer)`.
- The worker receives the answer on stdout and finishes in the same job.
- An unanswered question times out after a configurable period; the command
  prints a no-answer message and the job keeps running.

## Constraints and Non-Goals

Constraints:

- Loopback only.
- A per-job secret token; a job can ask and be answered only for itself.
- Works with `isolated` and `read_only` targets, subject to the sandbox open
  question below.
- No new dependency.

Non-goals:

- Proxying coordinator MCP servers to workers.
- Notify or approval tools.
- Answering from the dashboard.
- More than one pending question per job.

## Chosen Approach

A: a `refract ask` shell command. Refract injects `REFRACT_ASK_URL` and a
per-job `REFRACT_ASK_TOKEN` into the worker subprocess environment. The command
calls a loopback HTTP route on the existing server and blocks until an answer
or timeout.

- Rejected B, per-job native MCP endpoint: agy and pi expose MCP only through
  persistent config, which is racy across concurrent jobs, and isolated pi
  rejects explicit extensions.
- Rejected C, hybrid: two channels to build, secure, and test for one tool.

## Architecture and Data Flow

Components:

- `server/src/refract/cli.py`: new `ask` subcommand. Reads the two env vars,
  posts the question, blocks on the response, prints the answer or the
  no-answer message. Exits non-zero only when the env vars are missing or the
  server is unreachable.
- `server/src/refract/dashboard.py`: new route `POST /ask` built with the
  existing `_loopback_route` guard at `dashboard.py:461`. Validates the token
  against the job, records the question, and waits for the answer or timeout.
- Job execution path in `execution.py` and `backends/_shell.py`: generate the
  token at job start, pass both env vars to the worker subprocess, and revoke
  the token when the job ends.
- `server/src/refract/server.py`: new MCP tool `job_answer(job_id, answer)`.
  `job_wait` returns early when a question is pending.
- Worker contract `plugin/shared/worker-contract.md`: one short section telling
  workers when and how to run `refract ask`.

Flow:

1. Job starts. Server creates token T bound to job J and injects the env vars.
2. Worker runs `refract ask "Q"`. The CLI posts `{token: T, question: Q}`.
3. Server resolves T to J, rejects a second pending question for J, stores Q
   as pending, and wakes any `job_wait(J)` call.
4. `job_wait(J)` returns with the job still `running` and a new
   `result.pending_question` field holding `{question_id, text}`.
5. Coordinator calls `job_answer(J, answer)`. Server stores the answer, clears
   the pending state, and releases the blocked HTTP request.
6. CLI prints the answer. Worker continues. Coordinator calls `job_wait` again.

Pending-question state is held in memory, keyed by job. The question and
answer are also appended to the job's event stream so they appear in the
transcript and final result.

## Errors and Edge Cases

| Case | Behavior |
|---|---|
| Timeout, default configurable in `~/.refract/config.toml` | Route returns the no-answer message: "No answer from coordinator; use your best judgment or end with BLOCKED." Pending state cleared. |
| Unknown, revoked, or wrong-job token | 403. CLI prints an error and exits non-zero. |
| Second question while one is pending | 409. CLI tells the worker to wait for the first answer. |
| `job_answer` with no pending question | `invalid_state` error. |
| `job_answer` on a terminal job | `invalid_state` error. |
| Job cancelled while a question is pending | Blocked request released with the no-answer message; token revoked. |
| Daemon restart while a question is pending | Worker subprocess ends with the daemon, so in-memory state loss is acceptable. Job recovery follows existing rules. |
| Server unreachable from a sandboxed worker | CLI exits non-zero with a clear message; worker falls back to `BLOCKED`. |

Token handling: the token is never written to the prompt, stream events,
logs, or the dashboard. It lives only in the subprocess env and server memory.

## Migration

No DB schema change; pending state is in memory and Q/A use the existing
event stream. Schema stays v15.

MCP contract change: the tool set grows from seven to eight with `job_answer`,
and `job_wait` gains `result.pending_question`. Update
`plugin/skills/coordinating-multi-model-work/references/tool-contract.md`, the
Gate 2 outcome table, and `server/README.md`.

## Testing

- Unit: token creation, binding, revocation; route auth for valid, wrong-job,
  and revoked tokens; single-pending rule; timeout path; cancel path.
- Unit: `job_wait` early return with `pending_question`; `job_answer` happy
  path and both `invalid_state` cases.
- Unit: env injection reaches the subprocess for each backend; token absent
  from stream events and logs.
- CLI: `refract ask` with missing env, unreachable server, answer, timeout.
- Manual smoke: one real job per backend, codex, claude, agy, pi, on both a
  normal and a `read_only` target.

## Risks and Open Questions

- Open: do `read_only` or sandboxed targets allow the worker to run a shell
  command and reach 127.0.0.1? Must be verified per backend in phase 1. If a
  backend blocks it, that backend degrades to the current `BLOCKED` flow.
- Open: do the backend CLIs pass the parent environment through to tool
  shells? Verify per backend in phase 1.
- Risk: backend subprocess `timeout_s` keeps running while the worker is
  blocked. The ask timeout must stay below it.
- Risk: the `refract` executable may not be on PATH inside the worker. Inject
  an absolute path, or document `REFRACT_ASK_URL` with a curl fallback.
- Risk: the coordinator skill must handle `pending_question`, or questions
  will only ever time out.
