# Remove Legacy Job Result Metadata

**Status:** Approved 2026-10-27. Phase 1 authorized.
**Design:** [DESIGN.md](DESIGN.md)
**Slug:** `remove-legacy-metadata`
**Commit:** `refactor(metadata): replace legacy job result semantics`
**Base:** `refs/plans/remove-legacy-metadata/base`
**Base revision:** `ef9f219ae8cfe7d6664bfb6762c22382752ce36c`
**Tracking:** `tracked`

## Outcome

Replace untyped result metadata with the approved grouped contract. Migrate schema-15 history atomically to schema 16. Remove runtime compatibility, duplicate counters, and the backend result-usage bridge. Preserve normalized telemetry and job execution behavior.

Execute one phase per invocation after approval. Database migration, deployment, daemon restart, and live probes remain unauthorized outside their explicit execution gates.

## Coordination

```text
# ROUTE
- Sequence: implement -> review
- Implement Profile: selected from task guidance at execution
- Review Profile: selected from task guidance at execution
- Reason: breaking result contract with historical data migration
- Done When: every phase passes fresh checks and independent review
```

Use the existing isolated worktree. Resolve its actual Git root at execution. Require an attached branch and reconcile active jobs before every submission. The initial handover has no project or job references. Obtain guidance separately for each phase. Never route by a hard-coded provider or model.

Each phase uses test-first implementation, coordinator specification checks, and independent read-only quality review. Run all phase commands after implementation and after review fixes. Checkpoint only validated work. Do not edit source while a worker is active.

Write phase prompts, notes, and journals only when executing their phase. Preserve the approved design. Consolidate validated checkpoints into the one plan-level commit only after all phases pass.

The telemetry plan's historical handover remains ACTIVE on another project identity. This plan is a distinct approved successor in this worktree. Do not resume, cancel, consolidate, or rewrite that plan. The separate retry-policy plan has not executed and is outside scope.

## Contract and Migration Rules

The exact public shape is defined in DESIGN.md. Keep only `execution`, `failure`, `retry`, and `telemetry` at the metadata root. Do not add a public schema-version field or compatibility aliases.

- Typed nested objects reject unknown fields and invalid types.
- No failure is represented by `failure: null`.
- Missing measurements are explicit unavailable snapshots.
- Preserve measurement provenance and historical observation times.
- Do not infer normalized totals from backend-native counters.
- Preserve existing failure kinds and retryability behavior.
- Generate routing tokens at read time; never persist them.
- Store bounded accumulator state in `jobs.telemetry_state_json`.
- Exclude telemetry `version`, `attribution`, and `completed_attempts` from public output.
- Migration is the only place that reads historical result aliases.
- Normal schema-16 reads and writes accept canonical metadata only.

Migration accepts schema 15 and initializes fresh databases at 16. All other unsupported versions remain rejected without writes. Read-only preflight validates schema structure and historical metadata before writable initialization. Apply DDL, row transformations, and `user_version` within one transaction, before scheduler startup or job recovery. Roll back on failure.

Malformed JSON, invalid recognized fields, and unsupported telemetry versions abort migration with a bounded job/field diagnostic. Do not expose raw stored payloads. Known obsolete counters and unknown extension fields are deliberately removed. Never replace a missing historical measurement timestamp with migration time.

The operator stops the daemon and backs up the entire state directory before deployment. Implementation tests use synthetic temporary databases only. Downgrade requires restoring the backup; this plan adds no reverse migration.

## Baseline Evidence

At the plan base:

- `(cd server && uv run pytest -m 'not live')`: 728 passed, 15 deselected. This command resolved pytest from the ambient Python environment, so the isolated command below supersedes it.
- `bash plugin/tests/test-session-start.sh`: passed.
- `bash plugin/tests/test-contracts.sh`: passed.
- `(cd server/web && npm test)`: failed because local `vitest` was missing.
- `(cd server/web && npm run build -- --outDir /tmp/refract-metadata-dashboard-baseline)`: failed because local build dependencies were missing.

Dependency recovery used the existing lockfiles without tracked changes. Final baseline at `ef9f219ae8cfe7d6664bfb6762c22382752ce36c`:

