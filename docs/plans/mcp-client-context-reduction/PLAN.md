# MCP Client Context Reduction — Implementation Plan

Design: [DESIGN.md](DESIGN.md)

Reduce the context an MCP client spends on OpenMCP. Bound the jobs resource,
prune the resource surface, and defer the coordinator skill's review section to
a reference loaded at review time.

The plan spans two Git roots. Phase 1 runs in `/home/ngosi/projects/openmcp`.
Phases 2 and 3 run in `/home/ngosi/projects/superpowers-ccg`, a separate root
that needs its own project registration if routed. Both later phases change only
Markdown, a Bash test, and JSON version fields, which match the coordinator's
skip-coordination rule; executing them directly is acceptable.

Phase 2 carries the three repointed contract assertions. Landing the skill
content without them leaves `tests/run.sh` red.

---

### Phase 1: Bounded jobs resource and pruned resource surface

**Task Guide Input:** Reduce the MCP resource payload of the OpenMCP daemon in
`src/openmcp/server.py` and `src/openmcp/models.py`. Three distinct use cases:
(a) delete five resource endpoint functions and their `__all__` entries while
leaving the underlying runtime and database methods untouched, so a future HTTP
dashboard can still reach them; (b) add a new slim Pydantic model and reshape one
resource handler to return a bounded three-key object built from an existing
unbounded database query; (c) change one JSON serializer helper to emit compact
output. Existing tests import two of the deleted functions and assert on the
resource template list, so test updates are part of the work.

**Profile:** `Resolve at execution`

**Goal:** The jobs resource returns a bounded slim payload and the client sees
six resource templates instead of eleven.

**Files:**
- Modify: `src/openmcp/server.py`
- Modify: `src/openmcp/models.py`
- Modify: `tests/test_server.py`

**Tasks:**
1. Remove `project_resource`, `job_events_resource`, `context_resource`,
   `targets_resource`, and `profiles_resource` from `server.py`, including their
   `__all__` entries. Leave `database.jobs()`, `database.events()`,
   `database.context()`, and `runtime.targets()` unchanged.
2. Add `JobSummary` to `models.py` with `id`, `workflow`, `profile`, `state`,
   `context_key`, `target_id`, `attempts`, `updated_at`, and export it. It must
   carry no `result` field.
3. Reshape `project_jobs_resource` to return `{"active": [...], "recent": [...],
   "truncated": N}`. `active` is every job whose state is not in
   `TERMINAL_STATES`, uncapped. `recent` is the 10 most recent terminal jobs by
   `updated_at` descending. `truncated` counts terminal jobs omitted from
   `recent`. Change `_json` to use `separators=(",", ":")` instead of `indent=2`.
4. Update `tests/test_server.py`: drop the `profiles_resource` and
   `targets_resource` imports on line 15, and rewrite
   `test_runtime_resources_use_v2_templates_and_context` to assert the six
   surviving templates are present and the five removed ones absent. Add
   coverage for the uncapped `active` list, the 10-item `recent` cap and its
   ordering, `truncated` including the zero case, `JobSummary` exposing no
   `result`, `openmcp://jobs/{job_id}` still returning full `result.text`, and
   `_json` emitting no indentation.

**Acceptance Criteria:**
- `mcp.list_resource_templates()` returns exactly six templates: `projects`,
  `projects/{project_id}/jobs`, `projects/{project_id}/profiles`,
  `projects/{project_id}/context_instructions`, `jobs/{job_id}`, and
  `workflows/{project_id}`.
- `openmcp://projects/{project_id}/jobs` on a project with 370 jobs returns
  under 4 KB.
- No resource response contains target or provider identity.
- `openmcp://jobs/{job_id}` still returns full `result.text`.
- `database.jobs()` still returns full `JobView` rows including `result`.

**Reviewer Checklist:**
- `active` is genuinely uncapped; a coordinator must never miss a running job.
- `recent` orders by `updated_at`, not `created_at` or insertion order.
- `truncated` counts only terminal jobs, and is 0 rather than absent when none
  are omitted.
- No database or runtime method was narrowed, only the resource layer.
- No new query parameter or detail flag was introduced on the jobs resource.

**Verification Checks:**
- `cd /home/ngosi/projects/openmcp && uv sync --all-extras --frozen`
- `cd /home/ngosi/projects/openmcp && uv run pytest`
- `cd /home/ngosi/projects/openmcp && uv build`

**Commit:** `perf(server): bound jobs resource and prune resource surface`

---

### Phase 2: Coordinator skill content and contract assertions

**Task Guide Input:** Restructure the `coordinating-multi-model-work` skill in
the `superpowers-ccg` repository to cut its per-session context cost, and update
the Bash contract test that pins strings to it. Three distinct use cases:
(a) correct and prune a reference table of MCP tools and resources that is
currently stale against the server; (b) move one 3237-byte section out of a
skill file into a new reference file loaded on demand, preserving wording, while
leaving a stub that retains the safety rules and both required output blocks;
(c) add a new short section documenting a tool, written so that a
provider-identity grep guard in the test suite does not match. The test file
asserts three specific sentences live in the skill file; those sentences move,
so the assertions move with them.

