# Plan: Refract Monorepo

Design: [DESIGN.md](DESIGN.md)

Turns the imported `plugin/` (ex superpowers-ccg) and `server/` (ex openmcp)
trees into one product named `refract`. Plan base `refs/plans/refract-monorepo/base`
is the merge commit that completed the history import. Phase 1 builds the root
layout under the old names. Phase 2 renames the server. Phase 3 renames the
plugin and writes product docs. Each phase leaves every suite green.

**Commit:** `feat(refract): unify superpowers-ccg and openmcp as refract 1.0.0`

Shared rules for every phase:

- Do not edit anything under `docs/plans/` except this plan's coordination files.
  Historical plans stay verbatim.
- Do not touch `~/.openmcp`, `~/.claude`, the source repos
  `~/projects/superpowers-ccg` and `~/projects/openmcp`, or any Git state.
- Use `git mv` for every rename and move so history follows.
- Run `uv sync --all-extras` in `server/` before `uv run pytest`.
- The dashboard vitest suite had one flaky failure at plan base. A single
  failure counts as flaky only if an immediate rerun passes 203 of 203.

---

### Phase 1: Root layout with marketplace, CI, license, and ignore rules

**Task Guide Input:** In a freshly merged monorepo holding a Claude Code plugin
under `plugin/` and a Python uv project with a Vite dashboard under `server/`,
lift repository-level files to the root without renaming anything. Distinct use
cases: a root Claude Code marketplace pointing at `./plugin`, path-filtered CI
workflows per subproject, one merged AI review workflow, one root license, one
merged root `.gitignore` and `.gitattributes`, and removal of a tracked tool
artifact. Plugin contract tests must read the marketplace from its new location.

**Goal:** The repository root owns marketplace, CI, license, and ignore rules,
and every existing suite still passes with old product names intact.

**Files:**
- Move: `plugin/.claude-plugin/marketplace.json` -> `.claude-plugin/marketplace.json`
- Move: `plugin/.github/workflows/validate.yml` -> `.github/workflows/plugin.yml`
- Move: `server/.github/workflows/test.yml` -> `.github/workflows/server.yml`
- Move: `server/.github/workflows/ai-pr-review.yml` -> `.github/workflows/ai-pr-review.yml`
- Move: `plugin/LICENSE` -> `LICENSE`
- Move: `plugin/.gitattributes` -> `.gitattributes`
- Delete: `plugin/.github/workflows/ai-pr-review.yml`
- Delete: `plugin/.gitignore`
- Delete: `server/.gitignore`
- Delete: `server/.claude/.headroom_wrap_marker.json`
- Create: `.gitignore`
- Modify: `plugin/tests/test-contracts.sh`

**Tasks:**
1. Move the marketplace to the root and set its single plugin entry
   `"source": "./plugin"`. Keep every other field and value unchanged. Update
   `plugin/tests/test-contracts.sh` so both marketplace references read the
   file from the plugin root's parent directory.
2. Move and adapt CI. `plugin.yml` triggers on `plugin/**` and its own path and
   runs `plugin/tests/run.sh`. `server.yml` triggers on `server/**` and its own
   path. It sets `defaults.run.working-directory: server` and points setup-uv
   `cache-dependency-glob` at `server/uv.lock`. Keep its OS matrix and steps.
   `ai-pr-review.yml` keeps openmcp's label-based `review-mode` expression and
   uses `actions/checkout@v5`. Delete the plugin copy.
3. Move `LICENSE` and `.gitattributes` to the root. `*.sh text eol=lf` must
   still match `plugin/**/*.sh`.
4. Create one root `.gitignore` as the union of `plugin/.gitignore` and
   `server/.gitignore`. Drop the three legacy openmcp lines `agymcp/`,
   `codexmcp/`, and `openmcp/uv.lock`. Delete both nested files and the tracked
   `server/.claude/.headroom_wrap_marker.json`.

**Acceptance Criteria:**
- `claude plugin validate .` passes and reports the root marketplace.
- `git ls-files plugin/.claude-plugin/marketplace.json plugin/.gitignore server/.gitignore server/.claude plugin/.github server/.github`
  prints nothing.
