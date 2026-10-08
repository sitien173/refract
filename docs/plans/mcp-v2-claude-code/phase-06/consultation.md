# EXTERNAL RESPONSE

## META

- **Phase:** 6 — superpowers-ccg v12 contract
- **Date:** 2026-10-08
- **Mode:** Read-only implementation consultation
- **Registered root:** `/home/ngosi/projects/superpowers-ccg`
- **Reported companion HEAD:** `85283559ec9c8241a32d10557fa6b1ba49b57d5c`
- **Primary root:** `/home/ngosi/projects/openmcp`
- **Reported primary HEAD:** `18e352e5b33bf5ad3bdbaefeb464d55027534788`
- **Plan:** `docs/plans/mcp-v2-claude-code/`
- **Scope:** Fourteen authorized implementation paths
- **Implementation performed:** No
- **Tests executed:** None
- **Independent quality review:** Not performed

Repository cleanliness and commit identities were supplied as preflight information, not independently revalidated through Git.

## SUMMARY

**Phase 6 is suitable for implementation after targeted prompt corrections.**

The companion prompt is substantially aligned with the confirmed primary DESIGN and seven-phase PLAN.

Inspection of the current companion files and primary public OpenMCP source supports a minimal migration without expanding the fourteen-path scope.

The principal risks are:

1. Preserving obsolete assertions that contradict the v2 API.
2. Mistaking the pre-existing 101-line implementer failure for new v2 RED evidence.
3. Treating `task_guide` as a route-validation API exposing information it does not return.
4. Mishandling resumed jobs absent from the bounded terminal listing.
5. Weakening sequential Coordinator gates when documenting the new dependency scheduler.
6. Increasing existing line limits instead of making surgical reductions.

No additional implementation path is recommended.

## FILES MODIFIED

**None.**

No source files, plans, notes, journals, manifests, or Git metadata were changed.

* * *

## NOTES

### 1\. Inspected sources and evidence boundaries

Read the companion Phase 6 prompt and PLAN, the authoritative primary PLAN and DESIGN, all fourteen authorized implementation paths, and the primary public:

- [src/openmcp/server.py](<src/openmcp/server.py>)
- [src/openmcp/models.py](<src/openmcp/models.py>)

Also read the existing TDD and verification skill instructions.

**Source-verified:** Public tool signatures, visible response construction, job-summary DTO fields, error definitions, wait defaults, terminal result paging, response limits, and the `task_guide` return shape.

**Confirmed-design-derived, not independently runtime-verified:** Dependency persistence and immutability, reader/writer admission fairness, session recovery semantics, transitive cancellation, and successful end-to-end heartbeat behavior.

**Supplied preflight evidence:** Clean roots, baseline failure, prior phase outcomes, and completed literal audit.

No tests, OpenMCP calls, live-service inspections, or Git operations were performed.

### 2\. Verified seven-tool contract

The following public signatures match `server.py` and the authoritative DESIGN.

| Tool | Public arguments | Return shape |
| --- | --- | --- |
| `project_resolve` | `path`, `alias=""` | `{project:{id,alias,path}}` |
| `task_guide` | `project_id` | `{workflows,profiles:{default,available},guidance}` |
| `job_submit` | `project_id`, `workflow`, `prompt`, `profile=""`, `context_key=""`, `fresh_session=false`, `depends_on=[]` | `{job:summary}` |
| `job_wait` | `job_id`, `timeout_s=3600`, `result_offset=0` | `{job:summary,result:{text,error,next_offset}}` |
| `job_list` | `project_id` | `{active,recent,more_recent}` |
| `job_cancel` | `job_id` | `{job:summary,cancelled_dependents:[id]}` |
| `job_retry` | `job_id` | `{job:summary}` |

The public job-summary DTO contains exactly:

`id, project_id, workflow, profile, state, context_key, attempts, access_mode, depends_on, waiting_on, waiting_reason, created_at, updated_at`

The four workflow names are:

`consult`, `implement`, `review`, `other`.

