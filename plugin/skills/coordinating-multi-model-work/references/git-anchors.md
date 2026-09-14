# Phase Anchors

Phase identity must survive history rewriting. A squash, rebase, or reset moves
or destroys commits, so a recorded SHA is not a durable anchor. This file owns
the anchor format, its write lifecycle, and the resolution rules.

## Namespace

```text
refs/plans/<slug>/phase-<NN>/base   commit before the implementation job
refs/plans/<slug>/phase-<NN>/impl   final validated commit for the phase
```

Two properties carry the design. The namespace sits outside `refs/heads`, so
rewriting a branch never rewrites it. A ref also makes its object reachable, so
collection never removes the commit it names. Default push refspecs cover
`refs/heads` alone, so these stay local.

## Write lifecycle

| Moment | Action |
|---|---|
| Gate 2, before submitting the implementation job | Set `base` to clean HEAD. |
| Gate 3, review-fix loop | No ref writes. |
| Gate 3, Finalize | Set `impl` to HEAD after the last validated fix commit. |

```text
git update-ref refs/plans/<slug>/phase-<NN>/base <clean HEAD>
git update-ref refs/plans/<slug>/phase-<NN>/impl <validated HEAD>
```

`impl` is written once, at Finalize, so it always names the final validated
state of the phase. Writing it earlier makes it stale for every fix cycle, which
is why the review-fix loop reviews against HEAD instead: `impl` does not exist
while that loop runs.

## Review range

A closed phase is reviewed and re-inspected through its refs:

```text
refs/plans/<slug>/phase-<NN>/base..refs/plans/<slug>/phase-<NN>/impl
```

This range does not depend on HEAD, so rewriting history after the phase closes
cannot move it.

## Resolution

Recorded `commit` fields are advisory caches. Before trusting one, both checks
must succeed:

```text
git cat-file -e <sha>^{commit}
git merge-base --is-ancestor <sha> HEAD
```

Both are required. The first alone accepts a commit that still exists but has
left the branch. That case is the dangerous one: a range built from it still
resolves and still returns a diff, so a gate reviews the wrong delta and reports
success with nothing surfacing as an error.

On failure, descend:

| Rung | Source | Outcome |
|---|---|---|
| 1 | Cached `commit`, both checks pass | Use it. |
| 2 | `refs/plans/<slug>/phase-<NN>/{base,impl}` | Use the ref. Authoritative. |
| 3 | `git reflog` | Candidate only. Offer to the user; never use silently. |
| 4 | `FILES MODIFIED` in `phase-<NN>/journal.md` | Path scope without a diff. Degraded inspection only. |

When nothing above rung 4 resolves, set handover `status: STALE_ANCHOR` and
stop. Halting is the purpose of the ladder. It converts a silent wrong-scope
review into a visible failure the user can act on.

Never repair a broken anchor by guessing a replacement SHA, and never widen a
range to make it resolve.

## Retention

Anchors accumulate at two per phase and are never pruned automatically. Their
objects are retained deliberately, so a rewritten phase stays readable. Deletion
is manual:

```text
git update-ref -d refs/plans/<slug>/phase-<NN>/base
```

## Scope

Anchors are local to the repository and are written in every plan-artifact
tracking mode, because implementation commits are rewritten regardless of
whether plan files are committed.
