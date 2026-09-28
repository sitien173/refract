---
name: test-driven-development
description: "Use when writing or changing production behavior, or refactoring - applies RED → GREEN → REFACTOR and characterization coverage for behavior-preserving refactors."
---

# Test-Driven Development

## Role

This skill owns implementation test order. `systematic-debugging` owns bug
cause; `verifying-before-completion` owns final evidence claims.

## Iron Law

```text
NO CHANGED BEHAVIOR WITHOUT A FAILING TEST FIRST
NO REFACTOR WITHOUT PASSING CHARACTERIZATION COVERAGE
```

## Cycle

1. **RED.** Add one focused behavior test and run it. Quote the failure line.
   RED counts only when the failure names the intended missing behavior; an
   import error, typo, or missing fixture is not RED.
2. **GREEN.** Make the smallest production change that passes the focused test
   and the tests covering every module you touched.
3. **REFACTOR.** Improve structure only, running tests after each step. Stay
   green.
4. Repeat for the next behavior.

For a bug, RED reproduces the diagnosed defect. For a behavior-preserving
refactor, establish passing characterization tests first and keep them green.

## Edge Cases

- **RED passes already.** Strengthen the test. If the behavior truly exists,
  report that and write no production code.
- **No test harness.** Ask the user whether to add one or waive TDD for this
  change.
- **Flaky RED.** Run it three times. A test that does not fail every time is
  not RED; stabilize it first.
- **Hard boundary.** Network, clock, filesystem, or hardware: mock only that
  boundary and keep real behavior everywhere else.

## Rules

- Production behavior you wrote before its test is discarded and redone
  test-first. Pre-existing code is characterized, not discarded.
- Fix production code to meet the assertion. Change an assertion only when it
  contradicts the specification, and say so.
- Exceptions require user approval: generated code, pure configuration, or a
  throwaway prototype.

## Evidence Record

Record in the phase `notes.md` under Test evidence, or in the final report for
direct work:

```text
RED:   <command> -> <failing test>: <failure line>
GREEN: <command> -> <N> passed, 0 failed
```

Changed behavior without credible RED → GREEN evidence fails specification
review unless the user waived TDD.
