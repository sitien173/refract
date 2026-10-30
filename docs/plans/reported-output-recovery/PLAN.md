# Reported Output Recovery Plan

**Design:** [DESIGN.md](DESIGN.md)
**Status:** DONE. Both phases validated and independently reviewed on `main`. Phase refs preserve checkpoint evidence; final consolidation requires verification at the plan implementation ref.
**Context key:** `reported-output-recovery`
**Base:** `refs/plans/reported-output-recovery/base`
**Base commit:** `c5944a963f2ad169201feef7d30c385b27a05f0d`
**Commit:** `fix(retry): expose explicit recovery for reported successful output`

## Outcome

Return live `retry: {retryable, next_target}` in report acknowledgements. Only `succeeded` plus category `output` can expose fallback. The Coordinator explicitly creates recovery with `job_submit` and `fresh_session: true`.

Preserve original execution records. Leave `job_wait`, `job_retry`, database schemas, and automatic execution unchanged.

## Diagnosis and Scope

`server/src/refract/runtime.py:397` suppresses retry metadata for succeeded jobs. `Runtime.report_error` currently returns only the database acknowledgement. `server/src/refract/server.py:874` renders only `report` and `duplicate`. Therefore reporting unusable successful output supplies no recovery token.

The runtime already has `_next_target_token` and submission token validation. Reuse them rather than changing token formats, planning, or execution machinery.

The concrete example and confirmed design are recorded in DESIGN.md. Reproduce the missing report-acknowledgement token in a deterministic regression test before production edits.

## Baseline Evidence

Pinned revision: `c5944a963f2ad169201feef7d30c385b27a05f0d`. The attached branch was `main`; the tree was clean before anchoring. No project job was active. Plan tracking is `tracked`.

Commands run from the repository root:

- `(cd server && uv run pytest -q tests/test_runtime.py tests/test_server.py tests/test_database.py)`: passed, 188 tests; four skipped.
- `bash plugin/tests/test-contracts.sh`: passed.
- `git diff --check`: passed before plan creation.
- `(cd server && uv run pytest -q)`: passed, 1250 tests; 23 skipped; 15 live tests deselected. Task `b20d3b42d`, exit zero.

Focused baseline output: `.pi/tasks/01a188b2-3ae6-76b1-8d38-8f8c0eb361fb-3098105/b29557a6e.output`.

Existing environment warnings: ambient `VIRTUAL_ENV` differs from the project environment; an `SSL_CERT_DIR` entry does not exist. The focused baseline still exited zero. Live backend tests are excluded by repository configuration. No live probes or deployment are authorized.

All verification commands below passed at the plan base. Full baseline output: `.pi/tasks/01a188b2-3ae6-76b1-8d38-8f8c0eb361fb-3098105/b20d3b42d.output`. No baseline repair phase is required by these checks.

## Routing and Gates

- Sequence for each phase: `implement` then independent `review`.
- Implementation profile: resolve through fresh phase guidance.
- Review profile: resolve through fresh phase guidance.
- Reason: additive API behavior with explicit replay safeguards.
- Done when: phase commands pass at the reviewed checkpoint; specification and independent quality review pass.

The Coordinator creates phase prompts, notes, journals, and phase anchors during execution. Do not create empty phase directories while planning. Start one implementation job at a time. Workers edit only their declared file set. The Coordinator owns validation, Git checkpoints, and final consolidation.

## Phase 1: Return explicit recovery metadata without execution mutation

**Task Guide Input:** Implement the confirmed acknowledgement-only recovery contract. A succeeded job reported as output-unusable can expose the next healthy target. A report alone never launches recovery. Preserve other report behavior, stored execution history, sessions, target health, token validation, `job_wait`, and `job_retry`. Cover duplicate freshness and explicit new-job recovery through deterministic tests.

**Goal:** Make report acknowledgements sufficient for safe, explicit fallback routing.

**Files:**
- Modify: `server/src/refract/runtime.py`
- Modify: `server/src/refract/server.py`
- Modify: `server/tests/test_runtime.py`
- Modify: `server/tests/test_server.py`

**Tasks:**
1. Add a failing regression for succeeded output reports lacking recovery metadata. Record the failing assertion before production edits. Characterize unchanged execution and retry behavior.
2. Record or deduplicate the report first. Read the job, compute eligibility, and reuse `_next_target_token`. Include top-level `retry` in the rendered acknowledgement. Return `false` and `null` for ineligible or unavailable recovery. Preserve report fields and validation.
3. Cover state/category boundaries and live duplicate recomputation. Test health changes, configuration changes, exhausted candidates, existing token binding, stale-token rejection, and a duplicate report retrieving a refreshed token.
4. Exercise report then explicit `job_submit` with the same routing scope and `fresh_session: true`. Confirm the new job uses the selected fallback. Compare original execution fields, stored metadata, sessions, and health before and after reporting. Verify reporting itself starts no execution.

