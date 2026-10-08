## User Request
Complete the confirmed refract-monorepo plan. Phase 1 root layout is reviewed and complete. Rename the Python server and dashboard from openmcp to refract without changing behavior beyond names.

## Phase
Phase 2: server package, CLI, state paths, project configuration, dashboard, tests, and server docs use Refract. All existing suites pass with unchanged test coverage.

## Tasks
- task-1: Establish passing characterization coverage before changes. Move `server/src/openmcp` to `server/src/refract` using `git mv`. Update Python distribution and package, version to `1.0.0`, console script `refract = "refract.cli:main"`, hatch package and artifact paths, every import and identifier naming openmcp, helpers `openmcp_home` and `_openmcp_home`, environment variables to `REFRACT_HOME` and `REFRACT_LOG_*`, default state home `~/.refract`, database and log filenames `refract.db` and `refract.log`, project directory `.refract`, dashboard marker `.refract_dashboard`, and MCP display/instructions to Refract. Run `uv lock` and `uv sync --all-extras` in server.
- task-2: Rename corresponding imports, env variables, filesystem paths, and expected text in every server test. Keep every assertion and test, except name substitutions explicitly required by the design. No compatibility aliases, old env reads, migration code, schema changes, tool renames, workflow changes, port changes, or backend argument changes.
- task-3: Rename dashboard package to `refract-dashboard` version `1.0.0`, update UI text, index title, matching API strings/tests, and Vite output directory `../src/refract/dashboard_static`. Use `npm install` to regenerate package-lock.json, then `npm run build` to regenerate static assets. This is a names-only dashboard change, not UI redesign.
- task-4: Update server/README.md and server/CLI_ARGUMENTS.md with new names, commands, paths, env variables, repository URLs, and version references. Retain all documentation of existing behavior and dashboard security boundaries. Diagram filenames remain old until Phase 3, so preserve their links in this phase only if needed; document any exact residual naming conflict to the coordinator before claiming complete.

## Context
- Confirmed design and complete allowed file set: `docs/plans/refract-monorepo/DESIGN.md` and Phase 2 in `PLAN.md`.
- The current checkout is the implementation workspace. Do not create a worktree or branch.
- This session still uses the old installed plugin and daemon. Never rename or change their running state.
- Fresh Phase 1 baseline: 546 Python tests passed, 3 deselected; 203 dashboard tests passed. Run Python tests with working directory `server/`: one test reads README.md relative to cwd.
- Characterization applies to this behavior-preserving rename. Record passing baseline, the intended names-only substitutions, and passing suites. Keep test counts unchanged.
- A dashboard single-test failure is considered flaky only when an immediate complete rerun passes all 203 tests; record both results.
- Generated dashboard files must come from the dashboard build, not manual substitution.
- Historical plans remain verbatim. No test coverage weakening and no adjacent refactoring.

## Consultation Findings
- All 64 tracked server files with old names fit the declared file set.
- Also rename `.openmcp/task_guide.json`, `.openmcp/task_routes.json`, temporary directory/file prefixes, error class `OpenMCPError`, logger namespaces, and app-state attribute `openmcp_dashboard`. The dashboard marker is an app-state attribute, not a new filesystem marker.
- Rename server and client CSRF header together: `x-openmcp-csrf` / `X-OpenMCP-CSRF` to `X-Refract-CSRF`, with all related tests. Preserve every security boundary and API route.
- `test_smoke.py` checks distribution and version, so update its name/version assertions, not test count.
- Review generated lock diffs to avoid dependency upgrades in this names-only release.
- The three server README diagram links are already broken after import because their prefix is `docs/diagrams/` instead of `../docs/diagrams/`. Fix that prefix in Phase 2 and retain only those three `openmcp_*` filenames until their authorized Phase 3 rename. These exact link-target matches are the sole temporary nonblocking naming deferral. Do not claim a fully clean residual search in Phase 2.
- Drawio CLI is installed for Phase 3, but exports have not been exercised.

## Files
- Move `server/src/openmcp/` to `server/src/refract/`, including static assets.
- Modify `server/pyproject.toml`, `server/uv.lock`.
- Modify renamed source files containing old names: `__init__.py`, `cli.py`, `config.py`, `config_inspection.py`, `config_mutation.py`, `dashboard.py`, `database.py`, `drivers.py`, `execution.py`, `logging_setup.py`, `models.py`, `notifications.py`, `planning.py`, `processes.py`, `runtime.py`, `scheduler.py`, `server.py`, `streaming.py`, `workflows.py`, and `backends/{__init__,_shell,agy,claude,codex,pi}.py`.
- Modify `server/tests/*.py` for name substitutions only.
- Modify `server/web/index.html`, `server/web/package.json`, `server/web/package-lock.json`, `server/web/vite.config.js`, `server/web/src/api.js`, `server/web/src/api.test.js`, `server/web/src/App.test.jsx`, `server/web/src/components/Topbar.jsx`, `server/web/src/integration/dashboard-flow.test.jsx`, `server/web/src/screens/{ConfigHealth,ConfigHealth.test,Overview,Profiles.test,ProjectDetail.test,Projects}.jsx`.
- Regenerate `server/src/refract/dashboard_static/` with npm run build.
- Modify `server/README.md`, `server/CLI_ARGUMENTS.md`.
- Maintain `docs/plans/refract-monorepo/phase-02/notes.md` and `journal.md`.

Out of scope: every other path; all other docs/plans folders; source repositories `/home/ngosi/projects/superpowers-ccg` and `/home/ngosi/projects/openmcp`; `/home/ngosi/.openmcp`, `/home/ngosi/.refract`, `/home/ngosi/.claude`; Git refs, commits, stash, reset, configuration, push, remotes. `git mv` is allowed solely for the declared package move.

## Done When
- `cd server && uv sync --all-extras && uv run pytest`: 546 passed, 3 deselected.
- `cd server && uv build`: exit 0.
- `cd server && uv run refract --help`: exit 0.
- `cd server/web && npm test`: 203 passed.
- `cd server/web && npm run build`: exit 0.
- Case-insensitive residual search for openmcp under server excluding .venv, node_modules, __pycache__, .pytest_cache returns no product code matches. Report any remaining required old diagram filenames rather than silently breaking links.
- Default home uses `~/.refract` when REFRACT_HOME is unset, and OPENMCP_HOME is not read.
- Allowed-file diff only. No old package path remains. Assertions, tool names, workflows, DB schema, backend argv and port remain unchanged except name substitutions.

## SKILLS
- Test-driven-development: `/home/ngosi/projects/superpowers-ccg/skills/test-driven-development/SKILL.md`; use passing characterization coverage for the names-only refactor.

## Rules
Follow the supplied worker contract, project conventions, and ERP format. Stay within the declared file set. Maintain notes and journal. Read files before changing them. Do not commit. Return clarifications before making any required out-of-scope change.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