**Important correction:** `task_guide` accepts only `project_id`.

It exposes workflow names, default and available profile names, and project guidance.

It does not expose a configuration revision, execution target, capability list, or per-workflow routing identity.

A Coordinator can validate public names against the response. It cannot conclusively establish every profile/workflow mapping from invented response fields.

An unavailable profile or unsupported mapping must be handled through the actual guidance and resulting server error, without guessing a replacement.

### 3\. Standard cycle versus reconciliation

The standard successful cycle is:

```text
project_resolve
    ↓
task_guide
    ↓
job_submit
    ↓
job_wait
    ↓
result.text
```

This is four calls when the initial wait returns a terminal result fitting one page.

It is not a universal four-call maximum.

Additional calls are legitimately required for nonterminal waits, result pages, session resumption, or error reconciliation.

**Resume procedure:**

1. Resolve the canonical Git root.
2. Reuse the persisted project ID and recorded job references.
3. Call `job_list(project_id)`.
4. Reconcile active jobs against handover and Git state.
5. Recover known terminal jobs through `job_wait(job_id, timeout_s=0)` when necessary.
6. Submit new work only after resolving ownership and collision ambiguity.

A significant edge case requires explicit documentation:

`job_list` exposes all active jobs, but only the newest ten terminal jobs.

`more_recent` is an integer count, not a pagination cursor.

Therefore, a known job missing from `recent` is not necessarily unknown.

Use its recorded ID with `job_wait` rather than treating the absence as permission to submit duplicate work.

An active job absent from handover remains a collision: stop and request reconciliation.

Do not weaken the existing resume table.

### 4\. Waiting and result paging

The primary server source confirms:

- Default `job_wait` timeout: **3600 seconds**.
- Valid timeout range: **0–3600 seconds**.
- Heartbeat interval configured at 30 seconds.
- Nonterminal timeout returns a normal result with `next_action`.
- Nonterminal results contain empty result text.
- Terminal result text is paginated using Unicode character offsets.
- Complete response limits are strictly below 30,000 serialized characters and 9,000 UTF-8 bytes.

Recommended Coordinator rule:

> Maintain at most one outstanding wait per job. Use the default 3600-second wait without a short hardcoded replacement. Repeat only after receiving a nonterminal result. If the connection drops, reconnect using the same job ID rather than resubmitting the work.

Terminal paging must use:

```text
job_wait(
    job_id=<original ID>,
    timeout_s=0,
    result_offset=<result.next_offset>
)
```

Continue until `result.next_offset` is `null`.

Concatenate the returned text in offset order. Never silently discard intermediate pages.

The actual server code adaptively shrinks terminal pages to fit the complete response envelope.

Successful six-minute waits through the real Claude Code client remain Phase 7 acceptance work, not something verified by this consultation.

### 5\. Errors and mutation safety

The public source defines all thirteen approved error codes:

```text
unknown_project
invalid_path
alias_taken
unknown_job
unknown_profile
invalid_dependency
dependency_failed
invalid_state
config_invalid
daemon_stopping
invalid_request
response_too_large
internal_error
```

Expected errors have four fields:

```json
{
  "code": "error_code",
  "message": "Actionable explanation",
  "next_action": "Safe recovery instruction",
  "retryable": false
}
```

The server implements compact JSON error delivery and normalizes recognized SDK errors into `isError` responses.

Recommended documentation rules:

- Follow `next_action`.
- Correct invalid arguments without inventing alternate parameters.
- Resolve unknown projects through `project_resolve`.
- Use `job_list` when reconciling unknown job IDs.
- Treat `dependency_failed` as a retry/dependency recovery issue.
- Retry an `internal_error` at most once, then report its request ID.
- Never expose internal diagnostics or provider identities.

**Mutation-overflow safety is essential.**

Source inspection confirms that mutation responses can preserve the applied operation and root ID when response metadata exceeds the budget.

If `response_too_large` says a submission, retry, cancellation, or project resolution was already applied, follow the supplied ID and recovery instruction.

