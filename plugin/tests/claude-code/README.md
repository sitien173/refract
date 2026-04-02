# Claude Code Skills Tests

Automated tests for superpowers skills using Claude Code CLI.

## Overview

This test suite verifies that skills are loaded correctly and Claude follows them as expected. Tests invoke Claude Code in headless mode (`claude -p`) and verify the behavior.

## Requirements

- Claude Code CLI installed and in PATH (`claude --version` should work)
- Local superpowers plugin installed (see main README for installation)

## Running Tests

### Run all fast tests (recommended):
```bash
./run-skill-tests.sh
```

### Run integration tests (slow, 10-30 minutes):
```bash
./run-skill-tests.sh --integration
```

### Run specific test:
```bash
./run-skill-tests.sh --test test-subagent-driven-development.sh
```

### Run with verbose output:
```bash
./run-skill-tests.sh --verbose
```

### Set custom timeout:
```bash
./run-skill-tests.sh --timeout 1800  # 30 minutes for integration tests
```

## Test Structure

### test-helpers.sh
Common functions for skills testing:
- `run_claude "prompt" [timeout]` - Run Claude with prompt
- `assert_contains output pattern name` - Verify pattern exists
- `assert_not_contains output pattern name` - Verify pattern absent
- `assert_count output pattern count name` - Verify exact count
- `assert_order output pattern_a pattern_b name` - Verify order
- `create_test_project` - Create temp test directory
- `create_test_plan project_dir` - Create sample plan file

### Test Files

Each test file:
1. Sources `test-helpers.sh`
2. Runs Claude Code with specific prompts
3. Verifies expected behavior using assertions
4. Returns 0 on success, non-zero on failure

## Example Test

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

echo "=== Test: My Skill ==="

# Ask Claude about the skill
output=$(run_claude "What does the my-skill skill do?" 30)

# Verify response
assert_contains "$output" "expected behavior" "Skill describes behavior"

echo "=== All tests passed ==="
```

## Current Tests

### Fast Tests (run by default)

#### test-token-efficiency-guards.sh
Static workflow guard test:
- No stale CURSOR routing in active token-path docs
- No "prototype then rewrite" language
- Bounded task / worker ownership language exists
- Cross-validation is explicitly constrained

#### test-cp0-context-acquisition-guards.sh
Static CP0 guard test:
- CP0 is explicitly documented as the pre-routing stage
- Hybrid Context Engine language exists in startup and workflow docs
- Tool order remains Auggie → Morph WarpGrep → Serena → Grok Search
- CP0 tool matrix is embedded in the active checkpoint docs
- Architecture diagram includes CP0

#### test-cp1-routing-guards.sh
Static CP1 guard test:
- CP1 is explicitly named Task Assessment & Routing
- The exact `# CP1 ROUTING DECISION` block exists in hook and threshold docs
- Detailed and compact CP1 routing matrices are embedded in the active docs
- The diagram labels CP1 as Task Assessment & Routing

#### test-cp2-external-execution-guards.sh
Static CP2 guard test:
- CP2 is explicitly named External Execution
- External Response Protocol v1.1 exists in the active execution docs
- `## FILE CONTENTS` is required with full file content preferred and unified diff fallback
- Legacy `diff-or-questions` / `## DIFF` / `## QUESTIONS` contract is absent from active execution docs

#### test-cp3-reconciliation-guards.sh
Static CP3 guard test:
- CP3 is explicitly named Reconciliation
- The exact `# CP3 RECONCILIATION COMPLETE` block exists in hook and threshold docs
- Legacy `[CP3 Assessment]` / `[CP3] Verified` formats are absent from active docs
- The diagram labels CP3 as Reconciliation

#### test-cp4-final-spec-review-guards.sh
Static CP4 guard test:
- CP4 is explicitly named Final Spec Review
- The exact `# CP4 SPEC REVIEW COMPLETE` block exists in hook and threshold docs
- CP4 is explicitly spec-only and excludes code quality/style review
- The diagram labels CP4 as Final Spec Review

#### test-subagent-driven-development.sh
Tests skill content and requirements (~2 minutes):
- Skill loading and accessibility
- One bounded task at a time
- CP4 final spec review as the last review stage
- One worker owner per task
- Same worker session reuse for fixes
- No prototype-then-rewrite pattern
- External Response Protocol v1.1 output contract

### Integration Tests (use --integration flag)

#### test-subagent-driven-development-integration.sh
Full workflow execution test (~10-30 minutes):
- Creates real test project with Node.js setup
- Creates implementation plan with 2 tasks
- Executes plan using subagent-driven-development
- Verifies actual behaviors:
  - Plan read once at start (not per task)
  - Full task text provided in subagent prompts
  - Subagents perform self-review before reporting
  - CP4 final spec review happens at the end
  - Final review checks the artifact against the spec
  - Working implementation is produced
  - Tests pass
  - Proper git commits created

**What it tests:**
- The workflow actually works end-to-end
- Our improvements are actually applied
- Subagents follow the skill correctly
- Final code is functional and tested

#### test-cp4-before-done-integration.sh
Focused CP4 integration test:
- Forces Claude to emit the exact `# CP4 SPEC REVIEW COMPLETE` block
- Verifies required CP4 fields are present
- Verifies the CP4 block is a standalone text message
- Verifies CP4 appears before the final `DONE` marker

## Adding New Tests

1. Create new test file: `test-<skill-name>.sh`
2. Source test-helpers.sh
3. Write tests using `run_claude` and assertions
4. Add to test list in `run-skill-tests.sh`
5. Make executable: `chmod +x test-<skill-name>.sh`

## Timeout Considerations

- Default timeout: 5 minutes per test
- Claude Code may take time to respond
- Adjust with `--timeout` if needed
- Tests should be focused to avoid long runs

## Debugging Failed Tests

With `--verbose`, you'll see full Claude output:
```bash
./run-skill-tests.sh --verbose --test test-subagent-driven-development.sh
```

Without verbose, only failures show output.

## CI/CD Integration

To run in CI:
```bash
# Run with explicit timeout for CI environments
./run-skill-tests.sh --timeout 900

# Exit code 0 = success, non-zero = failure
```

## Notes

- Tests verify skill *instructions*, not full execution
- Full workflow tests would be very slow
- Focus on verifying key skill requirements
- Tests should be deterministic
- Avoid testing implementation details
