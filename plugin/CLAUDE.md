# CLAUDE.md

Guidance for Claude Code working in this repo.

## Workflow

3 gates: **Plan → Execute → Review**. Full details in `skills/coordinating-multi-model-work/SKILL.md`.

- **Plan** — new feature / ideation → CROSS_VALIDATION first (Codex + Gemini). Otherwise gather minimum context, define one phase (2–4 tasks, file set, Done When), output `# ROUTE`.
- **Execute** — route by side: Claude for simple tasks; Codex (`mcp__openmcp__run(backend="codex", ...)`) for back-side (backend, database, system, infra); Gemini (`mcp__openmcp__run(backend="agy", ...)`) for front-side (UI, CSS, motion, multimodal). No default executor.
- **Review** — (a) Spec: run Done When checks; (b) Quality scan on changed files (edge cases, error handling, security, naming, duplication, correctness). Severity downgrade: CRITICAL/HIGH → FAIL, MEDIUM → PASS_WITH_DEBT, LOW noted. Skip Quality for docs-only / trivial Claude edits.

## Hard Rules

- MCP failure → `BLOCKED`, ask the human. No silent retry, executor switch, or Task/Agent fallback.
- Long input → write to a repo file (prefer `docs/plans/`) and pass the path.
- **Absolute paths only when calling `mcp__openmcp__run`.** The dispatch prompt pointer, the `cd` arg, and every file path inside the prompt body must be absolute (forward slashes on Windows). Gemini/agy mis-resolves relative paths and will scan the whole device. Resolve before sending.
- One phase, one owner, one review. No draft-then-reimplement handoffs.

## Skills

- `brainstorming` — new features / ideation (runs Cross-Validation first).
- `writing-plans` — design → phase-based plan.
- `executing-plans` — run plan one phase at a time.
- `debugging-systematically` — evidence-based root cause.
- `verifying-before-completion` — final check before reporting done.
- `coordinating-multi-model-work` — canonical 3-gate workflow + routing.

## Commands

- `/brainstorm`, `/write-plan`, `/execute-plan`.

## Common Commands

- Install MCPs: `claude mcp add codex ...` / `claude mcp add gemini ...` (see README.md).
- Update plugin: `claude plugin update superpowers-ccg`.