**Acceptance Criteria:**
- Every successful acknowledgement retains `report` and `duplicate` and adds exactly `retry: {retryable, next_target}`.
- Only `succeeded` plus `output` can return `retryable: true` with a valid token.
- Protocol reports and other states return `false` and `null` in the acknowledgement. Existing failure-retry metadata from `job_wait` remains unchanged.
- No healthy later candidate returns `false` and `null`.
- Duplicate requests preserve retained report IDs and compute current routing rather than returning a stored token.
- Existing report-key conflicts, redaction, unknown-job errors, request bounds, and compact-response behavior remain valid.
- A token accepted by `job_submit` creates a different job ID at the intended fallback with fresh-session execution requested.
- Reporting changes only diagnostic storage. Original state, result, attempts, timestamps, session records, target health, and stored retry metadata remain unchanged.
- Succeeded `job_wait` retry metadata remains null; `job_retry` still rejects succeeded jobs.
- No changes to database schema, token format, driver classification, or execution machinery.
- The regression is RED before implementation and GREEN afterwards.

**Reviewer Checklist:**
- Determine eligibility from validated reporting and current job state, not response-text heuristics.
- Read job state after report recording completes. Exercise a report made while a job is nonterminal without exposing recovery.
- Preserve one retained event for identical duplicates; do not cache routing in events or results.
- Reuse current target selection and existing token validation without silently falling back to a primary submission.
- Check actual MCP serialization, not only runtime return dictionaries.
- Distinguish acknowledgement recovery hints from immutable result metadata and execution authorization.
- Verify tests assert state snapshots and submitted-target behavior rather than only key presence.

**Verification Checks:**
- `(cd server && uv run pytest -q tests/test_runtime.py tests/test_server.py tests/test_database.py)`
- `(cd server && uv run pytest -q)`
- `bash plugin/tests/test-contracts.sh`
- `git diff --check`

## Phase 2: Make acknowledgement-based recovery the coordinator contract

**Task Guide Input:** Document and test explicit recovery after an unusable succeeded result. The acknowledgement, not `job_wait`, supplies the token. Require complete terminal pagination, partial-effect reconciliation, original-job correlation, matching project/workflow/profile, and `fresh_session: true`. Stop for unavailable routing and refresh stale tokens without silently dropping them. Preserve diagnostic-only execution semantics and existing failed-job recovery.

**Goal:** Give coordinators one unambiguous, tested recovery procedure.

**Files:**
- Modify: `server/README.md`
- Modify: `server/src/refract/server.py`
- Modify: `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`
- Modify: `plugin/skills/coordinating-multi-model-work/references/review.md`
- Modify: `plugin/tests/test-contracts.sh`

**Tasks:**
1. Add failing contract assertions for acknowledgement recovery guidance, explicit new-job submission, and fresh-session safeguards. Preserve existing diagnostic and failed-job instructions.
2. Update server MCP guidance and README acknowledgement shape. Document eligible/ineligible combinations, duplicate freshness, absence of fallback, existing event retention, and unchanged `job_wait` and `job_retry` behavior.
3. Update the authoritative plugin tool contract and review recovery pointer. Require reconciliation before explicit submission. Keep one detailed recovery procedure, referenced from review guidance. Run the declared checks and resolve only in-scope findings.

**Acceptance Criteria:**
- Documentation shows top-level acknowledgement `retry` and the exact supported field names.
- Coordinator instructions read every terminal page before diagnosing output failure.
- Recovery uses the acknowledgement token in a new `job_submit`, preserving routing scope and using `fresh_session: true`.
- Instructions require inspecting partial files and external effects before replay; tokens do not authorize replay automatically.
- `false` and `null` stop recovery and request routing guidance.
- Stale-token handling refreshes via an identical retained report request. It never silently omits `next_target` to restart the primary target.
- Reporting failure never causes recursive reports or blocks safe reconciliation.
- The original job remains `succeeded`. `job_retry` remains unavailable for succeeded jobs. `job_wait` remains unchanged.
- Retention limits and strict-client compatibility are stated without promising durable eligibility or permanent deduplication.
- New contract assertions fail against old instructions and pass against updated instructions.

**Reviewer Checklist:**
- Separate reported unusable output from verified backend failure.
- Preserve all existing request arguments, bounds, privacy rules, and failed-job retry guidance.
- Ensure examples match Phase 1 serialization and do not invent new API parameters.
- Keep coordinator recovery explicit and bounded; do not introduce an automatic retry loop.
- Verify contract assertions test the new branches and safety requirements.

**Verification Checks:**
- `bash plugin/tests/test-contracts.sh`
- `(cd server && uv run pytest -q tests/test_runtime.py tests/test_server.py tests/test_database.py)`
- `(cd server && uv run pytest -q)`
- `git diff --check`

## Closeout

After both phases pass, consolidate checkpoints into the plan-level commit. Resolve phase refs before consolidation. Set the plan implementation ref only after consolidation, then rerun every verification command at that exact revision. Keep phase evidence and reviewed refs. Report live tests as not run; they are outside authorization.

Leave the unrelated active `worker-job-telemetry` plan and all existing plan artifacts unchanged. Reconcile live project jobs before every submission. Do not infer pending work from unrelated handover status alone.