Do not blindly repeat the mutation.

If the outcome remains ambiguous, reconcile before another submission.

### 6\. Dependency and admission semantics

The confirmed design requires immutable submission dependencies.

`depends_on` is caller-specified at submission. Dependency links are not subsequently edited.

`access_mode`, `waiting_on`, and `waiting_reason` are server-derived.

The allowed access classes are:

- `parallel_read`
- `exclusive`

The design establishes these rules:

- Reader overlap requires verified read-only enforcement for every possible execution target and fallback.
- `max_project_readers` defaults to 1.
- Exclusive work remains a barrier for later readers.
- Identical project/workflow/context session scopes serialize.
- Dependency-blocked jobs reserve no execution capacity.
- Failed, cancelled, or interrupted dependencies cancel queued descendants transitively.
- Retrying a parent does not revive cancelled descendants.
- Retrying a job preserves its job ID and dependency links.

These scheduler rules are design-confirmed; the scheduler implementation itself was not inspected.

**Coordinator policy remains stricter than scheduler capability.**

The presence of `depends_on` does not authorize overlapping gated implementation and review submissions in the same root.

Retain the existing sequence:

```text
Consult → Implement → Validate → Review
```

Each gate requires completed evidence and the relevant Git checks before the next submission.

Replace the obsolete FIFO-only description without removing Coordinator serialization policy.

### 7\. Minimal file-change recommendations

All proposed modifications fit within the fourteen authorized paths.

| Path or group | Recommended treatment |
| --- | --- |
| [references/tool-contract.md](<references/tool-contract.md>) | Replace legacy table/resources with seven-tool contract, DTO shapes, waits, errors, and dependencies. |
| [coordinating-multi-model-work/SKILL.md](<coordinating-multi-model-work/SKILL.md>) | Surgically replace setup, reconciliation, guidance, waiting, and FIFO-only statements. |
| [references/handover.md](<references/handover.md>) | Preserve schema; change only if needed to clarify existing reconciliation semantics. |
| [executing-plans/SKILL.md](<executing-plans/SKILL.md>) | Existing delegation and resume rules appear compatible; avoid unnecessary changes. |
| [executing-plans/implementer-prompt.md](<executing-plans/implementer-prompt.md>) | Remove at least one nonessential line while preserving fresh/resumed payloads. |
| [writing-plans/SKILL.md](<writing-plans/SKILL.md>) | Update obsolete project-registration terminology in the authoring prohibition. |
| [tests/test-contracts.sh](<tests/test-contracts.sh>) | Add v2 assertions; replace contradictory legacy assertions; preserve other guards. |
| Three manifests | Change only their version fields. |
| Four shared Markdown files | Change only the version markers. |

The fourteen paths are an authorization boundary, not a requirement to modify every file.

Do not introduce a new helper, test file, configuration file, dependency, or workflow.

### 8\. Strong surgical contract-test recommendations

The current [tests/test-contracts.sh](<tests/test-contracts.sh>) contains positive assertions that require obsolete behavior.

These must be replaced with equivalent v2 protections, rather than simply deleted.

In particular, replace assertions requiring:

- `status`
- `project_register`
- project/profile/workflow resource URIs
- same-project FIFO-only wording
- the obsolete writing-plans registration prohibition

Retain existing provider-identity, target-label, Git lifecycle, policy separation, anchor, ERP, and line-cap guards.

**First new RED assertion**

Add an explicit seven-tool check before the existing line-cap checks.

A suitable Bash pattern is:

```bash
contract=skills/coordinating-multi-model-work/references/tool-contract.md

tools=(
  project_resolve
  task_guide
  job_submit
  job_wait
  job_list
  job_cancel
  job_retry
)

for tool in "${tools[@]}"; do
    if ! grep -qF "| \`$tool\` |" "$contract"; then
        printf 'v2 contract missing tool: %s\n' "$tool" >&2
        exit 1
    fi
done
```

This intentionally fails against the existing reference because `project_resolve` and `job_list` have not yet been documented there.

