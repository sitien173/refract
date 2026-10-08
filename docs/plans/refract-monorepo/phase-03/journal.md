<!-- ccg-shared-version: 12.0.0 -->

# Phase 3: Journal: Plugin, diagrams, and product documentation rename

## META

- Plan: docs/plans/refract-monorepo/PLAN.md
- Implementation Profile: implement
- Consultation Profile: consult
- Review Profile: review
- Implementation Job: 382e6be2-b0df-49d0-83e8-ef48a0a30a6b; export fix f8bdaebb-57a3-45ab-b857-014e92011589
- Review Job: 58dfa930-cd55-4ce4-989f-6ffe72e458bc; export re-review ac2b668d-e414-48a0-94f4-2c7553555c3e
- Started: 2026-10-08T16:08:00+07:00
- Finished: 2026-10-08T17:03:26+07:00

## Consultation

- Job: d9788403-6673-4f96-8bc1-13d04fe88cdc
- Result: declared Phase 3 scope covers every live rename path.
- Preserve all existing contract guards and hook JSON/path-space behavior; rename manifest keyword and Codex interface fields as well as visible names.
- Installation syntax was verified from local CLI help. No publication is part of this plan.
- draw.io31.1.5 help confirms 1-based page indices:1Context,2Containers,3Components and PNG embedding/export flags. All five old PNGs have embedded source.
- Normal CLI help works; actual export is unverified. Xvfb and xvfb-run are available if a real display failure occurs. No undocumented flags or persistent configuration changes are required by current evidence.
- Verify rendered labels and embedded source after all five real exports.
- Read-only consultation left product files and HEAD unchanged. The only dirty path was the coordinator's saved consult job reference.

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase: 3 / Started: 2026-10-08T16:08:00+07:00 / Finished: 2026-10-08T16:30:37+07:00 / Plan dir: docs/plans/refract-monorepo
## SUMMARY
Completed the Refract 1.0.0 plugin, documentation, and diagram renames, including all five genuine draw.io PNG exports.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | `.claude-plugin/marketplace.json` | Marketplace and plugin entry renamed and versioned 1.0.0. |
| Modified | `plugin/.claude-plugin/plugin.json` | Refract name, description, URLs, keyword, and version. |
| Modified | `plugin/.codex-plugin/plugin.json` | Refract identity, URLs, interface name, and version. |
| Modified | `plugin/.mcp.json` | MCP server key `refract` and `REFRACT_URL`. |
| Modified | `plugin/README.md` | Refract descriptions, commands, skills, and verified conditional installation instructions. |
| Modified | `plugin/commands/brainstorm.md`, `plugin/commands/execute-plan.md`, `plugin/commands/write-plan.md` | Updated skill namespace and product references. |
| Modified | `plugin/hooks/hooks.json` | Registers renamed hook with the existing quoted dynamic plugin-root path. |
| Moved, modified | `plugin/hooks/superpowers-ccg-session-start.sh` → `plugin/hooks/refract-session-start.sh` | Product-neutral hook text and new skill references; preserved behavior and path-space support. |
| Modified | `plugin/shared/erp.md`, `plugin/shared/journal-template.md`, `plugin/shared/notes-template.md`, `plugin/shared/worker-contract.md` | Updated shared version markers to 1.0.0 and Refract references. |
| Modified | `plugin/skills/brainstorming/SKILL.md`, `plugin/skills/coordinating-multi-model-work/SKILL.md`, `plugin/skills/coordinating-multi-model-work/references/handover.md`, `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`, `plugin/skills/executing-plans/SKILL.md`, `plugin/skills/using-git-worktrees/SKILL.md` | Updated product names, namespace, environment variable, and Git config key. |
| Moved, modified | `plugin/skills/using-superpowers/SKILL.md` → `plugin/skills/using-refract/SKILL.md` | Renamed skill and frontmatter; updated namespace references. |
| Modified | `plugin/tests/test-contracts.sh` | Added RED/GREEN-proven case-insensitive legacy guard; updated expected names while retaining existing guards. |
| Modified | `plugin/tests/test-session-start.sh` | Updated hook path and retained the plugin-path-with-spaces test. |
| Moved, modified | `docs/diagrams/openmcp_c4_model.drawio` → `docs/diagrams/refract_c4_model.drawio` | Updated Refract source labels; preserved all geometry. |
| Moved, modified | `docs/diagrams/openmcp_c4_model.svg` → `docs/diagrams/refract_c4_model.svg` | Updated rendered and embedded source labels. |
| Moved, exported | `docs/diagrams/openmcp_c4_context.drawio.png` → `docs/diagrams/refract_c4_context.drawio.png` | Real draw.io export, page 1, embedded source. |
| Moved, exported | `docs/diagrams/openmcp_c4_container.drawio.png` → `docs/diagrams/refract_c4_container.drawio.png` | Real draw.io export, page 2, embedded source. |
| Moved, exported | `docs/diagrams/openmcp_c4_component.drawio.png` → `docs/diagrams/refract_c4_component.drawio.png` | Real draw.io export, page 3, embedded source. |
| Moved, modified | `docs/diagrams/openmcp_system_architecture.drawio` → `docs/diagrams/refract_system_architecture.drawio` | Updated product labels; preserved all geometry. |
| Moved, modified | `docs/diagrams/openmcp_system_architecture.svg` → `docs/diagrams/refract_system_architecture.svg` | Updated rendered and embedded source labels. |
| Moved, exported | `docs/diagrams/openmcp_system_architecture.drawio.png` → `docs/diagrams/refract_system_architecture.drawio.png` | Real draw.io export with embedded source. |
| Moved, modified | `docs/diagrams/openmcp_data_flow_diagram.drawio` → `docs/diagrams/refract_data_flow_diagram.drawio` | Added Refract client label; preserved all geometry. |
| Moved, modified | `docs/diagrams/openmcp_data_flow_diagram.svg` → `docs/diagrams/refract_data_flow_diagram.svg` | Updated rendered and embedded source label. |
| Moved, exported | `docs/diagrams/openmcp_data_flow_diagram.drawio.png` → `docs/diagrams/refract_data_flow_diagram.drawio.png` | Real draw.io export with embedded source. |
| Modified | `server/README.md` | Replaced the three deferred diagram links with existing Refract targets. |
| Created | `README.md` | Product overview, layout, installation, six manual migration steps, and lineage. |
| Created | `CHANGELOG.md` | Required 1.0.0 entry and source lineage. |
| Modified | `docs/plans/refract-monorepo/phase-03/notes.md` | Recorded five task decisions, RED/GREEN evidence, tests, and export verification. |
| Modified | `docs/plans/refract-monorepo/phase-03/journal.md` | Recorded metadata and this implementation response. |
## NOTES
- `docs/plans/refract-monorepo/phase-03/notes.md` (`## Task 1` through `## Task 5`, plus final verification).
## SPEC COMPLIANCE
- Meets Spec? WITH_DEBT — plugin, marketplace, Python, documentation, and diagram checks passed. The broad raw-byte grep also matches `ccG` inside an existing npm integrity hash and compressed context-PNG pixels; neither is legacy product text. No out-of-scope data or exported PNGs were altered to evade those false positives.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Coordinator Recovery