**Profile:** `Resolve at execution`

**Goal:** The coordinator skill drops to roughly 7.7 KB, documents
`context_init`, and `tests/run.sh` stays green.

**Files:**
- Modify: `skills/coordinating-multi-model-work/SKILL.md`
- Modify: `skills/coordinating-multi-model-work/references/tool-contract.md`
- Create: `skills/coordinating-multi-model-work/references/review.md`
- Modify: `skills/executing-plans/SKILL.md`
- Modify: `tests/test-contracts.sh`

**Tasks:**
1. In `tool-contract.md`, cut the Resources list to the six surviving templates,
   add the `active` / `recent` / `truncated` shape for the jobs resource, and
   correct two pre-existing omissions: add a `context_init` row to the Tools
   table and `openmcp://projects/{project_id}/context_instructions` to the
   Resources list.
2. Move the `Gate 3: Review` body from `SKILL.md` into `references/review.md`,
   preserving wording. The reference receives the spec verification steps, the
   quality review scoping rules, the two-cycle review-fix loop, and the finalize
   checklist including backlog debt filing. The `SKILL.md` stub retains the
   trigger condition, that a spec failure blocks quality review, that
   correctness and security findings force `FAIL`, that review runs against a
   read-only target and makes no commit, both required output blocks verbatim,
   and a direction to load the reference.
3. In `SKILL.md`, rewrite `Setup and Resume` step 4 to reconcile against
   `active` and fetch `openmcp://jobs/{job_id}` only for a specific result, and
   add a section after it documenting `context_init`: one instruction per
   `(project_id, workflow)` pair, empty instruction clears it, stored in the
   database and persistent across jobs and sessions until cleared, delivered
   through the worker's harness context mechanism additively and never through
   the job prompt or by shadowing repository context files, read back through
   the `context_instructions` resource. Name no backend, flag, or generated
   filename. Update `skills/executing-plans/SKILL.md` line 16 to the new shape.
4. In `tests/test-contracts.sh`, repoint the three assertions for `Accepted debt
   must never be lost`, `Blocking findings are never filed`, and `Filing a row
   never creates its own commit` from `SKILL.md` to `references/review.md`, and
   add a line-count cap for `references/review.md`.

**Acceptance Criteria:**
- `SKILL.md` is at or under 7.9 KB and still at or under 265 lines.
- `tool-contract.md` lists six resources and eight tools, and stays at or under
  90 lines.
- `references/review.md` exists and contains the finalize checklist.
- No file under `skills/` matches `\bcodex\b` or `\bagy\b`.
- `bash tests/run.sh` passes.

**Reviewer Checklist:**
- The Gate 3 stub still forces `FAIL` on correctness and security findings and
  still requires a read-only review target; these are safety rules, not detail.
- Both required output blocks remain verbatim in `SKILL.md`.
- The `context_init` section names no provider, flag, or generated filename.
- The finalize checklist survived the move intact, especially backlog debt
  filing; accepted debt must never be lost.
- The three repointed assertions match text that actually exists in
  `references/review.md`.

**Verification Checks:**
- `cd /home/ngosi/projects/superpowers-ccg && bash tests/run.sh`
- `cd /home/ngosi/projects/superpowers-ccg && wc -c skills/coordinating-multi-model-work/SKILL.md`

**Commit:** `docs(skill): defer gate 3 to reference and document context_init`

---

### Phase 3: Plugin version bump

**Task Guide Input:** Bump a plugin version across two JSON manifests and six
Markdown version markers in the `superpowers-ccg` repository. A Bash contract
test asserts the two manifest versions are equal to each other and that every
`shared/*.md` file carries a matching `ccg-shared-version` marker. Purely
mechanical; no behavioural change.

**Profile:** `Resolve at execution`

**Goal:** The skill contract change ships versioned at `10.2.0`.

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `shared/worker-contract.md`
- Modify: `shared/erp.md`
- Modify: `shared/notes-template.md`
- Modify: `shared/journal-template.md`
- Modify: `shared/backlog-contract.md`
- Modify: `shared/closeout-template.md`

**Tasks:**
1. Set `version` to `10.2.0` in `.claude-plugin/plugin.json` and in the first
   plugin entry of `.claude-plugin/marketplace.json`.
2. Set `ccg-shared-version` to `10.2.0` in all six `shared/*.md` files.

**Acceptance Criteria:**
- Both manifests report `10.2.0`.
- All six `shared/*.md` markers report `10.2.0`.
- `bash tests/run.sh` passes.
- No file outside the eight listed is modified.

**Reviewer Checklist:**
- All six `shared/*.md` files were updated; the contract test iterates the glob,
  so a missed file fails the build.
- No instructional content changed alongside the version fields.

**Verification Checks:**
- `cd /home/ngosi/projects/superpowers-ccg && bash tests/run.sh`

**Commit:** `chore(plugin): bump to 10.2.0`
