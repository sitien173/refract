# CLAUDE.md

Load `skills/coordinating-multi-model-work/SKILL.md` before any Plan, Execute,
Review, or resume action. It is the canonical workflow and handover contract.

## Skills (`superpowers-ccg:` namespace)

- `coordinating-multi-model-work` — canonical three gates and OpenMCP lifecycle.
- `brainstorming` — clarify and confirm a design.
- `writing-plans` — turn a design into a resumable phase plan.
- `executing-plans` — run one phase at a time.
- `systematic-debugging` — establish root cause before fixes.
- `test-driven-development` — RED → GREEN → REFACTOR.
- `verifying-before-completion` — require fresh evidence before claims.

## Slash Commands

- `/superpowers-ccg:brainstorm`
- `/superpowers-ccg:write-plan`
- `/superpowers-ccg:execute-plan`

## Project Rules

- OpenMCP runs at `http://127.0.0.1:8765/mcp`; require a running daemon.
- Register only an absent, clean Git root on an attached branch; recheck clean
  state before every job.
- Use `task_guide`; submit only `implement`, `consult`, or `review` with an
  optional `profile`.
- Project workflow files are unsupported; submit one direct job at a time.
- Keep active phase guidance decisions; load current guidance only for new
  phases.
- Use compact waits and inspect `job.result.text` plus direct implementation
  commits.
- Never edit a registered root while its job is queued or running. Resume
  through project jobs. Never expose provider, target, model, or native session
  identities.
- Long worker prompts belong under `docs/plans/`; submit a thin pointer.

## Install / Update

See `README.md`. Update with `claude plugin update superpowers-ccg`.
