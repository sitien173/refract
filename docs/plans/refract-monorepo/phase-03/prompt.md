## User Request
Complete the confirmed refract-monorepo plan. Phases 1 and 2 are reviewed. Finish the plugin, diagrams, and documentation rename to Refract 1.0.0, resolving the three deferred server README diagram filenames.

## Phase
Phase 3: every live product name is Refract; root marketplace and plugin validate; docs describe installation and manual migration; all diagram PNGs are re-exported from renamed draw.io sources.

## Tasks
- task-1: Manifest and wiring rename. Set root marketplace name `refract`, plugin entry name `refract`, version `1.0.0`, and Refract descriptions. Set Claude and Codex manifests to `refract` version `1.0.0`, appropriate Refract display text, homepage/repository `https://github.com/sitien173/refract`. Keep marketplace source `./plugin`. `.mcp.json` server key becomes `refract` and URL `${REFRACT_URL:-http://127.0.0.1:8765/mcp}`. Move hook `superpowers-ccg-session-start.sh` to `refract-session-start.sh` with git mv, update hooks.json and product-neutral hook text while preserving hook behavior and support for paths with spaces.
- task-2: Move `plugin/skills/using-superpowers/` to `plugin/skills/using-refract/` with git mv; rename frontmatter name and entry references. Replace all old namespaces with `refract:`, old tool prefix with `mcp__plugin_refract_refract__`, `ccg.plans.tracking` with `refract.plans.tracking`, shared marker with `refract-shared-version: 1.0.0`, old environment/paths/product names with their confirmed Refract counterparts in every plugin skill, reference, shared document, and command. Skill references must resolve to existing directories. No workflow/process redesign or unrelated edits.
- task-3: Update plugin contract and session-start tests to new names/version1.0.0/MCP key/REFRACT_URL/hook/skill paths. Keep every existing guard. Add a case-insensitive legacy-name guard for `openmcp|superpowers|ccg` in commands, hooks, shared, skills, and manifests. Write and demonstrate this guard failing against the pre-rename plugin, then make the minimal names-only changes to pass. Demonstrate the guard fails on a deliberately legacy-named fixture without leaving fixture files in the repository. Retain the hook test for plugin paths with spaces.
- task-4: Git mv all `docs/diagrams/openmcp_*` to `refract_*`. Update names and paths in draw.io and SVG source text, preserving all existing diagram components, geometry, layout, and meaning. Re-export every diagram PNG with drawio CLI, embedding source as planned. C4 context/container/component pages use the correct existing page indices, verified by source and CLI help. The confirmed plan shows `drawio -x -f png -e -p <1|2|3> -o docs/diagrams/refract_c4_{context,container,component}.drawio.png docs/diagrams/refract_c4_model.drawio`; validate actual page indexing before invoking. Other sources use `drawio -x -f png -e -o <name>.drawio.png <name>.drawio`. Preserve all diagram formats; do not replace with new diagram styles or hand-edit PNGs. Record export commands and results in notes. Update the three server/README.md diagram links to renamed files, resolving Phase 2 debt.
- task-5: Rename plugin README text and add root README.md covering Refract overview, layout, plugin and server installation, six exact manual migration steps from DESIGN.md, and lineage. Create CHANGELOG.md entry `1.0.0 - 2026-10-08`, with lineage from superpowers-ccg12.0.0 and openmcp2.0.0. Preserve exact migration commands/identifiers and keep migration documentation-only. Read current manifests/docs and verify installation syntax before describing it. No fabricated release or remote publication claims.

## Context
- Authoritative scope and design: Phase 3 in PLAN.md and DESIGN.md.
- Current product server already uses `refract`1.0.0, REFRACT_HOME/REFRACT_LOG_*, .refract, X-Refract-CSRF; backend behavior and seven MCP tools remain unchanged.
- Installed coordinator plugin and running daemon remain old names throughout this session. Do not cut over or edit source repos, home state, settings, permissions, or env configuration.
- Phase 2 debt is only three server README links currently `../docs/diagrams/openmcp_system_architecture.drawio.png`, `../docs/diagrams/openmcp_c4_model.svg`, and `../docs/diagrams/openmcp_data_flow_diagram.drawio.png`. All targets currently exist.
- Existing drawio CLI is `/home/ngosi/.local/bin/drawio`, linked to executable `/home/ngosi/AppImages/drawio.appimage`. Export functionality is not yet verified. Inspect errors and help before alternatives; use a supported headless route without adding dependencies or modifying user/system settings.
- Current baseline: plugin suite passed before this phase; Python546passed3deselected; dashboard203passed. Dashboard known single-test timing failure only counts as flaky if immediate full rerun passes203.
- All historical docs/plans remain verbatim. The new plan's coordination files intentionally retain historical request identifiers and are excluded from final legacy search.
- This is names-only refactoring and documentation, not a feature expansion. Preserve all guards and workflow semantics.

## Consultation Findings
- Scope covers all live rename paths. Preserve every existing test guard, including forbidden-pattern expressions with historical names in test-contracts.sh.
- Claude manifest keyword `openmcp-profiles` must also become `refract-profiles`; update Codex interface.websiteURL and interface.displayName.
- Hook registration must retain quoted `${CLAUDE_PLUGIN_ROOT}` path, SessionStart matcher, timeout, dynamic path resolution, JSON escaping, and both normal and space-containing path tests.
- Installed Claude help confirms `claude plugin marketplace add sitien173/refract` and `claude plugin install refract@refract`; document these only as installation commands once published. This plan does not publish or push. Local marketplace install is supported via local path, but verify before describing it.
- Installed draw.io31.1.5 help confirms page indexing is 1-based:1Context,2Containers,3Components. The planned PNG export flags and embedded-source flag are correct.
- `xvfb-run` and `Xvfb` are installed. Normal help works with nonfatal graphics warnings. Attempt the documented export first; if actual display initialization fails, use `xvfb-run -a drawio` without undocumented flags or persistent configuration changes.
- All five PNGs include compressed embedded source. Verify each rebuilt PNG signature, embedded updated XML labels, and rendered Refract text. Compare layout against original; no component/geometry changes.
- Use `markitdown` first when reading/extracting image or other document content. Put Markdown in /tmp and inspect conversion errors before alternatives. Embedded PNG source metadata may then require direct chunk inspection; do not hand-edit exported PNGs.

