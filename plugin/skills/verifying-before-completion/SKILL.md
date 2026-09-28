---
name: verifying-before-completion
description: "Use before claiming any work is complete, fixed, passing, reviewed, or ready to hand off - defines the fresh evidence each claim requires."
---

# Verifying Before Completion

## Role

This skill owns evidence and claim discipline. The coordinating skill chooses
the revision, diff ranges, and review sequence.

## Iron Law

```text
NO COMPLETION CLAIM WITHOUT FRESH VERIFICATION EVIDENCE
```

## Method

1. **Identify** each claim you intend to make and the evidence it needs,
   using the claim standard below.
2. **Pin the revision.** Coordinated work: the revision the coordinating skill
   names. Direct work: the current working tree, with `git status` recorded.
3. **Run** each complete command or inspection now, at that revision.
4. **Read** the full output, exit code, and failure count.
5. **Compare** the results with every acceptance criterion, one at a time.
6. **Report** only what the evidence supports.

## Required Evidence

- Applicable build, lint, type, test, and smoke checks.
- Changed paths and diffs match approved scope.
- Acceptance criteria checked individually.
- Bug regression fails without the fix and passes with it.
- Specification and independent quality-review outcomes, for coordinated work.
- Explicit debt, skipped checks, and environmental blockers.
- Final revision and repository cleanliness.

## Claim Standard

| Claim | Minimum evidence |
| --- | --- |
| Tests pass | Fresh output with zero failures |
| Build succeeds | Fresh exit code 0 |
| Bug is fixed | Original reproduction or regression test passes |
| Requirements are met | Criterion-by-criterion evidence |
| Worker finished correctly | Inspected diff, fresh checks, clean state, and coordinator checkpoint |

`FAIL` blocks completion. `PASS_WITH_DEBT` is acceptable only for explicit,
assigned, non-blocking debt. Worker summaries and prior runs are not proof.

## Edge Cases

- **Check cannot run.** Missing tool, credentials, or service: report
  `not run - <reason>`. An unrun check is never a passed check.
- **Truncated output.** Rerun with output captured to a file and read the
  summary lines.
- **Inconsistent runs.** Report both results and mark the claim unverified.
- **Revision moved.** HEAD or the tree changed mid-verification: restart at
  the new revision.

## Output Format

```text
# VERIFICATION
- Revision: <sha or ref> | working tree
- Changed files: <paths>
- Checks: <command> -> <exit code, pass/fail counts> | not run - <reason>
- Criteria: <criterion> -> met | not met, <evidence>
- Review: Spec <status>, Quality <status> | n/a
- Debt: <item and owner> | none
- Clean: yes | no, <paths>
```

State outcomes in the past tense from evidence: passed, failed, not run.
