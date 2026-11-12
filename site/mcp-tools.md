---
layout: default
title: MCP tools
nav_order: 5
---

# MCP tools

The daemon serves MCP at `http://127.0.0.1:8765/mcp`. Nine self-describing MCP tools cover the job lifecycle:

| Tool | Purpose |
| --- | --- |
| `list` | Active and recent jobs, workflows, profiles, and guidance for a project |
| `submit` | Queue a job with a workflow, prompt, and optional profile and session |
| `wait` | Block until a job finishes or asks a question |
| `answer` | Reply to a worker's pending question |
| `cancel` | Stop a queued or running job |
| `retry` | Create a new job from a finished one on the next target |
| `card_create`, `card_move`, `card_list` | Track work on a per-repository board |

Jobs are admitted first in, first out, up to `max_jobs` across all projects. Several jobs in one project can run at once and edit the same checkout. Jobs that share a project, session, workflow, and target run one at a time.

`wait` returns `{job, result}`. Every finished job writes its full text to `result.result_path`; read it when `result.truncated` is true.

## Recovery and Routing

- `retry(job_id)` runs the request again on `result.next_target`, the next healthy target in profile order. `retry(job_id, target=X)` pins a target.
- On `failure_kind` `context_overflow`, submit again with `fresh=true`.
- On `replay_blocked`, the worker already changed files. Inspect the checkout before retrying.
- An open circuit skips a target until its cooldown ends. When no target is available, the error is `targets_unavailable` with `retry_after_s`.
- Errors return `code`, `message`, and `next_action`. `invalid_request` means the arguments did not match the schema or named an unknown target.

The full contract for Coordinator agents is in [`tool-contract.md`](https://github.com/sitien173/refract/blob/main/plugin/skills/coordinating-multi-model-work/references/tool-contract.md).

## Worker questions

Each worker gets `REFRACT_ASK_URL` and `REFRACT_ASK_TOKEN` in its environment. Running `refract ask "<question>"` blocks until the Coordinator calls `answer` or `ask_timeout_s` passes. The worker's tool shell must have `refract` on `PATH`.

Source: [server/README.md](https://github.com/sitien173/refract/blob/main/server/README.md)
