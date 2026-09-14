# Plan and Phase Anchors

Plan identity and reviewed phase checkpoints must survive consolidation and
history rewriting. This file owns anchor formats, writes, and resolution.

## Namespace

```text
refs/plans/<slug>/base              commit before plan work
refs/plans/<slug>/impl              sole final plan commit
refs/plans/<slug>/phase-<NN>/base   checkpoint before phase implementation
refs/plans/<slug>/phase-<NN>/impl   final validated phase checkpoint
```

Refs sit outside `refs/heads`. Consolidating or rewriting the branch therefore
does not move them. Each ref also retains its commit object locally. Default push
refspecs omit these refs.

## Write lifecycle

| Moment | Action |
|---|---|
| Before preparing Phase 1 | Set plan `base` to clean HEAD. |
| Gate 2, before implementation | Set phase `base` to clean checkpoint HEAD. |
| Gate 3, after the final phase fix | Set phase `impl` to validated checkpoint HEAD. |
| Final plan consolidation | Replace branch checkpoints with one commit, then set plan `impl` to HEAD. |

```text
git update-ref refs/plans/<slug>/base <clean HEAD>
git update-ref refs/plans/<slug>/phase-<NN>/base <checkpoint HEAD>
git update-ref refs/plans/<slug>/phase-<NN>/impl <validated checkpoint HEAD>
git update-ref refs/plans/<slug>/impl <sole plan commit>
```

Write each `impl` once. Phase `impl` captures reviewed evidence before
consolidation. Plan `impl` captures the resulting single branch commit.

## Consolidation

After every phase passes and final coordination state is ready:

1. Confirm no project job is active.
2. Confirm every phase has `base` and `impl` refs.
3. Confirm the root is clean at the final checkpoint.
4. Create one replacement commit from the final checkpoint tree. Give it the
   plan `base` as parent and use `PLAN.md`'s message.
5. Atomically move the attached branch from the checkpoint tip to that commit.
6. Set the plan `impl` ref to the resulting HEAD.
7. Run final verification against that exact HEAD.

Use Git plumbing so the working tree remains unchanged:

```text
<replacement> = git commit-tree <checkpoint>^{tree} -p <plan-base> -m "<plan message>"
git update-ref <attached-branch-ref> <replacement> <checkpoint>
git update-ref refs/plans/<slug>/impl <replacement>
```

The old value on the branch update makes a moved tip fail atomically. This
rewrite is allowed only at final plan consolidation. Phase refs retain every
reviewed range and comprehensive artifact.

## Review ranges

Review an active phase through:

```text
refs/plans/<slug>/phase-<NN>/base..HEAD
```

Inspect a closed phase through:

```text
refs/plans/<slug>/phase-<NN>/base..refs/plans/<slug>/phase-<NN>/impl
```

Inspect the completed plan through:

```text
refs/plans/<slug>/base..refs/plans/<slug>/impl
```

## Resolution

Recorded commit fields are advisory caches. Before trusting one, both checks
must succeed:

```text
git cat-file -e <sha>^{commit}
git merge-base --is-ancestor <sha> HEAD
```

Phase checkpoint caches normally fail the ancestry check after consolidation.
That is expected. Their refs remain authoritative and must resolve directly.

| Rung | Source | Outcome |
|---|---|---|
| 1 | Cached commit, both checks pass | Use it. |
| 2 | Corresponding plan or phase ref | Use the ref. Authoritative. |
| 3 | `git reflog` | Candidate only. Offer it; never use silently. |
| 4 | `FILES MODIFIED` in the phase journal | Degraded path inspection only. |

When nothing resolves, set handover `status: STALE_ANCHOR` and stop. Never guess
a replacement SHA or widen a range merely to make it resolve.

## Retention

Anchors remain local and are never pruned automatically. Their objects are
retained deliberately. Deletion is manual:

```text
git update-ref -d refs/plans/<slug>/phase-<NN>/base
```

Write anchors in both plan-artifact tracking modes.