- Implementation job382e6be2-b0df-49d0-83e8-ef48a0a30a6b reported failed with no result text after writing product changes and a TASK_COMPLETE journal. Partial changes were retained and inspected, not reset.
- Fresh plugin suite and both manifests passed; exact server-cwd pytest passed546with3deselected; server residual openmcp search returned no matches.
- Two defects reproduced in isolated /tmp fixtures: README wildcard mv command failed with db/db-wal/db-shm files; root-marketplace legacy fixture passed because the new guard omitted that file.
- Installation docs also need the existing required configuration prerequisite before serve. Two test diagnostic messages still use the old product name outside guard patterns.
- Raw grep additionally matches an unchanged opaque npm integrity hash and PNG pixel bytes. These are not product names; altering integrity or rendered images to hide them is prohibited.
- Recovery instructions are in prompt.md; same declared file set and phase goal remain in force. One permitted retry will return corrected output and evidence.

# EXTERNAL RESPONSE
## META
- Phase: 3 / Started: 2026-10-08T16:31:00+07:00 / Finished: 2026-10-08T16:39:22+07:00 / Plan dir: docs/plans/refract-monorepo
## SUMMARY
Completed recovery corrections to the Refract 1.0.0 documentation and legacy guard, preserving the earlier plugin and diagram work.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | `.claude-plugin/marketplace.json` | Refract marketplace and plugin entry, version 1.0.0. |
| Modified | `plugin/.claude-plugin/plugin.json` | Refract identity, URLs, keyword, and version. |
| Modified | `plugin/.codex-plugin/plugin.json` | Refract identity, URLs, interface display name, and version. |
| Modified | `plugin/.mcp.json` | Refract MCP key and `REFRACT_URL`. |
| Modified | `plugin/README.md` | Refract plugin overview and conditional install commands. |
| Modified | `plugin/commands/brainstorm.md`, `plugin/commands/execute-plan.md`, `plugin/commands/write-plan.md` | Updated namespaces and product names. |
| Modified | `plugin/hooks/hooks.json` | Registers renamed hook with the quoted dynamic root path. |
| Moved, modified | `plugin/hooks/superpowers-ccg-session-start.sh` → `plugin/hooks/refract-session-start.sh` | Product-neutral wording and Refract skill references. |
| Modified | `plugin/shared/erp.md`, `plugin/shared/journal-template.md`, `plugin/shared/notes-template.md`, `plugin/shared/worker-contract.md` | Refract shared markers at 1.0.0. |
| Modified | `plugin/skills/brainstorming/SKILL.md`, `plugin/skills/coordinating-multi-model-work/SKILL.md`, `plugin/skills/coordinating-multi-model-work/references/handover.md`, `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`, `plugin/skills/executing-plans/SKILL.md`, `plugin/skills/using-git-worktrees/SKILL.md` | Updated namespaces, product names, and Git configuration key. |
| Moved, modified | `plugin/skills/using-superpowers/SKILL.md` → `plugin/skills/using-refract/SKILL.md` | Renamed entry skill and updated frontmatter/references. |
| Modified | `plugin/tests/test-contracts.sh` | Legacy guard now scans root marketplace; updated diagnostic messages and values while preserving existing guards. |
| Modified | `plugin/tests/test-session-start.sh` | Updated hook path; retained space-containing path coverage. |
| Moved, modified | `docs/diagrams/openmcp_c4_model.drawio` → `docs/diagrams/refract_c4_model.drawio` | Refract labels; geometry preserved. |
| Moved, modified | `docs/diagrams/openmcp_c4_model.svg` → `docs/diagrams/refract_c4_model.svg` | Updated SVG and embedded source labels. |
| Moved, exported | `docs/diagrams/openmcp_c4_context.drawio.png` → `docs/diagrams/refract_c4_context.drawio.png` | draw.io page 1 export with embedded source. |
| Moved, exported | `docs/diagrams/openmcp_c4_container.drawio.png` → `docs/diagrams/refract_c4_container.drawio.png` | draw.io page 2 export with embedded source. |
| Moved, exported | `docs/diagrams/openmcp_c4_component.drawio.png` → `docs/diagrams/refract_c4_component.drawio.png` | draw.io page 3 export with embedded source. |
| Moved, modified | `docs/diagrams/openmcp_system_architecture.drawio` → `docs/diagrams/refract_system_architecture.drawio` | Refract labels; geometry preserved. |
| Moved, modified | `docs/diagrams/openmcp_system_architecture.svg` → `docs/diagrams/refract_system_architecture.svg` | Updated SVG and embedded source labels. |
| Moved, exported | `docs/diagrams/openmcp_system_architecture.drawio.png` → `docs/diagrams/refract_system_architecture.drawio.png` | draw.io export with embedded source. |
| Moved, modified | `docs/diagrams/openmcp_data_flow_diagram.drawio` → `docs/diagrams/refract_data_flow_diagram.drawio` | Refract client label; geometry preserved. |
| Moved, modified | `docs/diagrams/openmcp_data_flow_diagram.svg` → `docs/diagrams/refract_data_flow_diagram.svg` | Updated SVG and embedded source label. |
| Moved, exported | `docs/diagrams/openmcp_data_flow_diagram.drawio.png` → `docs/diagrams/refract_data_flow_diagram.drawio.png` | draw.io export with embedded source. |
| Modified | `server/README.md` | Correct Refract diagram links. |
| Created, modified | `README.md` | Added required config prerequisite/link; replaced unsafe file globs with suffix-preserving migration prose; retained exact state move and six steps. |
| Created | `CHANGELOG.md` | Refract 1.0.0 entry and lineage. |
| Modified | `docs/plans/refract-monorepo/phase-03/notes.md` | Added recovery root-cause, fixture, and verification evidence. |
| Modified | `docs/plans/refract-monorepo/phase-03/journal.md` | Appended recovery response and updated phase finish time. |
## NOTES
- `docs/plans/refract-monorepo/phase-03/notes.md` (`## Task 1` through `## Task 5`, `## Recovery Findings`).
- Coordinator-owned modifications to `docs/plans/refract-monorepo/.handover.md`, `DESIGN.md`, `PLAN.md`, and `phase-03/prompt.md` were present at recovery start and left untouched.
## SPEC COMPLIANCE
- Meets Spec? YES — recovery defects are corrected, all suites and validators pass, and decoded PNG sources confirm Refract labels. Opaque hash/pixel substring hits are not product text, as clarified in the confirmed plan.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