- `(cd server && uv run --extra dev python -m pytest -m 'not live')`: passed, 728 tests; 15 live tests deselected. Interpreter: Python 3.12.13.
- `(cd server/web && npm test)`: passed, 242 tests across 21 files after `npm ci`.
- `(cd server/web && npm run build -- --outDir /tmp/refract-metadata-dashboard-baseline)`: passed.
- `diff -r server/src/refract/dashboard_static /tmp/refract-metadata-dashboard-baseline`: passed; isolated output matched packaged assets.
- Both plugin checks above passed.

Frontend tests emitted existing React act warnings. `npm ci` reported six dependency vulnerabilities: two moderate, two high, and two critical. No audit remediation was attempted. Dependency triage belongs to the repository maintainer and remains outside this metadata plan. These installation warnings are not a security-clearance claim.

All verification commands run from the repository root. Python commands explicitly use the project interpreter and dev extra. Tests exclude the opt-in `live` marker. A failure caused by product code blocks execution and must become a first repair phase with approval; do not hide it by weakening tests.

## Phase 1: Define the canonical contract and conversion boundary

**Task Guide Input:** Implement strict grouped job-result metadata models, public telemetry projection, and pure schema-15 conversion helpers with unit coverage. Keep the public API and database version unchanged until Phase 2. Use server implementation guidance; review strict typing and historical conversion independently.

**Goal:** Define one tested contract before switching persistence.

**Files:**
- Create: `server/src/refract/result_metadata.py`
- Create: `server/tests/test_result_metadata.py`
- Modify: `server/src/refract/telemetry.py`
- Modify: `server/tests/test_telemetry.py`

**Tasks:**
1. Add strict canonical execution, failure, retry, telemetry, and metadata types. Preserve existing failure enums and measurement semantics. Add tests before implementation.
2. Add explicit projection between internal telemetry state and public measurements. Preserve the existing accumulator and its bounded reconciliation state. Do not expose internal fields through generic model dumps.
3. Add a pure, migration-only converter for schema-15 records. Preserve valid normalized measurements and operational facts; drop obsolete counters and stored tokens. Reject malformed recognized data without fabricating timestamps.

**Acceptance Criteria:**
- Exact key sets and nested types match DESIGN.md.
- Tests reject aliases, extra fields, booleans-as-counts, negative values, non-finite percentages, invalid quality combinations, and unsupported versions.
- Legacy-only records produce unavailable normalized metrics, not guessed totals.
- Normalized telemetry wins over conflicting legacy counters unchanged.
- Public projection cannot expose accounting state.
- Existing API behavior and database schema remain unchanged in this phase.

**Reviewer Checklist:**
- Pre-validation cannot silently strip unknown fields before strict validation.
- Migration conversion is not used as a runtime fallback.
- Missing observation time never becomes the migration timestamp.
- Reuse existing measurement logic; avoid a second accounting algorithm.

**Verification Checks:**
- `(cd server && uv run --extra dev python -m pytest -m 'not live')`
- `bash plugin/tests/test-session-start.sh`
- `bash plugin/tests/test-contracts.sh`

## Phase 2: Switch persistence and server responses atomically

**Task Guide Input:** Wire canonical metadata through storage, execution, runtime, MCP, and dashboard detail responses. Upgrade synthetic schema-15 history to schema 16, isolate accounting state, and preserve retry/pagination behavior. This is one coupled server-contract change; do not leave a mixed persistence boundary. Independently review migration safety and result serialization.

**Goal:** All server result paths use canonical metadata only.

