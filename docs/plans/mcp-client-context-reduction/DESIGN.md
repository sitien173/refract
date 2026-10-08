# MCP Client Context Reduction — Design

## Purpose

Reduce the context an MCP client spends on OpenMCP. Two costs dominate and
neither is the tool surface.

The first is the jobs resource. `openmcp://projects/{project_id}/jobs` returns
every job a project has ever run, with full `result_text`, unpaginated. Measured
on 2026-08-29 against `~/.openmcp/openmcp.db`: 1135 jobs total, 370 on the
busiest project, ~594 KB of result text for that project alone. The
`coordinating-multi-model-work` skill instructs the client to read this resource
at every setup.

The second is the coordinator skill itself. `SKILL.md` is 10.5 KB and loads on
every session through the SessionStart hook, including sessions that match its
own `When to Skip Coordination` rule and never route a job. `Gate 3: Review` is
3237 B of it and is unreachable until an implementation job is terminal.

## Measurements

Taken 2026-08-29. These set the baseline for acceptance.

| Surface | Measurement |
|---|---|
| `projects/{id}/jobs`, busiest project | 370 jobs, ~594 KB result text |
| `result_text` per job | max 24225 B, mean 1629 B, total 1848955 B |
| `jobs/{id}/events` | max 25 events/job, mean 5.34, 2-336 B each |
| Resource templates | 11 registered, 5 referenced by the skill |
| `SKILL.md` | 10.5 KB, `Gate 3` 3237 B |

Events are not a problem. Worst case is roughly 2 KB per job. The resource is
removed for surface reasons, not payload reasons.

## Decisions

- Bound `openmcp://projects/{project_id}/jobs` to one fixed slim shape. No
  `detail` or `limit` query parameter, because an opt-out flag is a footgun the
  agent can trip.
- Split the payload into `active`, `recent`, and `truncated`. `active` is every
  non-terminal job and is never capped, because the coordinator must not miss a
  running job. `recent` is the 10 most recent terminal jobs by `updated_at`.
  `truncated` is a count of omitted terminal jobs, not a list of identifiers.
- Drop `result` from the list view entirely. Full detail stays on
  `openmcp://jobs/{job_id}`.
- Remove five resource templates: `projects/{project_id}`,
  `jobs/{job_id}/events`, `contexts/{project_id}/{context_key}`, `profiles`,
  and `targets`.
- Keep `projects/{project_id}/context_instructions`. It is the only read-back
  path for `context_init`, which otherwise has a write path and no read path.
- Slim at the resource layer only. `database.jobs()`, `database.events()`,
  `database.context()`, and `runtime.targets()` keep full fidelity.
- Keep `job_wait` returning full `result.text`. It carries the worker's ERP
  report at a mean of 1629 B; truncating it would break the gate it serves.
- Move the `Gate 3` body out of `SKILL.md` into a reference loaded at review
  time. Preserve the text rather than rewriting it.
- Document `context_init` in `SKILL.md` without naming any backend, flag, or
  file. Provider identity stays private.
- Bump the plugin to `10.2.0`, since the skill contract changes.

## Rejected alternatives

### Opt-in detail flag on the jobs resource

`?detail=full` or `?limit=N` restoring the current payload. Rejected because the
default is only as good as the discipline of every future caller, and a single
`detail=full` re-imports 594 KB.

### Filter the jobs resource by `context_key`

Naturally bounded per plan, but a setup-time reconcile happens before a plan is
chosen and still needs a keyless fallback. That fallback is the slim shape, so
the filter adds a parameter without removing a case.

### Truncate `result.text` above a threshold

Rejected. The mean is 1629 B and the peak is 24 KB. The saving is small and the
failure mode, a silently clipped worker report, is severe.

### Compress prose across all skill sections

Rejected for this change. Rewriting instruction text risks shifting agent
behaviour in ways the contract test cannot detect.

## Section A — Resource surface (`src/openmcp/server.py`)

Remove `project_resource`, `job_events_resource`, `context_resource`,
`targets_resource`, and `profiles_resource`, and drop them from `__all__`.

Six templates remain:

- `openmcp://projects{?scope}`
- `openmcp://projects/{project_id}/jobs`
- `openmcp://projects/{project_id}/profiles`
- `openmcp://projects/{project_id}/context_instructions`
- `openmcp://jobs/{job_id}`
- `openmcp://workflows/{project_id}`

The unbuilt web dashboard plan specifies its own `@mcp.custom_route` endpoints
reading runtime and database methods directly, so removing these MCP resources
does not block it.

## Section B — Jobs payload (`src/openmcp/models.py`, `server.py`)

Add `JobSummary` with `id`, `workflow`, `profile`, `state`, `context_key`,
`attempts`, and `updated_at`. No `target_id`, `result`, `created_at`, or
`project_id`; execution identity stays internal and the caller supplied the
project.

`project_jobs_resource` returns:

```json
{
  "active": [{"id": "...", "workflow": "implement", "state": "running",
              "profile": "...", "context_key": "...", "attempts": 1,
              "updated_at": "..."}],
  "recent": [{"id": "...", "workflow": "review", "state": "succeeded", "...": "..."}],
  "truncated": 364
}
```

`active` holds every job whose state is not in `TERMINAL_STATES`. `recent` holds
the 10 most recent terminal jobs ordered by `updated_at` descending.
`truncated` is the count of terminal jobs omitted from `recent`.

`_json` replaces `indent=2` with `separators=(",", ":")`.

## Section C — Coordinator skill (`superpowers-ccg`)

`references/tool-contract.md`:

- Resource list drops to the six above.
- Add the `active` / `recent` / `truncated` shape so the coordinator does not
  probe for it.
- Add the missing `context_init` row to the Tools table and the
  `context_instructions` resource to the Resources list. Both are present in
  `server.py` and absent from the contract; this is a pre-existing defect
  corrected here because the same list is being edited.

`SKILL.md`:

- `Setup and Resume` step 4 reconciles against `active`. `recent` and
  `truncated` are context, not a work queue. Fetch `openmcp://jobs/{job_id}`
  only when a specific result is needed.
- New short section after `Setup and Resume` documenting `context_init`:
  one instruction per `(project_id, workflow)` pair; empty `instruction` clears
  that pair; stored in the OpenMCP database and persistent across jobs and
  sessions until cleared; delivered to the worker through its harness context
  mechanism, additively, never through the job prompt and never shadowing the
  repository's own context files; read back without writing through
  `openmcp://projects/{project_id}/context_instructions`.
- `Gate 3: Review` reduces to a stub retaining the trigger condition, that a
  spec failure blocks quality review, that correctness and security findings
  force `FAIL`, that review runs against a read-only target and makes no commit,
  both required output blocks verbatim, and a direction to load
  `references/review.md`.

`references/review.md`, new: the spec verification steps, the quality review
scoping rules, the two-cycle review-fix loop, and the finalize checklist
including backlog debt filing.

`skills/executing-plans/SKILL.md` line 16 reads the same jobs resource and moves
to the new shape.

Net `SKILL.md` is roughly 7.7 KB: 10.5 KB less the 3237 B `Gate 3` body, plus
about 400 to 500 B for the `context_init` section.

Prompt-size note. Any fixed per-project preamble currently repeated inside job
prompts can move to `context_init` once and stop being re-sent on every
submission. The existing session resume rule already keeps follow-up prompts
thin; this covers the remaining fixed preamble.

## Compatibility and migration

No database migration. This is a read-layer change; stored rows are untouched
and `database.jobs()` still returns full `JobView` rows.

No API versioning. The MCP client is the only consumer of these resources today,
confirmed by search across both repositories.

The daemon must restart and the MCP client must reconnect before the new
template list is visible.

`.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` both move to
`10.2.0`, and the `ccg-shared-version` marker in all six `shared/*.md` files
moves with them. `tests/test-contracts.sh` enforces all three conditions.

## Testing

`tests/test_server.py`:

- Line 15 imports `profiles_resource` and `targets_resource`; both are removed.
- `test_runtime_resources_use_v2_templates_and_context` at line 174 asserts
  `openmcp://targets{?scope}` and `openmcp://profiles{?scope}` are present and
  calls the removed functions at lines 191-192. Rewrite it to assert the six
  surviving templates are present and the five removed ones are absent.

New coverage:

- `active` contains every non-terminal job with no cap.
- `recent` caps at 10 and orders by `updated_at` descending.
- `truncated` counts omitted terminal jobs and is 0 when none are omitted.
- `JobSummary` exposes no `result` field.
- `openmcp://jobs/{job_id}` still returns full `result.text`.
- `_json` emits no indentation.

`tests/test-contracts.sh` in `superpowers-ccg`:

- Three assertions pin `Accepted debt must never be lost`, `Blocking findings
  are never filed`, and `Filing a row never creates its own commit` to
  `SKILL.md`. All three move with the finalize block; repoint them at
  `references/review.md`.
- Add a line-count cap for `references/review.md`, matching the existing caps of
  265 lines on `SKILL.md` and 90 on `tool-contract.md`.
- The provider-identity guard at line 47 greps `skills/` for `\bcodex\b` and
  `\bagy\b`. The `context_init` documentation must name no backend, flag, or
  generated filename.

## Verification commands

```
cd /home/ngosi/projects/openmcp && uv sync --all-extras --frozen && uv run pytest && uv build
cd /home/ngosi/projects/superpowers-ccg && bash tests/run.sh
```

## Acceptance

- `openmcp://projects/{project_id}/jobs` on the busiest project returns under
  4 KB, down from ~594 KB.
- The client sees 6 resource templates, down from 11.
- No resource or tool response exposes target or provider identity.
- `SKILL.md` is at or under 7.9 KB and still passes every contract assertion.
- Both verification commands pass.
