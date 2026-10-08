# Refract Monorepo Design

**Status:** Confirmed 2026-10-08
**Consultation:** skipped - target had no Git repo during design; every decision is user-owned and confirmed in dialogue

## Purpose

Combine the `superpowers-ccg` Claude Code / Codex plugin and the `openmcp` MCP
server into one repository and one product named `refract`, with a clean
layout and a full rename.

## Users and Success Criteria

Users: the maintainer (`sitien173`) and plugin users who install from the
marketplace.

Success criteria:

1. `~/projects/refract` holds both codebases with full `main` history of each
   source repo. `git log --follow` on any imported file reaches its original
   first commit.
2. Layout matches "Architecture and Data Flow" below.
3. Every live name follows the rename map. A case-insensitive search for
   `openmcp|superpowers|ccg` outside `docs/plans/` returns only the README
   lineage and migration lines, the CHANGELOG lineage line, and the legacy-name
   guard patterns in `plugin/tests/test-contracts.sh`. Substring matches inside
   opaque integrity hashes or compressed image bytes are not product names;
   retain the hash values and verify decoded diagram labels separately.
4. All existing suites pass under the new names: plugin contract tests,
   `claude plugin validate` for the marketplace and the plugin, server pytest,
   `uv build`, dashboard vitest, and dashboard build.
5. README documents the manual state move from `~/.openmcp` to `~/.refract`.

## Constraints and Non-Goals

Constraints:

- Source repos `~/projects/superpowers-ccg` and `~/projects/openmcp` stay
  untouched.
- Historical `docs/plans/` content imported from openmcp stays verbatim.
- No push and no remote configuration.

Non-goals:

- Importing non-`main` branches.
- Importing superpowers-ccg's untracked `docs/plans/` and `docs/reviews/`.
- Migration code. State moves by documented manual steps only.
- Running the migration on the maintainer's machine. This covers `~/.openmcp`,
  Claude settings, and env vars.
- Behavior changes beyond names: tool names, workflows, port `8765`, DB schema,
  and backend adapters stay the same.

## Chosen Approach

Two self-contained subprojects, `plugin/` and `server/`, under one root that
owns the marketplace, CI, docs, license, and product README. History is
imported with `git filter-repo` path rewrites and unrelated-history merges.

Rejected:

- Plugin at repo root: plugin installs would copy the server and dashboard, and
  the root would mix two products.
- `packages/*`: JS monorepo convention with no workspace tool to justify it.
- Fresh copy without history: loses blame and `log --follow`.

## Architecture and Data Flow

```text
refract/
├── .claude-plugin/marketplace.json   # name "refract", plugin source "./plugin"
├── .github/workflows/
│   ├── plugin.yml                    # paths: plugin/**, runs plugin/tests/run.sh
│   ├── server.yml                    # paths: server/**, uv sync/pytest/build matrix
│   └── ai-pr-review.yml              # openmcp variant: label-based mode, checkout@v5
├── plugin/                           # ex superpowers-ccg
│   ├── .claude-plugin/plugin.json
│   ├── .codex-plugin/plugin.json
│   ├── .mcp.json                     # server key "refract", ${REFRACT_URL:-http://127.0.0.1:8765/mcp}
│   ├── commands/ hooks/ shared/ skills/ tests/
├── server/                           # ex openmcp, self-contained uv project
│   ├── pyproject.toml uv.lock README.md CLI_ARGUMENTS.md
│   ├── src/refract/ tests/
│   └── web/                          # dashboard, builds into src/refract/dashboard_static
├── docs/
│   ├── diagrams/                     # refract_* sources and exports
│   └── plans/                        # openmcp plan history, verbatim, plus refract plans
├── .gitignore                        # merged from both repos
├── CHANGELOG.md                      # 1.0.0 entry with lineage
├── LICENSE                           # MIT, covers both parts
└── README.md                         # product overview, install, migration, lineage
```

Runtime data flow is unchanged. Claude Code loads the plugin. The plugin's
`.mcp.json` points at the loopback HTTP daemon. The daemon runs jobs through
backend CLIs.

Rename map:

| Item | Old | New |
|---|---|---|
| Product display name | Superpowers CCG / OpenMCP | Refract |
| Plugin name | `superpowers-ccg` | `refract` |
| Marketplace name | `superpowers-ccg-marketplace` | `refract` |
| Skill namespace | `superpowers-ccg:<skill>` | `refract:<skill>` |
| Hook script | `superpowers-ccg-session-start.sh` | `refract-session-start.sh` |
| Coordinator entry skill | `using-superpowers` | `using-refract`; hook wording becomes product-neutral |
| Shared version marker | `ccg-shared-version` | `refract-shared-version` |
| MCP server key | `openmcp` | `refract` |
| MCP tool prefix | `mcp__plugin_superpowers-ccg_openmcp__` | `mcp__plugin_refract_refract__` |
| Plugin env var | `OPENMCP_URL` | `REFRACT_URL` |
| Git config key | `ccg.plans.tracking` | `refract.plans.tracking` |
| Python dist, package, CLI | `openmcp` | `refract` |
| Server env vars | `OPENMCP_HOME`, `OPENMCP_LOG_*` | `REFRACT_HOME`, `REFRACT_LOG_*` |
| State home and files | `~/.openmcp/openmcp.{db,log}` | `~/.refract/refract.{db,log}` |
| Project config | `.openmcp/config.toml` | `.refract/config.toml` |
| Dashboard | `openmcp-dashboard`, `.openmcp_dashboard` | `refract-dashboard`, `.refract_dashboard` |
| Diagrams | `openmcp_*` | `refract_*`, PNGs re-exported with `drawio` CLI |
| Versions | plugin 12.0.0, server 2.0.0, dashboard 1.2.0 | all 1.0.0 |
| homepage / repository | `github.com/sitien173/{superpowers-ccg,openmcp}` | `github.com/sitien173/refract` |

## Errors and Edge Cases

- Two `ai-pr-review.yml` files differ: keep openmcp's label-based review mode
  with `actions/checkout@v5`.
- openmcp tracks `.claude/.headroom_wrap_marker.json`, a tool artifact: drop it.
- openmcp has no license: root MIT `LICENSE` covers both parts.
- `mcp-v2-claude-code` plan exists in both repos: only openmcp's tracked copy is
  imported, so there is no collision.
- `openmcp.db` holds 76 `.openmcp/` mentions in `jobs`, `context_turns`,
  `events`, and `job_stream_events`. They are prompt and transcript text, not
  functional paths, so no DB rewrite is needed.
- This session runs the old plugin and daemon. Workers use them throughout.
  Cutover is the maintainer's manual step.

## Migration

Bootstrap, done before plan base `f79380a`:

1. Fresh `main` clones in `/tmp/refract-import/`.
2. `git filter-repo --to-subdirectory-filter plugin` on superpowers-ccg.
3. `--to-subdirectory-filter server`, then `--path-rename server/docs/:docs/`,
   on openmcp.
4. `git init -b main`, an empty init commit, then two
   `--allow-unrelated-histories` merges.

The imported blob sets matched both sources exactly.

Manual state move, documented in README and not executed by this plan:

1. Stop the old daemon.
2. `mv ~/.openmcp ~/.refract`, then rename `openmcp.db*` to `refract.db*` and
   `openmcp.log*` to `refract.log*`.
3. Move each project's `.openmcp/` to `.refract/`.
4. Per repo: `git config --local refract.plans.tracking "$(git config --local ccg.plans.tracking)"`.
5. Rename `OPENMCP_*` env vars to `REFRACT_*`.
6. In Claude settings, replace the `superpowers-ccg` marketplace and plugin with
   `refract`. Update permission entries naming
   `mcp__plugin_superpowers-ccg_openmcp__*` or `.openmcp`.

## Testing

| Phase | Work | Verification |
|---|---|---|
| 1 Layout | Root files, CI split, marketplace, `.gitignore`, LICENSE, artifact drop | `plugin/tests/run.sh`; `cd server && uv sync --all-extras --frozen && uv run pytest`; `cd server/web && npm ci && npm test`; `claude plugin validate .` |
| 2 Server rename | Package, CLI, env vars, state paths, project config, dashboard, web, tests, server docs, `uv.lock`, rebuilt `dashboard_static` | `uv sync --all-extras`, `uv run pytest`, `uv build`, `npm test`, `npm run build`, residual grep on `server/` |
| 3 Plugin, docs, diagrams | Manifests, hook, skills, shared, commands, `.mcp.json`, git config key, contract tests, diagrams, root README and CHANGELOG | `plugin/tests/run.sh`, `claude plugin validate .`, `claude plugin validate plugin`, repo-wide residual grep |

Each phase gets an independent review. Phases consolidate into one commit on
top of the import merges.

## Risks and Open Questions

- Risk: contract tests in `plugin/tests/test-contracts.sh` pin old names and
  forbidden-pattern lists. Phase 3 must update them to the new names, not
  delete them, and add a guard that fails on legacy names in workflow files.
- Risk: the first dashboard vitest run at plan base failed 1 of 203 tests, and
  three reruns passed 203 of 203. Treat a single failure as flaky only if an
  immediate rerun passes.
- Risk: a missed path string in the server only fails at runtime, for example
  `~/.openmcp` defaults or `.openmcp_dashboard`. The residual grep and pytest
  cover this.
- Risk: the `mcp__plugin_refract_refract__` prefix is redundant. The maintainer
  accepted it.
- Open: none.
