## User Request
Combine the superpowers-ccg plugin and the openmcp MCP server into one repository named refract. History is already imported: the plugin lives under `plugin/`, the server under `server/`, and openmcp docs under `docs/`. This phase lifts repository-level files to the root without renaming anything.

## Phase
Phase 1: the repository root owns marketplace, CI, license, and ignore rules, and every existing suite still passes with old product names intact.

## Tasks
- task-1: `git mv plugin/.claude-plugin/marketplace.json .claude-plugin/marketplace.json`; set its single plugin entry `"source": "./plugin"`; keep every other field and value unchanged. Update `plugin/tests/test-contracts.sh` so both marketplace references read `.claude-plugin/marketplace.json` from the plugin root's parent directory, for example `root.parent / ".claude-plugin/marketplace.json"`.
- task-2: CI. `git mv plugin/.github/workflows/validate.yml .github/workflows/plugin.yml`: trigger on push and pull_request with `paths: ["plugin/**", ".claude-plugin/**", ".github/workflows/plugin.yml"]`, run `plugin/tests/run.sh`. `git mv server/.github/workflows/test.yml .github/workflows/server.yml`: trigger with `paths: ["server/**", ".github/workflows/server.yml"]`, add `defaults: run: working-directory: server`, set setup-uv `cache-dependency-glob: server/uv.lock`, keep its OS matrix and steps. `git mv server/.github/workflows/ai-pr-review.yml .github/workflows/ai-pr-review.yml`, keep its label-based `review-mode` expression, and change `actions/checkout@v4` to `actions/checkout@v5`. `git rm plugin/.github/workflows/ai-pr-review.yml`.
- task-3: `git mv plugin/LICENSE LICENSE` and `git mv plugin/.gitattributes .gitattributes`. Its rule `*.sh text eol=lf` must still match `plugin/**/*.sh`.
- task-4: Create root `.gitignore` as the union of `plugin/.gitignore` and `server/.gitignore`, deduplicated, grouped with short comments. Drop exactly three legacy lines: `agymcp/`, `codexmcp/`, `openmcp/uv.lock`, plus their now-empty comment headers. Then `git rm plugin/.gitignore server/.gitignore server/.claude/.headroom_wrap_marker.json`.

## Context
- Root marketplace path resolution: Claude Code resolves a relative plugin `source` from the directory containing `.claude-plugin/`. `./plugin` is valid; `..` and backslashes are rejected.
- `plugin/tests/run.sh` derives `repo_root` as the plugin directory and calls `claude plugin validate "$repo_root"`, which validates `plugin/.claude-plugin/plugin.json` after the move. Leave run.sh unchanged.
- `plugin/tests/test-contracts.sh` loads JSON documents into a dict keyed by path, with `root` = plugin dir. It asserts plugin, marketplace, and codex versions are all `12.0.0`. Keep that assertion.
- Nested `.gitignore` patterns without a slash match at any depth, so moving them to the root keeps `.venv/`, `node_modules/`, `__pycache__/` and similar ignored under `server/` and `server/web/`.
- Use `git mv` / `git rm` so history follows. Do not commit.

## Files
- `.claude-plugin/marketplace.json` (moved from `plugin/.claude-plugin/marketplace.json`)
- `.github/workflows/plugin.yml` (moved from `plugin/.github/workflows/validate.yml`)
- `.github/workflows/server.yml` (moved from `server/.github/workflows/test.yml`)
- `.github/workflows/ai-pr-review.yml` (moved from `server/.github/workflows/ai-pr-review.yml`)
- `plugin/.github/workflows/ai-pr-review.yml` (delete)
- `LICENSE` (moved from `plugin/LICENSE`)
- `.gitattributes` (moved from `plugin/.gitattributes`)
- `.gitignore` (create)
- `plugin/.gitignore`, `server/.gitignore`, `server/.claude/.headroom_wrap_marker.json` (delete)
- `plugin/tests/test-contracts.sh`
- `docs/plans/refract-monorepo/phase-01/notes.md`, `docs/plans/refract-monorepo/phase-01/journal.md`

Out of scope: every other path. Never edit historical `docs/plans/` folders. Never touch `~/.openmcp`, `~/.claude`, `~/projects/superpowers-ccg`, `~/projects/openmcp`, or Git refs, commits, stash, or config.

## Done When
- `claude plugin validate .` passes from the repo root and reports the root marketplace.
- `git ls-files plugin/.claude-plugin/marketplace.json plugin/.gitignore server/.gitignore server/.claude plugin/.github server/.github` prints nothing.
- `git status --porcelain --ignored server/.venv server/web/node_modules` shows both as ignored (`!!`).
- `git diff --name-status -M HEAD` lists only the paths in Files.
- `plugin/tests/run.sh`
- `cd server && uv sync --all-extras --frozen && uv run pytest` gives 546 passed, 3 deselected.
- `cd server/web && npm test` gives 203 passed. A single failure counts as flaky only if an immediate rerun passes 203 of 203.

## SKILLS
- none

## Rules
Follow the supplied worker contract, project conventions, and the ERP format. Do not edit files outside the allowed set. Stay within scope. Maintain this phase's `notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
