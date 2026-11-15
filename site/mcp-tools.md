---
layout: default
title: MCP tools
nav_order: 5
---

# MCP tools

The daemon serves MCP at `http://127.0.0.1:8765/mcp`. Nine self-describing MCP tools cover the job lifecycle:

| Tool | Purpose |
| --- | --- |
| `submit` | Queue a job with a workflow and prompt, or pass `from_job` to copy a finished job. With `from_job`, only `target` and `fresh` may be set. |
| `get` | Read a job without waiting: its result, pending question, and attempts |
| `wait` | Block until any of 1 to 16 listed `job_ids` finishes or asks a question |
| `cancel` | Stop a queued or running job; returns `cancel_status` |
| `answer` | Reply to a worker's pending question |
| `list` | Active and recent jobs, workflows, profiles, and guidance for a project |
| `card_create`, `card_move`, `card_list` | Track work on a per-repository board |

Jobs are admitted first in, first out, up to `max_jobs` across all projects. Several jobs in one project can run at once and edit the same checkout. Jobs that share a project, session, workflow, and target run one at a time.

`wait` and `get` return `{job, result, truncated, result_path, pending_question, failure_kind, next_target, model, duration_ms, tokens}`; `get` adds `attempts`. A response stays below 9,000 UTF-8 bytes. A longer result is truncated and carries `truncated: true` and `result_path`; read the full text from that file. `cancel` returns `{job, cancel_status}`: `terminated` for a queued job, `requested` for a running job, and `already_terminal` for a finished job, which is never changed.

## Recovery and Routing

- `submit(from_job=X)` runs a finished job again on `next_target`, the next healthy target in profile order after the source job's last attempt. `submit(from_job=X, target=Y)` pins a target. The source job must be terminal and not pruned. `fresh` defaults to null. Without `from_job`, null means false. With `from_job`, omitting `fresh` copies the source job's value, and an explicit `fresh=false` overrides a source job that used `fresh=true`.
- When an attempt is `replay_safe`, the server retries on the same target when `retry.codes` or `retry.patterns` match, opens a fresh session on `context_overflow`, and falls back to the next target, all inside the same job. Each step is one `attempts` row with `reason` `retry`, `fresh_session`, or `fallback`.
- An attempt is `replay_safe` only when the target streams events, no `tool.started` event occurred, and the worker asked no question. A failed attempt that is not `replay_safe` is not recovered automatically, so the job ends failed; inspect the checkout before calling `submit(from_job=...)`. An attempt that is not `replay_safe` can still succeed.
- After a daemon restart, `running` jobs are `interrupted`, `open` questions are `expired`, and `queued` jobs resume. Nothing re-runs by itself.
- An open circuit skips a target until its cooldown ends. When no target is available, the error is `targets_unavailable` with `retry_after_s`.
- Errors return `code`, `message`, and `next_action`. `invalid_request` means the arguments did not match the schema or named an unknown target.

The full contract for Coordinator agents is in [`tool-contract.md`](https://github.com/sitien173/refract/blob/main/plugin/skills/coordinating-multi-model-work/references/tool-contract.md).

## Worker questions

Each worker gets `REFRACT_ASK_URL` and `REFRACT_ASK_TOKEN` in its environment. Running `refract ask "<question>"` blocks until the Coordinator calls `answer` or `ask_timeout_s` passes. The worker's tool shell must have `refract` on `PATH`.

Source: [server/README.md](https://github.com/sitien173/refract/blob/main/server/README.md)