It demonstrates a missing v2 requirement independently of the old implementer line-cap failure.

The implementation worker must actually execute this test and retain its failure output before changing production documentation.

**Additional assertions**

Require explicit reference coverage for:

- All seven signatures and nested response shapes.
- The thirteen exact error codes.
- `result.next_offset`, `result_offset`, and zero-timeout terminal paging.
- Default 3600-second waiting.
- Same-ID connection recovery.
- Active/recent listing bounds.
- `cancelled_dependents`.
- Immutable dependency semantics.
- Reader/exclusive admission and waiting metadata.
- Public workflow/profile guidance without route identity fields.
- Safe mutation-overflow reconciliation.

Use targeted positive checks against the owning document rather than a large number of vague keyword checks across all skills.

Keep the existing recursive privacy and policy guards.

Add a negative check across `skills` and `shared` for:

```text
project_register
openmcp://
resource_uri
timeout_s: 300
```

Ensure missing paths or command errors cannot accidentally count as successful negative checks.

The existing test already checks manifest-version equality and shared marker parity.

Strengthen it with the fixed expected version:

```python
assert plugin_version == "12.0.0"
```

Verify the manifest changes are version-only by inspecting the source diff, not merely by comparing parsed version strings.

**Preserve the existing caps:**

| File class | Maximum lines |
| --- | --- |
| Coordinator skill | 265 |
| Tool contract reference | 90 |
| Implementer prompt | 100 |
| Normal skills | 90 |

Do not raise limits, disable loops, or delete unrelated assertions.

### 9\. Baseline failure versus v2 RED

The supplied companion preflight records:

```text
implementer-prompt.md: 101 lines
limit: 100
```

That failure predates Phase 6 implementation.

Its recorded evidence must remain separate from the newly introduced v2 failure.

Recommended implementation sequence:

1. Add the new v2 assertions.
2. Execute the focused contract test before documentation edits.
3. Record the exact failure identifying the absent v2 requirement.
4. Apply the smallest documentation and version changes.
5. Remove one nonessential implementer-prompt line.
6. Run the focused test and full verification suite.
7. Record complete RED/GREEN results and actual exit codes.

The existing baseline trace is not new RED evidence.

No new RED or GREEN execution was performed during this consultation.

### 10\. Exact prompt corrections

The prepared prompt should be finalized with the following clarifications.

**Correction A —** `**task_guide**` **input**

Replace the instruction implying that the phase request is passed to `task_guide`.

Use:

> Call `task_guide(project_id)` once for each new phase and use its public workflows, profiles, and guidance. Carry the complete phase request in the self-contained `job_submit.prompt`. Do not assume route identity or configuration fields exist in the guidance response.

**Correction B — Resume listing**

Add:

> `job_list` returns all active jobs but only ten terminal jobs. A saved job reference missing from `recent` must be checked with `job_wait(job_id, timeout_s=0)` before concluding it is unavailable. Never interpret listing truncation as permission to submit duplicate work.

**Correction C — Waiting**

Use:

> Keep one outstanding `job_wait` per job, normally with the default 3600-second timeout. Repeat only after a nonterminal response. Reconnect with the original job ID after a dropped call. Page terminal results using `result.next_offset`, `timeout_s=0`, and `result_offset` until null. Do not poll, sleep, or overlap replacement waits.

**Correction D — Dependencies**

Add:

> Document immutable dependencies and reader/writer admission as server capabilities, but retain sequential Coordinator submissions and all implementation, validation, review, Git, and anchor gates.

**Correction E — TDD evidence**

Add:

> Place a focused new v2 contract assertion before the baseline-failing line-cap check, demonstrate its specific failure before changing documentation or manifests, and preserve the separate pre-existing 101-line failure record.

**Correction F — Source scope**

Add:

> The fourteen implementation paths are the complete permission boundary. Modify only paths requiring corrections. Preserve compatible files unchanged, and limit manifest edits to three version fields and shared edits to four version markers.

These corrections require no new path or additional implementation phase.

