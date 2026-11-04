# Phase 7 notes

Status: complete

Execution mode: direct, per owner 2026-11-04. No coordinator, no Refract jobs, no review gates. TDD with per-step commits.

## Baseline

- HEAD 1eb5d9fe, base ref phase-07/base = 607abd5d.
- PYTEST 768 passed, 15 deselected. PLUGIN pass. LINES 8735.
- `server/web` does not exist. `dashboard.py` mounts only `/ask`.

## TDS source

- `tds` CLI, `@trulioodesign/tds-mcp v1.1.2`. `tds rules` read 2026-11-04.
- Rules that apply: light theme only; semantic tokens only, no hex or core tokens; exact `tds-*` classes; component CSS embedded from `tds component`; sentence case; Inter via `var(--font-family)`.
- Components to use: `tds-data-table` for the job list and targets, `tds-tag` for state and breaker badges, `tds-announcement` for the config error.

## Step plan

- 7A: dashboard. RED tests in `server/tests/test_dashboard.py`: job list; running and finished job detail; targets page with an open circuit and a config error; output polling with `after=N`; `<script>` in a prompt rendered escaped; non-loopback request 403; route list is exactly the four dashboard routes plus `/ask`. GREEN: `dashboard.py` pages with `html.escape`, inline poll JS that stops on a terminal state, CSS vendored to `src/refract/dashboard_static/tds/` and package data in `pyproject.toml`.
- 7B: docs. `README.md` manual migration text for the v3 schema; `server/README.md` dashboard section replacing 'Worker Live Dashboard Streaming'.
- 7C: success check, refs, `plan_impl_ref`, final audit, handover.

## Step 7A: dashboard

### RED

- `server/tests/test_dashboard.py` gained 14 tests: route set, job list, running detail with poll, finished detail without script, prompt escaping, unknown job 404, targets with open circuit and config error, output `after=N`, empty output for a finished job, bad `after` 400, non-loopback client and foreign Host 403 for all four routes.
- The `request` helper now splits the query string from the path.
- RED run: 13 failed, 9 passed. Failures were 404 for missing routes and the route set assertion.

### GREEN

- `test_dashboard.py`: 22 passed.
- PYTEST: 782 passed, 15 deselected. PLUGIN pass. Ruff F diff against baseline: none. LINES 8977.
- `server/web` absent. Route registrations: the four dashboard routes and `/ask` in `dashboard.py`, plus the MCP mount in `server.py`.

### Changes

- `dashboard.py`: `/dashboard`, `/dashboard/jobs/{job_id}`, `/dashboard/jobs/{job_id}/output`, `/dashboard/targets`, all through `_loopback_route`. Every value passes through `html.escape`. No template engine and no new dependency.
- Job list merges jobs across projects, newest first, capped at 200 rows.
- Job detail shows metadata, prompt, result, error and output. Output already on disk renders server side. A 25-line inline script polls only while the job is not terminal and reloads the page once it is.
- The output endpoint reads `streams/<job_id>.jsonl`; seq is the line number, so it survives a daemon restart. It skips a partial last line and returns at most 500 events per call. `next` is the last returned seq, or `after` when nothing is new.
- Targets page shows each target with its breaker state as a tag, open-until time, cooldown, load and probing, plus config health. An invalid config renders a `tds-announcement--error` with the escaped error and source path.
- CSS is inlined in a `<style>` block, per TDS rule 4, so no static route is needed.
- `dashboard_static/tds/`: `tokens.css`, `fonts.css`, `data-table.css`, `tag.css`, `announcement.css`.

### TDS source detail

- Component CSS is verbatim from `tds component data-table`, `tds component tag` and `tds component announcement`.
- `tokens.css` holds the RULE 2 semantic token block from `tds rules`, preceded by the 48 core tokens that the semantic block and the component CSS reference, with values from `tds tokens all`.
- `fonts.css` sets body, nav, heading and `pre` typography from semantic tokens only. TDS ships no font files, so Inter falls back to the system sans-serif face.

### Deviations

- No `pyproject.toml` change. Hatchling packages every file under `src/refract`. A wheel built with the cached hatchling contained all five CSS files under `refract/dashboard_static/tds/`.
- The core tokens in `tokens.css` exist only because the vendored component CSS and semantic tokens reference them. Dashboard code uses semantic tokens only.

### Debt

- The output endpoint reads the whole stream file per poll. It is bounded only by the existing stream size cap debt.

## Step 7B: docs and orphaned stream tail

### RED

- `test_storage_v3.py`: the stream test now asserts `Database` has no `stream_tail`. It failed before the change.

