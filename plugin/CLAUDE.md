# CLAUDE.md

Project pointers for Claude Code. Workflow, routing, and review semantics live in `skills/coordinating-multi-model-work/SKILL.md` — load it before any Plan / Execute / Review action.

## Skills (`superpowers-ccg:` namespace)

- `coordinating-multi-model-work` — canonical 3-gate workflow, routing, review, resume artifacts. **Load first.**
- `brainstorming` — new features and configured consultation.
- `writing-plans` — design → phase-based plan.
- `executing-plans` — run a plan one phase at a time.
- `test-driven-development` — failing test first, then minimal code (feature/bugfix work).
- `systematic-debugging` — root cause before any fix (bugs / test failures).
- `verifying-before-completion` — fresh evidence before reporting done.

## Slash commands

- `/superpowers-ccg:brainstorm`
- `/superpowers-ccg:write-plan`
- `/superpowers-ccg:execute-plan`

## Project-specific rules

- Long prompts → write under `docs/plans/`. Submit a thin pointer.
- OpenMCP runs as a local HTTP daemon. Detailed setup is in `README.md`.
- The agent loading the workflow becomes Coordinator.
- Follow `setup_instruction`; register only an absent, clean root.
- Use `task_route`; Coordinator chooses agent nicknames.
- Submit built-in `implement`, `consult`, or `review` workflows.
- Read effective project routing profiles before selection.
- Existing phase chains retain stored routing decisions.
- Use compact job waits. Read only `job.result.text`.
- Resume through project jobs. Never expose provider identities.

## Install / update

- Install MCPs: see `README.md`.
- Update plugin: `claude plugin update superpowers-ccg`.