### 11\. Version synchronization

Direct file inspection confirms the current value is `11.0.6`.

The required target is `12.0.0`.

**Manifest values — exactly three:**

1. [.claude-plugin/plugin.json](<.claude-plugin/plugin.json>) → `version`
2. [.claude-plugin/marketplace.json](<.claude-plugin/marketplace.json>) → `plugins[0].version`
3. [.codex-plugin/plugin.json](<.codex-plugin/plugin.json>) → `version`

**Shared markers — exactly four:**

1. [shared/erp.md](<shared/erp.md>)
2. [shared/journal-template.md](<shared/journal-template.md>)
3. [shared/notes-template.md](<shared/notes-template.md>)
4. [shared/worker-contract.md](<shared/worker-contract.md>)

Replace only:

```text
ccg-shared-version: 11.0.6
```

with:

```text
ccg-shared-version: 12.0.0
```

Preserve every other shared-contract rule.

Do not change the manifest descriptions, plugin metadata, MCP configuration, or unrelated JSON fields.

Version synchronization is not, by itself, evidence of a completed release.

### 12\. Required future verification

The implementation worker should execute the prepared commands with the specified deadlines:

```bash
timeout --kill-after=5s 120s bash tests/run.sh
timeout --kill-after=5s 30s bash -n tests/test-contracts.sh
git diff --check
```

Also perform the exact prohibited-pattern audit with `tgrep`.

A no-match result with exit status 1 is expected for that audit.

Capture full command output, distinguish timeouts from test failures, and stop if a command exceeds its deadline.

Inspect the eventual diff inventory and verify no unauthorized implementation path changed.

Do not interpret test success as independent quality-review approval.

* * *

## SPEC COMPLIANCE

**Assessment: PLANNING SUITABILITY ONLY**

| Criterion | Consultation assessment |
| --- | --- |
| Confirmed seven-tool contract | Source-verified |
| Public signatures and DTO shapes | Source-verified |
| Task-guide response limitations | Source-verified |
| 3600-second wait and terminal paging implementation | Source-verified |
| Thirteen error definitions | Source-verified |
| Response-size and mutation-overflow handling | Source-verified |
| Immutable dependency and admission rules | Confirmed design; runtime not independently inspected |
| Coordinator gates and ownership preservation | Migration approach identified |
| Fourteen-path boundary | Matches companion and primary plans |
| Version-only change requirements | Existing values inspected; proposed changes defined |
| New v2 RED | Not executed |
| Fresh GREEN verification | Not executed |
| Implementation correctness | Not assessed |
| Independent quality approval | Not assessed |

**Conclusion:** The migration approach is consistent with the confirmed specification, subject to the prompt corrections above.

This is not an implementation-compliance or quality sign-off.

* * *

## CLARIFICATIONS NEEDED

**None blocking.**

The following distinctions should be resolved in the finalized prompt, without requesting additional scope:

1. `task_guide` exposes public choices, not a complete executable-route validation schema.
2. `job_list` is not an exhaustive terminal-job history.
3. Four calls describe the normal successful cycle, not every recovery or paginated-result path.
4. Dependency-enabled scheduling does not change sequential Coordinator gate ownership.
5. Authorized paths need not all be modified.

No missing implementation path was identified in the inspected files. The broader literal audit's finding of no omitted paths was supplied in the prepared prompt and was not independently rerun.

The Coordinator should confirm that both repository states remain unchanged before authorizing implementation.

* * *

## NEXT

**TASK\_COMPLETE — Read-only Phase 6 consultation.**

The consultation has identified a bounded implementation approach, source-supported v2 contract details, required test changes, and exact prompt corrections.

No implementation, test execution, journal write, plan modification, Git mutation, or independent quality review occurred.

**Recommended next action:** Coordinator records this consultation, incorporates the prompt corrections, reconfirms the two repository baselines, and authorizes Phase 6 implementation under the existing fourteen-path boundary.

Condense repeated implementation guidance

Separate verified facts from recommendations

Add a prioritized implementation checklist