- `git status --porcelain --ignored server/.venv server/web/node_modules` shows
  both paths as ignored.
- `git diff --name-status -M refs/plans/refract-monorepo/phase-01/base` lists
  only the paths in this phase's file set.

**Reviewer Checklist:**
- Marketplace `source` is exactly `./plugin`, with no `..` and no backslash.
- `server.yml` would run from `server/`, and its path filters cannot skip a
  server change.
- No ignore pattern from either nested `.gitignore` was lost except the three
  named legacy lines.
- No file outside the listed set changed.

**Verification Checks:**
- `plugin/tests/run.sh`
- `claude plugin validate .`
- `cd server && uv sync --all-extras --frozen && uv run pytest`
- `cd server/web && npm test`

---

### Phase 2: Server, CLI, state paths, and dashboard renamed to refract

**Task Guide Input:** Rename a Python 3.12 uv package and its React/Vite
dashboard from `openmcp` to `refract` with no behavior change. Distinct use
cases are listed here. The import package moves `src/openmcp` to
`src/refract`. The distribution, console script, and version become `refract`
1.0.0. Environment variables `OPENMCP_HOME` and `OPENMCP_LOG_*` become
`REFRACT_HOME` and `REFRACT_LOG_*`. The default state home becomes `~/.refract`
with `refract.db` and `refract.log`. The per-project config moves from
`.openmcp/config.toml` to `.refract/config.toml`. `.openmcp_dashboard` becomes
`.refract_dashboard`. The MCP server name and instructions text become
Refract. The dashboard package becomes `refract-dashboard` 1.0.0 with UI text
updated. The lockfiles and the built `dashboard_static` are regenerated. Tests
and server docs follow every rename.

**Goal:** `server/` contains no `openmcp` or `OpenMCP` string except the three
README diagram link targets that Phase 3 renames, and every server suite passes.
The final plan retains the strict zero-legacy-name requirement.

**Files:**
- Move: `server/src/openmcp/` -> `server/src/refract/` (all files, including `dashboard_static/`)
- Modify: `server/pyproject.toml`, `server/uv.lock`
- Modify: every file under `server/src/refract/` that contains `openmcp` or
  `OpenMCP`: `__init__.py`, `cli.py`, `config.py`, `config_inspection.py`,
  `config_mutation.py`, `dashboard.py`, `database.py`, `drivers.py`,
  `execution.py`, `logging_setup.py`, `models.py`, `notifications.py`,
  `planning.py`, `processes.py`, `runtime.py`, `scheduler.py`, `server.py`,
  `streaming.py`, `workflows.py`, and `backends/{__init__,_shell,agy,claude,codex,pi}.py`
- Modify: `server/tests/*.py`, which covers every test module containing the
  old name, plus `conftest.py` and `orchestration_helpers.py`
- Modify: `server/web/index.html`, `server/web/package.json`,
  `server/web/package-lock.json`, `server/web/vite.config.js`,
  `server/web/src/api.js`, `server/web/src/api.test.js`,
  `server/web/src/App.test.jsx`, `server/web/src/components/Topbar.jsx`,
  `server/web/src/integration/dashboard-flow.test.jsx`,
  `server/web/src/screens/{ConfigHealth,ConfigHealth.test,Overview,Profiles.test,ProjectDetail.test,Projects}.jsx`
- Regenerate: `server/src/refract/dashboard_static/` via `npm run build`
- Modify: `server/README.md`, `server/CLI_ARGUMENTS.md`

**Tasks:**
1. `git mv server/src/openmcp server/src/refract`. Then update
   `pyproject.toml` with project name `refract`, version `1.0.0`, script
   `refract = "refract.cli:main"`, and hatch `packages` and `artifacts` paths.
   Rename all imports, `openmcp_home`/`_openmcp_home` helpers, env vars, default
   home, db and log file names, project config dir, dashboard marker, MCP
   server name, and `_INSTRUCTIONS` text. Run `uv lock` to refresh `uv.lock`.
