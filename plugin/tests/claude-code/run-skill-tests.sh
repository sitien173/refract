#!/usr/bin/env bash
# Test runner for Claude Code skills
# Tests skills by invoking Claude Code CLI and verifying behavior
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Reuse helpers (incl. cross-platform timeout wrapper)
source "$SCRIPT_DIR/test-helpers.sh"

echo "========================================"
echo " Claude Code Skills Test Suite"
echo "========================================"
echo ""
echo "Repository: $(cd ../.. && pwd)"
echo "Test time: $(date)"
echo "Claude version: $(claude --version 2>/dev/null || echo 'not found')"
echo ""

# Parse command line arguments
VERBOSE=false
SPECIFIC_TEST=""
TIMEOUT=300  # Default 5 minute timeout per test
RUN_INTEGRATION=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --test|-t)
            SPECIFIC_TEST="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --integration|-i)
            RUN_INTEGRATION=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --verbose, -v        Show verbose output"
            echo "  --test, -t NAME      Run only the specified test"
            echo "  --timeout SECONDS    Set timeout per test (default: 300)"
            echo "  --integration, -i    Run integration tests (slow, 10-30 min)"
            echo "  --help, -h           Show this help"
            echo ""
            echo "Tests:"
            echo "  test-namespace-consistency.sh       Lint: no stale superpowers-ccg: namespace"
            echo "  test-token-efficiency-guards.sh     Lint: bounded worker and anti-token-bomb rules"
            echo "  test-cp0-context-acquisition-guards.sh  Lint: CP0 hybrid context engine docs stay aligned"
            echo "  test-cp1-routing-guards.sh          Lint: CP1 routing block and matrix stay aligned"
            echo "  test-cp2-external-execution-guards.sh  Lint: CP2 external execution protocol stays aligned"
            echo "  test-cp3-reconciliation-guards.sh  Lint: CP3 reconciliation contract stays aligned"
            echo "  test-cp4-final-spec-review-guards.sh  Lint: CP4 phase review contract stays aligned"
            echo "  test-subagent-driven-development.sh  Test skill loading and requirements"
            echo ""
            echo "Integration Tests (use --integration):"
            echo "  test-subagent-driven-development-integration.sh  Full workflow execution"
            echo "  test-cp1-before-task-integration.sh   CP1 block appears before first subagent dispatch"
            echo "  test-cp3-before-finish-integration.sh CP3 reconciliation block appears before DONE"
            echo "  test-cp4-before-done-integration.sh   CP4 spec review block appears before DONE"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# List of skill tests to run (fast unit tests)
tests=(
    "test-namespace-consistency.sh"
    "test-token-efficiency-guards.sh"
    "test-cp0-context-acquisition-guards.sh"
    "test-cp1-routing-guards.sh"
    "test-cp2-external-execution-guards.sh"
    "test-cp3-reconciliation-guards.sh"
    "test-cp4-final-spec-review-guards.sh"
    "test-subagent-driven-development.sh"
)

# Tests that do not require the Claude Code CLI (safe for CI without claude installed)
static_tests=(
    "test-namespace-consistency.sh"
    "test-token-efficiency-guards.sh"
    "test-cp0-context-acquisition-guards.sh"
    "test-cp1-routing-guards.sh"
    "test-cp2-external-execution-guards.sh"
    "test-cp3-reconciliation-guards.sh"
    "test-cp4-final-spec-review-guards.sh"
)

# Integration tests (slow, full execution)
integration_tests=(
    "test-subagent-driven-development-integration.sh"
    "test-cp1-before-task-integration.sh"
    "test-cp3-before-finish-integration.sh"
    "test-cp4-before-done-integration.sh"
)

# Add integration tests if requested
if [ "$RUN_INTEGRATION" = true ]; then
    tests+=("${integration_tests[@]}")
fi

# Filter to specific test if requested
if [ -n "$SPECIFIC_TEST" ]; then
    tests=("$SPECIFIC_TEST")
fi

# Require Claude only when at least one selected test needs it
needs_claude=false
for test in "${tests[@]}"; do
    is_static=false
    for st in "${static_tests[@]}"; do
        if [ "$test" = "$st" ]; then
            is_static=true
            break
        fi
    done
    if [ "$is_static" = false ]; then
        needs_claude=true
        break
    fi
done

if [ "$needs_claude" = true ] && ! command -v claude &> /dev/null; then
    echo "ERROR: Claude Code CLI not found"
    echo "Install Claude Code first: https://code.claude.com"
    exit 1
fi

# Track results
passed=0
failed=0
skipped=0

# Run each test
for test in "${tests[@]}"; do
    echo "----------------------------------------"
    echo "Running: $test"
    echo "----------------------------------------"

    test_path="$SCRIPT_DIR/$test"

    if [ ! -f "$test_path" ]; then
        echo "  [SKIP] Test file not found: $test"
        skipped=$((skipped + 1))
        continue
    fi

    if [ ! -x "$test_path" ]; then
        echo "  Making $test executable..."
        chmod +x "$test_path"
    fi

    start_time=$(date +%s)

    if [ "$VERBOSE" = true ]; then
        if run_with_timeout "$TIMEOUT" bash "$test_path"; then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            echo ""
            echo "  [PASS] $test (${duration}s)"
            passed=$((passed + 1))
        else
            exit_code=$?
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            echo ""
            if [ $exit_code -eq 124 ]; then
                echo "  [FAIL] $test (timeout after ${TIMEOUT}s)"
            else
                echo "  [FAIL] $test (${duration}s)"
            fi
            failed=$((failed + 1))
        fi
    else
        # Capture output for non-verbose mode
        if output=$(run_with_timeout "$TIMEOUT" bash "$test_path" 2>&1); then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            echo "  [PASS] (${duration}s)"
            passed=$((passed + 1))
        else
            exit_code=$?
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            if [ $exit_code -eq 124 ]; then
                echo "  [FAIL] (timeout after ${TIMEOUT}s)"
            else
                echo "  [FAIL] (${duration}s)"
            fi
            echo ""
            echo "  Output:"
            echo "$output" | sed 's/^/    /'
            failed=$((failed + 1))
        fi
    fi

    echo ""
done

# Print summary
echo "========================================"
echo " Test Results Summary"
echo "========================================"
echo ""
echo "  Passed:  $passed"
echo "  Failed:  $failed"
echo "  Skipped: $skipped"
echo ""

if [ "$RUN_INTEGRATION" = false ] && [ ${#integration_tests[@]} -gt 0 ]; then
    echo "Note: Integration tests were not run (they take 10-30 minutes)."
    echo "Use --integration flag to run full workflow execution tests."
    echo ""
fi

if [ $failed -gt 0 ]; then
    echo "STATUS: FAILED"
    exit 1
else
    echo "STATUS: PASSED"
    exit 0
fi
