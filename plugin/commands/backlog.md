---
description: List, file, or triage rows in the repository backlog.
argument-hint: "[empty | add <text> | triage]"
---

Follow `shared/backlog-contract.md` for the row schema, id allocation, transition
rules, and formatting. Do not restate those rules; read the file.

Operate on `docs/plans/BACKLOG.md`. Create it from the contract skeleton when
absent. Edit it only when no project job is active.

Three verbs, selected by the argument:

- **empty** — Print every row grouped by `status`, in the order `inbox`, `ready`,
  `in-plan`, `done`, `declined`, with a count per group. Report when `inbox`
  holds more than five rows, since untriaged rows are the failure mode of this
  file. Change nothing.
- **`add <text>`** — Append one row. `status` is `inbox`, `source` is
  `user MM-DD` using today's date, `pri` and `ref` stay empty. Take the id from
  the trailer and increment the trailer in the same edit.
- **`triage`** — Walk `inbox` rows one at a time, oldest id first. For each, ask
  for a priority and either promote it to `ready` or set it `declined` with a
  short reason in `ref`. Never batch the questions.

There is no verb for starting work on a row. `/superpowers-ccg:brainstorm B-NNN`
reads a row directly and begins the design.

Argument: $ARGUMENTS