2. Update every server test for the new package, env vars, paths, and strings.
   Do not weaken or delete assertions.
3. Rename the dashboard package to `refract-dashboard` 1.0.0, update UI text,
   `index.html` title, API paths or strings that name openmcp, `vite.config.js`
   `outDir` to `../src/refract/dashboard_static`, and the tests. Run
   `npm install` to refresh `package-lock.json`, then `npm run build`.
4. Update `server/README.md` and `server/CLI_ARGUMENTS.md` to the new names,
   commands, env vars, and paths.

**Acceptance Criteria:**
- `grep -rniE 'openmcp' server --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=__pycache__ --exclude-dir=.pytest_cache`
  matches only the three `server/README.md` diagram link targets under
  `../docs/diagrams/openmcp_*` until Phase 3 resolves them. No other match is allowed.
- `cd server && uv run refract --help` exits 0.
- Default state home resolves to `~/.refract` when `REFRACT_HOME` is unset, and
  `OPENMCP_HOME` is no longer read.
- Test count is unchanged from plan base: 546 passed, 3 deselected.

**Reviewer Checklist:**
- No behavior change beyond names: port, tool names, workflows, DB schema, and
  backend argv are identical.
- No leftover dual-read of old env vars or old paths. The design rules out
  migration code.
- `dashboard_static` was rebuilt from source, not hand-edited.
- No test assertion was weakened or removed.

**Verification Checks:**
- `cd server && uv sync --all-extras && uv run pytest`
- `cd server && uv build`
- `cd server && uv run refract --help`
- `cd server/web && npm test`
- `cd server/web && npm run build`
- `grep -rniE 'openmcp' server --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=__pycache__ --exclude-dir=.pytest_cache`
  must match only the three deferred README diagram targets in Phase 2, and
  must print nothing after Phase 3.

---

### Phase 3: Plugin, diagrams, and product docs renamed to refract

**Task Guide Input:** Rename a Claude Code and Codex plugin from
`superpowers-ccg` to `refract` 1.0.0, matching a server already renamed to
`refract`. Distinct use cases are listed here. The plugin, marketplace, and
Codex manifest names, versions, display names, and URLs change to
`https://github.com/sitien173/refract`. The MCP server key becomes `refract`
and the URL env var becomes `REFRACT_URL`. The tool prefix becomes
`mcp__plugin_refract_refract__`. The skill namespace becomes `refract:` and the
`using-superpowers` skill is renamed to `using-refract`. The session-start hook
script and its wording change. The git config key `ccg.plans.tracking`
becomes `refract.plans.tracking`. The `ccg-shared-version` marker becomes
`refract-shared-version`. Contract tests follow every rename and gain a
legacy-name guard. Diagrams are renamed and re-exported. The root README and
CHANGELOG are written.

**Goal:** A repo-wide search finds legacy names only in the allowed places, and
the plugin and marketplace validate.

**Files:**
- Modify: `.claude-plugin/marketplace.json`
- Modify: `plugin/.claude-plugin/plugin.json`, `plugin/.codex-plugin/plugin.json`, `plugin/.mcp.json`
- Move: `plugin/hooks/superpowers-ccg-session-start.sh` -> `plugin/hooks/refract-session-start.sh`
- Modify: `plugin/hooks/hooks.json`, `plugin/hooks/refract-session-start.sh`
- Move: `plugin/skills/using-superpowers/` -> `plugin/skills/using-refract/`
- Modify: `plugin/skills/using-refract/SKILL.md`, `plugin/skills/brainstorming/SKILL.md`,
  `plugin/skills/coordinating-multi-model-work/SKILL.md`,
  `plugin/skills/coordinating-multi-model-work/references/{handover,tool-contract}.md`,
  `plugin/skills/executing-plans/SKILL.md`, `plugin/skills/using-git-worktrees/SKILL.md`,
  and any other `plugin/skills/**` file naming a renamed item
