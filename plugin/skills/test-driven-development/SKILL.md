---
name: test-driven-development
description: "Uses RED → GREEN → REFACTOR for features and bug fixes, and characterization coverage for behavior-preserving refactors."
---

# Test-Driven Development

Load `coordinating-multi-model-work` first when work will be delegated.

## Iron Law

```text
NO CHANGED BEHAVIOR WITHOUT A FAILING TEST FIRST
NO REFACTOR WITHOUT PASSING CHARACTERIZATION COVERAGE
```

## RED → GREEN → REFACTOR

1. **RED:** Write one focused test for one observable behavior.
2. Run it and confirm it fails because the behavior is missing, not because the
   test is broken. If it already passes, improve the test.
3. **GREEN:** Write the smallest production change that makes the test pass.
4. Run the focused test and relevant suite; fix production code, not assertions.
5. **REFACTOR:** Improve structure only while tests remain green.
6. Repeat for the next behavior.

For a bug, the RED test reproduces the diagnosed defect. For a
behavior-preserving refactor, establish passing characterization tests first and
keep them green; do not manufacture a failure.

## Rules

- Code written before its behavior test must be discarded and redone test-first.
- Do not add speculative features during GREEN.
- Prefer real behavior over mocks; mock only unavoidable boundaries.
- Record the failing command/output and the later passing command/output.
- Exceptions require user approval: generated code, pure configuration, or a
  throwaway prototype.

## Review Requirement

Changed behavior without credible RED → GREEN evidence fails specification
review unless the user explicitly waived TDD. A passing test written only after
the implementation is coverage, not test-first evidence.

## References

- `skills/systematic-debugging/SKILL.md` — root cause before bug-fix RED.
- `skills/verifying-before-completion/SKILL.md` — fresh final verification.