### GREEN

- PYTEST 782 passed, 15 deselected. PLUGIN pass. Ruff F diff: none. LINES 8958.

### Changes

- `README.md` "Manual state migration": replaced the schema 16 text. It now states schema 18, no migration of older databases, the rename to `refract.db.v2.bak` with sidecars, refusal when a `.v2.bak` exists or the schema is newer, and restore by renaming back.
- `server/README.md`: "Worker Live Dashboard Streaming" is now "Dashboard and Live Output", with the three pages, the output endpoint and loopback access. The storage bullet says the dashboard reads the stream file.
- `database.py`: removed the in-memory stream tail, `STREAM_TAIL_EVENTS`, `stream_tail` and its lock. 7A made the stream file the only read path, which left the tail with no production caller.

### Deviations

- Removing the memory tail is outside the Phase 7 task list. It was orphaned by 7A.

## Step 7C: success check and final audit

### Success check at f33c53e2

- LINES: 8958, at most 9000. Plan start was 13,484.
- PYTEST: 782 passed, 15 deselected.
- PLUGIN: `test-session-start.sh`, `test-contracts.sh` and `test-stats.sh` pass.
- Six-tool contract: `tests/test_mcp_schema_contract.py`, `test_server.py::test_tool_surface_lists_exact_v3_contract` and `test_server.py::test_tool_schema_limits_and_annotations_are_v3`: 11 passed.
- `server/web` absent. No `result_offset`, `next_offset` or `langfuse` in `server/src/refract`.
- HTTP routes: four dashboard routes and `/ask` from `register_dashboard_routes`, plus the MCP mount at `/`.

### DESIGN success criteria

| Criterion | Evidence |
|---|---|
| 1. Exactly six MCP tools | `test_tool_surface_lists_exact_v3_contract` |
| 2. `submit` and `wait` suffice; no paging | contract tests; no paging fields in source |
| 3. At most 9,000 lines; `server/web` gone | LINES 8958; directory absent |
| 4. Each audit defect fixed with a test | table below |
| 5. Full suite passes at each checkpoint | PYTEST recorded in every phase's notes |

### Errors and Edge Cases audit

| Case | Test |
|---|---|
| Codex exits 0 without an agent message | `test_codex_backend.py::test_no_output_is_no_agent_messages` |
| No exact Codex session match | `test_resume_without_exact_session_source_stores_no_session_id` |
| Resumed session fails with `context_overflow` | `test_resumed_context_overflow_fails_without_in_run_recovery` |
| Resume fails after tool activity | `test_resumed_failure_after_tool_activity_is_replay_blocked` |
| Daemon crash leaves worker groups | `test_restart_kills_worker_group_of_interrupted_job`, `test_restart_leaves_group_without_matching_job_id` |
| Answer races the ask timeout | `test_answer_after_question_deadline_is_rejected` |
| `refract ask` client hang | `test_ask_client_timeout_is_ask_timeout_plus_ten` |
| Revoked ask tokens accumulate | `test_revoked_tokens_are_not_retained` |
| Grandchild holds stdout | `test_grandchild_holding_stdout_does_not_stall_after_parent_exit` |
| Non-UTF-8 output | `test_non_utf8_output_does_not_truncate_later_lines` |
| Stdin write failure | `test_stdin_write_failure_is_reported_as_request_error` |
| Parser or emitter exception | `test_parser_exception_fails_attempt_and_kills_group` |
| Sticky target removed or circuit open | `test_sticky_target_removed_from_profile_falls_back_to_profile_order`, `test_success_records_sticky_target_and_next_submit_prefers_it` |
| `retry(target=X)` with unknown target | `test_retry_with_unknown_target_lists_profile_targets` |
| Tool activity then failure | `test_resumed_failure_after_tool_activity_is_replay_blocked` |
| Result over the response cap | `test_long_result_is_truncated_with_full_text_at_result_path` |
| `submit` path not in a Git repository | `test_submit_outside_git_is_invalid_path` |

### Reviewer checklist, self-checked

- Every interpolated value in `dashboard.py` passes through `html.escape`, except tag and table markup built from escaped parts and the constant `yes` or `no`.
- Every `tds-*` class used in `dashboard.py` exists in the vendored CSS. `fonts.css` uses semantic tokens only and contains no hex color.
- The poll script is emitted only for non-terminal jobs and stops when `terminal` is true.

### Not done by this plan

- The manual smoke run per real CLI and the cutover belong to the owner after consolidation, per PLAN.md "After Consolidation".
