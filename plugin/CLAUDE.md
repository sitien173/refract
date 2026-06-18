# CLAUDE.md

Project pointers for Claude Code. Workflow, routing, and review semantics live in `skills/coordinating-multi-model-work/SKILL.md` — load it before any Plan / Execute / Review action.

## Skills (`superpowers-ccg:` namespace)

- `coordinating-multi-model-work` — canonical 3-gate workflow, routing, review, resume artifacts. **Load first.**
- `brainstorming` — new features / ideation (Cross-Validation only if full-stack / unclear / high-impact).
- `writing-plans` — design → phase-based plan.
- `executing-plans` — run a plan one phase at a time.
- `test-driven-development` — failing test first, then minimal code (feature/bugfix work).
- `systematic-debugging` — root cause before any fix (bugs / test failures).
- `verifying-before-completion` — fresh evidence before reporting done.

## Slash commands

- `/superpowers-ccg:brainstorm`
- `/superpowers-ccg:prd` — rough requirements → research-backed PRD
- `/superpowers-ccg:write-plan`
- `/superpowers-ccg:execute-plan`
- `/superpowers-ccg:setup-openmcp-env` — configure `OPENMCP_*` env vars → `~/.openmcp/.env`

## Project-specific rules

- Long prompts → write to a repo file under `docs/plans/` and pass the absolute path.
- MCP backends: `codex` (back-side), `agy` (front-side). Detailed setup in `README.md`.

## Install / update

- Install MCPs: see `README.md`.
- Update plugin: `claude plugin update superpowers-ccg`.
