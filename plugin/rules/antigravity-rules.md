# Superpowers-CCG — Agent Rules

> Skill namespace: `superpowers-ccg:` (e.g. `superpowers-ccg:coordinating-multi-model-work`).

## Workflow

Three gates: **Plan → Execute → Review**.

1. **Plan** — gather minimum context. Run CROSS_VALIDATION (Codex + agy, reconcile) **only** when work is full-stack, unclear, or high-impact; otherwise skip. Define one phase: 2–4 tasks, file set, Done When. Output `# ROUTE`.
2. **Execute** — route by side; worker edits files and returns `## FILES MODIFIED`.
3. **Review** — run Done When, output `# REVIEW` with PASS / PASS_WITH_DEBT / FAIL.

Full rules: `skills/coordinating-multi-model-work/SKILL.md`.

## Routing (by side, no default)

| Phase | Owner | MCP |
|---|---|---|
| Simple/trivial Claude can handle directly | Claude | none |
| **Back-side**: backend, API, logic, database, system, infra, CI/CD, scripts | Codex | `mcp__plugin_superpowers-ccg_openmcp__run(backend="codex", ...)` |
| **Front-side**: UI, CSS, motion, canvas/SVG, interactions, multimodal, large-context UI/doc sweeps | agy | `mcp__plugin_superpowers-ccg_openmcp__run(backend="agy", ...)` |
| Full-stack / unclear / high-impact new work | Cross-Validation → side owner | both |
| Single-side new feature, clear scope | Side owner directly (skip CV) | one |
| Full-stack execution | Split into back-side + front-side sub-phases | both |

## Skills

| Skill | Trigger | Purpose |
|---|---|---|
| `superpowers-ccg:brainstorming` | New feature, ideation, design | Clarify, produce design doc; cross-validate only if full-stack / unclear / high-impact |
| `superpowers-ccg:writing-plans` | Confirmed design needs a plan | Phase-based implementation plan |
| `superpowers-ccg:executing-plans` | Plan exists, run it | One phase at a time with Plan → Execute → Review |
| `superpowers-ccg:verifying-before-completion` | About to claim done | Final integration + review |
| `superpowers-ccg:coordinating-multi-model-work` | Any routing decision | 3-gate workflow, side-based routing |

## Commands

| Command | Skill |
|---|---|
| `/brainstorm` | `brainstorming` |
| `/write-plan` | `writing-plans` |
| `/execute-plan` | `executing-plans` |

## Iron Laws

- No production code without a failing test first.
- No fixes without root-cause investigation first.
- No completion claims without fresh verification evidence.

## Hard Rules

- MCP failure → `BLOCKED`, ask the human. No silent retry, executor switch, or Task/Agent fallback.
- One phase, one owner, one review. No draft-then-reimplement handoffs.
- Cross-Validation runs only when work is full-stack, unclear, or high-impact. Skip for clear single-side work — CV catches misses via dual review, it is not a default ceremony.
- Route by side, not by default — never auto-route to one executor.
- User overrides ("use Codex" / "use agy" / "no external models" / "skip cross-validation") win.