# EXTERNAL RESPONSE
## META
- Phase: 3 review fix / Started: 2026-10-08T16:55:00+07:00 / Finished: 2026-10-08T17:03:26+07:00 / Plan dir: docs/plans/refract-monorepo
## SUMMARY
Re-exported all five Refract diagrams at scale 2, restoring their plan-base pixel dimensions without changing diagram sources or geometry.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Re-exported | `docs/diagrams/refract_c4_context.drawio.png` | Page 1, scale 2, embedded source; 1611×1105. |
| Re-exported | `docs/diagrams/refract_c4_container.drawio.png` | Page 2, scale 2, embedded source; 1305×1845. |
| Re-exported | `docs/diagrams/refract_c4_component.drawio.png` | Page 3, scale 2, embedded source; 2145×2105. |
| Re-exported | `docs/diagrams/refract_system_architecture.drawio.png` | Scale 2, embedded source; 1685×2085. |
| Re-exported | `docs/diagrams/refract_data_flow_diagram.drawio.png` | Scale 2, embedded source; 1405×1425. |
| Modified | `docs/plans/refract-monorepo/phase-03/notes.md` | Appended scaling commands and validation evidence. |
| Modified | `docs/plans/refract-monorepo/phase-03/journal.md` | Appended review-fix response and finish metadata. |
## NOTES
- `docs/plans/refract-monorepo/phase-03/notes.md` (`## Review Follow-up: PNG Export Resolution`).
## SPEC COMPLIANCE
- Meets Spec? YES — all five outputs match their prior dimensions and contain valid embedded Refract source; plugin tests, both validators, and naming checks pass.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Coordinator Verification

