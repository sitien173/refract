<!-- ccg-shared-version: 10.2.0 -->

# Backlog Contract

Single source of truth for `docs/plans/BACKLOG.md`. The `/ccg:backlog` command,
`brainstorming`, `writing-plans`, `executing-plans`, and
`coordinating-multi-model-work` all follow this file rather than restating rules.

The backlog closes the lifecycle loop. Accepted debt becomes a row, triage
promotes it, a design consumes it, a plan closes it at closeout.

## Location

`docs/plans/BACKLOG.md`, one per repository. Create it from the skeleton below
when absent.

## Row schema

Six columns, in this order: `id`, `title`, `source`, `pri`, `status`, `ref`.

| Column | Rule |
|---|---|
| `id` | `B-NNN`, zero-padded to three digits. Allocate from the trailer comment. |
| `title` | Imperative, one line. Strip pipe characters; they break the row. |
| `source` | Origin of the row. See the source vocabulary below. |
| `pri` | `P1`, `P2`, or `P3`. Blank until triage. |
| `status` | `inbox`, `ready`, `in-plan`, `done`, or `declined`. |
| `ref` | Meaning depends on `status`. See the ref semantics below. |

### Source vocabulary

| Value | Meaning |
|---|---|
| `user MM-DD` | Filed by hand through `/ccg:backlog add`. |
| `<slug>/ph-NN debt` | Accepted debt from a phase that finished `PASS_WITH_DEBT`. |
| `<slug>/ph-NN follow-up` | A per-task follow-up accepted at closeout. |
| `retro/<slug>` | A process fix accepted from a plan retro. |

### Priority

| Value | Meaning |
|---|---|
| `P1` | Blocks planned work, or carries correctness or security risk. |
| `P2` | Default. Real work, nothing blocked. |
| `P3` | Nice to have. |

### Ref semantics

`ref` is deliberately overloaded. A seventh column would be empty on most rows.

| Status | `ref` holds |
|---|---|
| `inbox` | empty |
| `ready` | empty |
| `in-plan` | the plan slug |
| `done` | the plan slug, then the range `<phase_base>..<HEAD>` |
| `declined` | a short reason |

## Id allocation

The trailer comment `<!-- next id: B-NNN -->` sits at the end of the file and is
the only source of ids.

- Read the trailer, use that id for the new row, then increment the trailer.
- Increment the trailer **in the same edit that appends the row**. A separate
  edit leaves a window where two writers take the same id.
- Never reuse an id, including from a `declined` or `done` row.
- Never renumber existing rows.

## Formatting

- No column alignment. Pad each cell with a single space.
- Alignment is the most common cause of failed table edits. Do not add it, and do
  not reformat rows you are not changing.
- Append new rows at the bottom of the table.
- Keep one blank line between the table and the trailer.

## Status transitions

| From | To | Trigger | Owner |
|---|---|---|---|
| new | `inbox` | `/ccg:backlog add` | the command |
| new | `inbox` | a `PASS_WITH_DEBT` debt entry | coordinator, at phase finalization |
| new | `inbox` | an accepted follow-up or retro fix | executing-plans, at closeout |
| `inbox` | `ready` | triage assigns a priority | `/ccg:backlog triage` |
| `inbox` | `declined` | triage rejects, reason into `ref` | `/ccg:backlog triage` |
| `ready` | `in-plan` | a plan directory is created for it | writing-plans |
| `in-plan` | `done` | closeout | executing-plans, final phase |
| `in-plan` | `ready` | the plan was abandoned | `/ccg:backlog` |

No other transition is legal. In particular nothing moves directly from `inbox`
to `in-plan`; triage is not optional.

## Auto-file policy

| Signal | Behavior |
|---|---|
| `PASS_WITH_DEBT` debt entry | Files one `inbox` row automatically at phase finalization. Accepted debt must never be lost to inattention. |
| Per-task `Follow-ups for human` | Collected across every phase, presented at closeout, filed only for the ones the user accepts. |
| Non-blocking review findings | Same as follow-ups. |

Automatic debt rows fold into the existing `chore(plan): record phase <N>`
commit. Filing a row never creates its own commit.

Blocking findings are never filed. They are fixed inside the phase.

## Write safety

Backlog writes follow the existing coordination-file rule: edit
`docs/plans/BACKLOG.md` only when no project job is active. A worker may hold the
tree otherwise, and a lost row is invisible.

## Skeleton

Create the file with exactly this content when it does not exist.

```markdown
# Backlog

| id | title | source | pri | status | ref |
|----|-------|--------|-----|--------|-----|

<!-- next id: B-001 -->
```

## Populated example

```markdown
# Backlog

| id | title | source | pri | status | ref |
|----|-------|--------|-----|--------|-----|
| B-001 | Add cross-plan status view | user 08-24 | P2 | inbox | |
| B-002 | Stop dropping partial worker output on retry | auth-rewrite/ph-02 debt | P1 | ready | |
| B-003 | Fix hook JSON escaping | retro/auth-rewrite | P1 | in-plan | hook-escape |
| B-004 | Migrate handover schema to v2 | user 08-11 | P1 | done | handover-v2 a1b2c3d..e5f6a7b |
| B-005 | Sync plans to an external tracker | user 08-20 | P3 | declined | out of scope |

<!-- next id: B-006 -->
```
