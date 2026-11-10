---
title: Workflows
nav_order: 3
---

# Workflows

## Commands

| Command | Purpose |
| --- | --- |
| `/refract:brainstorm <idea>` | Clarify intent and trade-offs; write `DESIGN.md`. |
| `/refract:write-plan <design>` | Turn a confirmed design into a phase plan. |
| `/refract:execute-plan [target]` | Run or resume one wave of phases through all three gates. |
| `/refract:execute-plan-all [target]` | Autonomously execute all waves through final audit and consolidation. |

In Pi, drop the `refract:` prefix: `/brainstorm`, `/write-plan`, `/execute-plan`, `/execute-plan-all`.

## Job workflows

Each job runs one workflow. A profile maps workflows to targets.

| Workflow | Use |
| --- | --- |
| `implement` | Repository changes |
| `review` | Independent verification of a change |
| `consult` | Read-only analysis and second opinions |
| `other` | Anything else; requires an explicit mapping and never falls back |

## Run without Refract

Set `REFRACT_DISABLE=1` to skip the daemon check and tell the host agent to ignore Refract for that session:

```bash
REFRACT_DISABLE=1 claude -p "Summarize this repository"
```

Source: [README.md](https://github.com/sitien173/refract/blob/main/README.md), [plugin/README.md](https://github.com/sitien173/refract/blob/main/plugin/README.md)