- Implementation job 382e6be2-b0df-49d0-83e8-ef48a0a30a6b attempt 2 succeeded; full terminal ERP read, NEXT TASK_COMPLETE.
- Fresh plugin/tests/run.sh passed both session-start and contract suites; root marketplace and plugin validators passed; git diff --check passed.
- Fresh server-cwd uv sync --all-extras and uv run pytest returned 546 passed, 3 deselected. Full output: /tmp/refract-phase03-coordinator-pytest.log.
- Copied root marketplace with description OpenMCP legacy fixture was correctly rejected with exit 1 and the legacy-product diagnostic. No live manifest was mutated.
- markitdown converted all five PNGs to temporary Markdown without text. Direct visual inspection and decoded embedded XML then confirmed Refract labels for all five exports. All three draw.io sources retain exactly the original mxGeometry elements; all SVGs parse and contain only current product labels.
- Every npm integrity value equals the plan-base value. Raw grep still matches an opaque ccG hash and compressed PNG bytes, not product names. No hash or image was altered to evade those matches.
- An initial namespace-check script incorrectly treated the documented brainstorm command as a skill. Corrected inspection verified every concrete namespace reference resolves to an existing skill or command.
- All server README diagram links resolve; six migration steps match DESIGN.md and remain documentation only. Residual server openmcp search prints nothing.
- Imported historical plans are unchanged. Changed paths match the declared phase scope plus coordinator-owned files; no source repositories or runtime state changed.