- Modify: `plugin/shared/{erp,journal-template,notes-template,worker-contract}.md`
- Modify: `plugin/commands/{brainstorm,execute-plan,write-plan}.md`
- Modify: `plugin/tests/test-contracts.sh`, `plugin/tests/test-session-start.sh`
- Modify: `plugin/README.md`, `server/README.md` (diagram links only)
- Move and modify: `docs/diagrams/openmcp_*` -> `docs/diagrams/refract_*`, with
  diagram text updated in `.drawio` and `.svg` sources and PNGs re-exported
- Create: `README.md`, `CHANGELOG.md`

**Tasks:**
1. Manifests and wiring: set name `refract`, version `1.0.0`, Refract display
   text, and the new homepage and repository URLs in all three manifests. Set
   marketplace `name` to `refract`. Change the `.mcp.json` key to `refract` and
   its URL to `${REFRACT_URL:-http://127.0.0.1:8765/mcp}`. Rename the hook
   script, update `hooks.json`, and make the hook text product-neutral using
   `refract:` skill names.
2. Skills, shared, and commands: `git mv` the `using-superpowers` skill to
   `using-refract` and update its front-matter `name`. Replace every
   `superpowers-ccg:` reference with `refract:`, every old tool prefix with
   `mcp__plugin_refract_refract__`, `ccg.plans.tracking` with
   `refract.plans.tracking`, `ccg-shared-version` with `refract-shared-version`,
   and OpenMCP product mentions with Refract.
3. Contract tests: update `test-contracts.sh` and `test-session-start.sh` to
   the new names, the `1.0.0` version assertion, the `refract` MCP key and
   `REFRACT_URL`, and the renamed skill path. Keep every existing guard. Add one
   guard that fails when `openmcp`, `superpowers`, or `ccg`
   (case-insensitive) appears in `commands`, `hooks`, `shared`, `skills`, or
   the plugin manifests.
4. Docs and diagrams: `git mv` each `docs/diagrams/openmcp_*` file to
   `refract_*`. Replace diagram text in the `.drawio` and `.svg` sources.
   Re-export PNGs with
   `drawio -x -f png -e -p <1|2|3> -o docs/diagrams/refract_c4_{context,container,component}.drawio.png docs/diagrams/refract_c4_model.drawio`
   and `drawio -x -f png -e -o <name>.drawio.png <name>.drawio` for the
   other two sources. Fix diagram links in `server/README.md`. Write root
   `README.md` covering product overview, layout, install of plugin and
   server, the six manual migration steps from DESIGN.md, and a lineage
   note. Write `CHANGELOG.md` with a `1.0.0 - 2026-10-08` entry and lineage
   from superpowers-ccg 12.0.0 and openmcp 2.0.0.

**Acceptance Criteria:**
- `claude plugin validate .` and `claude plugin validate plugin` pass.
- `plugin/tests/run.sh` passes, including the new legacy-name guard.
- `git grep -niE 'openmcp|superpowers|ccg' -- ':!docs/plans'` matches only
  `README.md` lineage and migration lines, the `CHANGELOG.md` lineage line, and
  guard patterns in `plugin/tests/test-contracts.sh` as product text. Opaque npm
  integrity hashes and compressed PNG bytes are not product names. Verify the
  integrity value is unchanged, and decode embedded diagram XML to check labels
  instead of altering data to evade raw-byte substring matches.
- Every PNG under `docs/diagrams/` was re-exported in this phase and shows
  Refract naming.

**Reviewer Checklist:**
- Skill cross-references resolve: every `refract:<skill>` names an existing
  `plugin/skills/<skill>/` directory.
- Hook output still matches what `test-session-start.sh` asserts, including the
  plugin path containing spaces.
- Migration steps in `README.md` match DESIGN.md exactly and are documentation
  only.
- No historical `docs/plans/` file changed.

**Verification Checks:**
- `plugin/tests/run.sh`
- `claude plugin validate .`
- `claude plugin validate plugin`
- `cd server && uv run pytest`
- `git grep -niE 'openmcp|superpowers|ccg' -- ':!docs/plans'`
