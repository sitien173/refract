---
name: test-driven-development
description: "Applies RED → GREEN → REFACTOR to changed behavior and characterization coverage to behavior-preserving refactors."
---

# Test-Driven Development

This skill owns implementation test order. `systematic-debugging` owns bug
cause; `verifying-before-completion` owns final evidence claims.

## Iron Law

```text
NO CHANGED BEHAVIOR WITHOUT A FAILING TEST FIRST
NO REFACTOR WITHOUT PASSING CHARACTERIZATION COVERAGE
```

## Cycle

1. **RED:** Add one focused behavior test. Run it and confirm it fails for the
   intended missing behavior.
2. **GREEN:** Make the smallest production change that passes the focused test
   and relevant suite.
3. **REFACTOR:** Improve structure only while tests stay green.
4. Repeat for the next behavior.

For a bug, RED must reproduce the diagnosed defect. For a behavior-preserving
refactor, establish passing characterization tests and keep them green; do not
manufacture a failure.

## Rules

- Discard production behavior written before its test and redo it test-first.
- If RED already passes, strengthen the test before production changes.
- Fix production code, not assertions.
- Prefer real behavior; mock only unavoidable boundaries.
- Record failing and passing commands and outputs.
- Exceptions require user approval: generated code, pure configuration, or a
  throwaway prototype.

Changed behavior without credible RED → GREEN evidence fails specification
review unless the user waived TDD.