**Files:**
- Modify: `server/src/refract/result_metadata.py`
- Modify: `server/src/refract/models.py`
- Modify: `server/src/refract/telemetry.py`
- Modify: `server/src/refract/database.py`
- Modify: `server/src/refract/execution.py`
- Modify: `server/src/refract/runtime.py`
- Modify: `server/src/refract/server.py`
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/tests/test_result_metadata.py`
- Modify: `server/tests/test_telemetry.py`
- Modify: `server/tests/test_database.py`
- Modify: `server/tests/test_database_atomicity.py`
- Modify: `server/tests/test_execution.py`
- Modify: `server/tests/test_runtime.py`
- Modify: `server/tests/test_server.py`
- Modify: `server/tests/test_dashboard.py`
- Modify: `server/tests/test_mcp_schema_contract.py`

**Tasks:**
1. Add schema-15 preflight and transactional schema-16 migration. Add `telemetry_state_json`; initialize fresh databases identically. Test rollback, repeated opens, unsupported databases, connection cleanup, and unchanged historical data.
2. Make `JobResult.metadata` typed. Update terminal writes, live merges, retry rollover, restart recovery, and accumulator loading to use separate internal state and canonical snapshots. Remove legacy allowlists and generic metadata merge behavior.
3. Update execution metadata production and dynamic retry projection. Preserve failure-kind precedence and context-overflow behavior. Until Phase 3, read only model identity from the old driver usage bridge; never publish its counters.
4. Route MCP and dashboard detail responses through the same canonical serializer. Update tool descriptions and embedded server guidance to the grouped result paths. Preserve nulls, response limits, pending questions, and Unicode pagination.

**Acceptance Criteria:**
- Fresh and migrated databases use schema 16.
- A failed migration leaves schema and row data unchanged.
- Valid historical normalized telemetry survives with original provenance.
- Job IDs, text, errors, states, timestamps, plans, history, sessions, and streams survive.
- Schema-16 reopen performs no conversion or rewriting.
- Running, terminal, cancelled, interrupted, and retried jobs expose the canonical shape.
- Public MCP and dashboard metadata have identical key sets and null semantics.
- No persisted record contains an opaque retry token. Public responses generate eligible tokens from current routing state.
- Accumulator state survives restart and retry without double-counting.
- Unsupported databases retain no-write and connection-cleanup guarantees.

**Reviewer Checklist:**
- No implicit commit splits migration; `user_version` changes last.
- Startup recovery cannot race migration.
- Historical fixtures are genuine schema-15 databases, not schema-16 databases with a changed version number.
- Terminal writes cannot erase newer valid telemetry.
- Dashboard serialization does not drop required null fields.
- Success, context overflow, replay blocking, cancellation, and changed target health preserve existing routing behavior.
- No normal read path falls back to historical aliases.

**Verification Checks:**
- `(cd server && uv run --extra dev python -m pytest -m 'not live')`
- `bash plugin/tests/test-session-start.sh`
- `bash plugin/tests/test-contracts.sh`

## Phase 3: Remove the backend legacy usage bridge

**Task Guide Input:** Remove backend-native result-usage dictionaries and duplicate result counters across all four adapters and drivers. Preserve normalized telemetry collection, explicit model identity, non-streaming fallbacks, and execution outcomes. Independently review accounting equivalence and remaining references.

**Goal:** Legacy result semantics disappear at their production source.

**Files:**
- Modify: `server/src/refract/backends/__init__.py`
- Modify: `server/src/refract/backends/agy.py`
- Modify: `server/src/refract/backends/claude.py`
- Modify: `server/src/refract/backends/codex.py`
- Modify: `server/src/refract/backends/pi.py`
- Modify: `server/src/refract/drivers.py`
- Modify: `server/src/refract/execution.py`
- Modify: `server/tests/test_streaming_backends.py`
- Modify: `server/tests/test_execution.py`
- Modify: `server/tests/test_smoke.py`

**Tasks:**
1. Replace `BackendResult.usage` and `DriverResult.usage` with explicit optional model identity. Delete `USAGE_KEYS`, `_usage_dict`, and parsers used only for removed legacy outputs.
2. Keep provider-native usage parsing needed by normalized collectors. Add regression coverage for four adapters, final-only results, cache accounting, missing telemetry, model fallback, cancellation, and failures.
3. Audit production references. Remove only newly orphaned imports and helpers. Classify remaining native payload keys as collector inputs, not public compatibility.

**Acceptance Criteria:**
- Neither result type carries the old usage dictionary.
- No duplicate legacy result-usage parser remains.
- Model identity and all supported normalized measurements remain available.
- Provider-event fixture keys remain unchanged unless a fixture specifically describes the removed public result shape.
- Backend transports, legacy event recognition, and execution outcomes are unchanged.

**Reviewer Checklist:**
- A native payload key is not sufficient reason to delete collector code.
- Non-streaming paths still preserve available telemetry.
- Unknown measurements remain unavailable; configured model fallback does not fabricate capacity.
- Production legacy-field reads exist only in the schema-15 converter or necessary provider payload parsing.

**Verification Checks:**
- `(cd server && uv run --extra dev python -m pytest -m 'not live')`
- `bash plugin/tests/test-session-start.sh`
- `bash plugin/tests/test-contracts.sh`

## Phase 4: Update clients, contracts, and packaged dashboard

**Task Guide Input:** Align dashboard consumers and fixtures, coordinator instructions, plugin contract tests, and public documentation with canonical metadata and schema-16 upgrade behavior. Rebuild dashboard assets. This combines UI consumption and documentation; choose guidance for the actual phase scope without hard-coding a route. Independently review stale field references and deployability.

**Goal:** Shipped clients and documentation require only the new contract.

**Files:**
- Modify: `server/web/src/components/JobDetails.jsx`
- Modify: `server/web/src/components/JobDetails.test.jsx`
- Modify: `server/web/src/screens/ProjectDetail.test.jsx`
- Modify: `server/web/src/integration/dashboard-flow.test.jsx`
- Modify: `server/src/refract/dashboard_static/index.html`
- Regenerate: `server/src/refract/dashboard_static/assets/` with the existing build
- Modify: `plugin/skills/coordinating-multi-model-work/SKILL.md`
- Modify: `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`
- Modify: `plugin/tests/test-contracts.sh`
- Modify: `README.md`
- Modify: `server/README.md`
- Modify: `server/CLI_ARGUMENTS.md`

**Tasks:**
1. Update dashboard fixtures to exact canonical metadata and remove any old-shape fallback. Preserve measurement labels, quality/provenance, polling, unavailable values, and transcript behavior. Test public metadata without internal version/attribution fields.
2. Update coordinator paths and plugin assertions together. Document `metadata.failure.kind`, `metadata.retry.next_target`, and `metadata.retry.retryable`; keep submit parameter names unchanged. Do not weaken unrelated contract checks.
3. Document the breaking contract, schema-15 upgrade, backup requirement, rollback behavior, malformed-record failures, and coordinated server/plugin/client deployment. Preserve backend capability limitations and leave historical plans/audits unchanged.
4. Run `npm run build` from `server/web` to regenerate packaged assets. Review deletions and additions rather than editing generated files manually. Rerun the offline release checks.

**Acceptance Criteria:**
- Dashboard tests cover complete, partial, unavailable, running, and terminal telemetry with canonical metadata.
- Navigation, polling, and transcript retention regressions remain covered.
- Current plugin and public documentation contain no instructions to consume removed result fields.
- Tests assert canonical fields and reject accidental legacy reintroduction.
- Packaged assets are reproducible from the updated source.
- Documentation explicitly states historical raw counters are removed, not normalized.

**Reviewer Checklist:**
- No new UI feature or unrelated formatting changes.
- No metadata aliases remain in fixtures or active guidance.
- Unrelated uses of `metadata`, provider-native counters, and legacy routes remain in scope only when necessary.
- The documentation never claims new provider capabilities or live verification.
- Generated bundle changes match the source build.

**Verification Checks:**
- `(cd server && uv run --extra dev python -m pytest -m 'not live')`
- `(cd server/web && npm test)`
- `(cd server/web && npm run build -- --outDir /tmp/refract-metadata-dashboard-baseline)`
- `bash plugin/tests/test-session-start.sh`
- `bash plugin/tests/test-contracts.sh`
- `diff -r server/src/refract/dashboard_static /tmp/refract-metadata-dashboard-baseline`

## Final Acceptance and Handoff

Rerun all Phase 4 verification commands at the final checkpoint. Compare isolated build output with packaged dashboard files. Inspect the final diff against the plan base and classify every remaining legacy-token match: migration input, provider payload, explicit rejection test, or historical document. Production metadata fallbacks are not an allowed category.

Do not deploy intermediate phases. Server contract changes precede client updates in this worktree; the complete plan is the deployable unit. Update server, plugin, and dashboard together after operator backup and shutdown.

Require specification PASS and independent quality PASS for every phase, or explicitly owned non-blocking debt. Record actual check output, counts, and limitations in phase journals. Consolidate the plan only after acceptance, then verify the final revision and clean tree. Execution requires separate user approval of this plan.