## Quality Review

# CODE QUALITY REVIEW
- Job: 58dfa930-cd55-4ce4-989f-6ffe72e458bc
- Range: refs/plans/refract-monorepo/phase-03/base..3453fa8086161b5187e370b907bfe1e722747a5c
- Status: PASS_WITH_DEBT
- Findings: LOW, all five PNG exports have approximately half the original dimensions. Owner: Phase 3 diagram task. Restore export scale while retaining embedded source and unchanged geometry.
- Scope checked: marketplace/plugin/Codex manifests, MCP wiring, hook and path-space behavior, skills/commands/shared markers, retained contract guards and root legacy fixture, all eleven diagrams, root documentation, six migration steps, historical-plan and path boundaries.
- No blocking correctness or security findings. Phase 2 diagram-link debt resolved. Full suites were not independently rerun; reviewer independently inspected the pinned diff and artifacts.
- Read-only integrity confirmed: HEAD remained 3453fa8086161b5187e370b907bfe1e722747a5c; only the coordinator's saved review-job reference changed.

## Review Follow-up

- One bounded fix batch will restore PNG resolution within the declared export scope. Do not change source geometry, text, SVGs, product behavior, or dependency data. Verify the supported draw.io scaling flag before use, re-export all five with embedded XML, then review only this delta.

## Export Re-review

# CODE QUALITY REVIEW
- Job: ac2b668d-e414-48a0-94f4-2c7553555c3e
- Range: 3453fa8086161b5187e370b907bfe1e722747a5c..b623e8bada85260cbedbfa2f69e07d928d0ed064
- Status: PASS
- Findings: none. The prior resolution debt is resolved.
- Scope checked: all five PNG exports and three authorized coordination files. Independent checks confirmed original dimensions, valid signatures and chunk checksums, and decoded models identical to the accepted checkpoint. Sources, SVGs, text, and geometry did not change.
- Fresh coordinator checks confirmed original dimensions and embedded Refract XML for every PNG, both plugin test suites, both manifest validators, and declared path boundaries.
- Read-only integrity confirmed: HEAD remained b623e8bada85260cbedbfa2f69e07d928d0ed064; only the coordinator's saved review-job reference changed. No project jobs remain active.

## Review Result

- Spec Status: PASS
- Quality Status: PASS
- Debt: none. Phase 2 diagram filenames and Phase 3 export resolution are resolved.

## Final Checkpoint

- Phase base ref: refs/plans/refract-monorepo/phase-03/base
- Phase implementation ref: refs/plans/refract-monorepo/phase-03/impl
- Plan commit ref: refs/plans/refract-monorepo/impl
- Reviewed product checkpoint: b623e8bada85260cbedbfa2f69e07d928d0ed064
- Final coordination state is checkpointed before consolidation. The coordinator runs all final checks at the sole plan commit and reports their output before claiming completion.