## Files
- `.claude-plugin/marketplace.json`.
- `plugin/.claude-plugin/plugin.json`, `plugin/.codex-plugin/plugin.json`, `plugin/.mcp.json`.
- Move and modify hook script plus `plugin/hooks/hooks.json`.
- Move `plugin/skills/using-superpowers/` to `using-refract/`; modify any plugin/skills file containing renamed names, versions, or cross-references.
- `plugin/shared/{erp,journal-template,notes-template,worker-contract}.md`.
- `plugin/commands/{brainstorm,execute-plan,write-plan}.md`.
- `plugin/tests/test-contracts.sh`, `plugin/tests/test-session-start.sh`.
- `plugin/README.md`; `server/README.md` diagram links only.
- Every `docs/diagrams/openmcp_*` renamed to `refract_*` with text changes and generated PNG exports.
- New root `README.md`, `CHANGELOG.md`.
- Maintain phase03 `notes.md` and `journal.md`.

Out of scope: any other path, historical plans, running installed plugin/server state, source repos `/home/ngosi/projects/superpowers-ccg` and `/home/ngosi/projects/openmcp`, `/home/ngosi/.claude`, `/home/ngosi/.openmcp`, `/home/ngosi/.refract`. Do not change Git refs, commits, stash, configuration, branches, remotes, or push. Git mv is permitted only for declared renames. No actual state migration.

## Done When
- `plugin/tests/run.sh`: all contract/session-start checks pass including legacy guard.
- `claude plugin validate .` and `claude plugin validate plugin`: pass.
- `cd server && uv run pytest`:546passed3deselected.
- `git grep -niE 'openmcp|superpowers|ccg' -- ':!docs/plans'`: matches only root README lineage/migration, CHANGELOG lineage, and guard patterns in test-contracts.sh.
- Strict server residual grep excluding .venv, node_modules, __pycache__, .pytest_cache has no match.
- Every `refract:<skill>` cross-reference names an existing skill directory.
- Every PNG in docs/diagrams genuinely re-exported and carries Refract labels and embedded updated source. All renamed diagram sources/exports remain parseable and linked paths exist.
- Six manual migration steps match DESIGN.md exactly; no migration was run.
- No historical plan modified; diff contains only declared files.

## SKILLS
- Test-driven-development: `/home/ngosi/projects/superpowers-ccg/skills/test-driven-development/SKILL.md` for guard RED/GREEN and passing characterization for names-only changes.
- STOW public documentation: `/home/ngosi/.claude/skills/stow/SKILL.md` and `references/public-documentation.md`. Protect requested literals, use concrete concise prose, distinguish planned migration from executed state, no emojis, em dashes, or parenthetical prose clauses.
- Diagram-design was assessed and dropped: the user explicitly requires preserving existing draw.io diagrams and exporting them, not redesigning them or adding HTML artifacts.

## Recovery Findings
The first Phase 3 job failed after writing completed files/journal but returned no ERP text. Preserve the work and do not repeat completed moves. Resolve only these in-scope issues, then rerun verification and return ERP:
- README.md:38-40 documents `mv ~/.refract/openmcp.db* ~/.refract/refract.db*` and equivalent logs. A temporary home with db/db-wal/db-shm reproduced exit1: target `refract.db*` does not exist. Remove these invalid executable glob commands. Keep the exact state-directory mv command, then give explicit prose to rename each matching database/log file from old prefix to new prefix while preserving suffix. This implements DESIGN's manual instruction without unsafe shell expansion. No actual migration.
- Root install instructions run serve before creating its required config. Add a link to server README Configuration and explicit prerequisite to create ~/.refract/config.toml with installed targets, profiles, and default_profile before starting. Do not invent a generated default configuration.
- Legacy guard misses root .claude-plugin/marketplace.json. A temporary copied tree with marketplace description `OpenMCP legacy fixture` passed test-contracts.sh. Include `../.claude-plugin/marketplace.json` in the existing guard. Demonstrate that exact fixture fails after correction. Preserve all existing checks.
- test-contracts.sh still has two diagnostic printf messages naming OpenMCP, not guard patterns. Rename those diagnostic messages to Refract, retaining the guards.
- Broad raw-byte grep hits `ccG` in an unchanged npm integrity hash and compressed PNG pixels. Do not modify hashes or exports to dodge matches. Classify those as non-name data, document exact evidence, and verify all remaining textual product matches belong only to approved README/CHANGELOG lines and legacy guard expressions. The coordinator will clarify acceptance for opaque bytes without changing the final names-only design.

## Rules
Follow existing worker contract and ERP. Read files before changing. Stay within allowed file set, preserve assertions/guards/history, maintain notes/journal, do not commit. Report any blocking tool/export issue with command and exact error instead of claiming it passed. Verify APIs/CLI syntax from existing code/docs or official help; use ctx7 for unfamiliar library-specific questions and tvly only for public web access.

## Response Format
Return the full ERP `# EXTERNAL RESPONSE` and matching status line. Enumerate every modified path and export evidence.
