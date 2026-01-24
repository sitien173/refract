# Skills Evaluation Scenarios

Use evaluation scenarios (per Anthropic best practices) to validate skill effectiveness.

## Evaluation Format

```json
{
  "skill": "skill-name",
  "query": "User request",
  "context": "Optional context file",
  "expected_behavior": [
    "Expected behavior 1",
    "Expected behavior 2"
  ]
}
```

## Core Workflow Skills

### test-driven-development

```json
{
  "skill": "test-driven-development",
  "query": "Add a function to validate email format",
  "expected_behavior": [
    "Write a failing test before implementation",
    "Run tests to confirm failure and show the reason",
    "Write minimal code to make the test pass",
    "Run tests to confirm passing",
    "Do not add functionality beyond the test scope"
  ]
}
```

```json
{
  "skill": "test-driven-development",
  "query": "This function has a bug, please fix it",
  "context": "src/utils/parser.ts",
  "expected_behavior": [
    "Write a failing test that reproduces the bug",
    "Confirm the test fails for the correct reason",
    "Fix the code",
    "Confirm the test passes"
  ]
}
```

### debugging-systematically

```json
{
  "skill": "debugging-systematically",
  "query": "Tests are failing, please take a look",
  "context": "npm test output shows 3 test failures",
  "expected_behavior": [
    "Phase 1: Carefully read the error messages before proposing fixes",
    "Try to reproduce the issue",
    "Check recent code changes",
    "Phase 2: Compare with similar working code",
    "Phase 3: Form a single hypothesis and minimize the test",
    "Phase 4: Write a failing test before fixing"
  ]
}
```

```json
{
  "skill": "debugging-systematically",
  "query": "Build failed and I can't understand the error",
  "expected_behavior": [
    "Do not guess a fix immediately",
    "Carefully read the full error message and stack trace",
    "If multiple components are involved, add diagnostic logs to isolate the layer",
    "Form a hypothesis before proposing a fix"
  ]
}
```

### verifying-before-completion

```json
{
  "skill": "verifying-before-completion",
  "query": "Fix this bug and then commit",
  "expected_behavior": [
    "Run tests after the fix",
    "Show test output proving success",
    "Only claim 'fixed' after seeing passing evidence",
    "Avoid vague wording like 'should work' or 'should pass'"
  ]
}
```

### brainstorming

```json
{
  "skill": "brainstorming",
  "query": "I want to add user authentication",
  "expected_behavior": [
    "Understand the current project state first (files, docs, recent commits)",
    "Ask one question at a time",
    "Prefer multiple-choice questions",
    "Propose 2-3 different approaches with trade-offs",
    "Present the design in sections and confirm after each"
  ]
}
```

### executing-plans

```json
{
  "skill": "executing-plans",
  "query": "Execute the plan in docs/plans/feature.md",
  "expected_behavior": [
    "Read the plan first and review it critically",
    "Ask questions before starting if anything is unclear",
    "Use a checklist to track progress",
    "Report after each batch and wait for feedback",
    "Do not skip verification steps in the plan"
  ]
}
```

### developing-with-subagents

```json
{
  "skill": "developing-with-subagents",
  "query": "Execute this plan using subagents",
  "context": "docs/plans/feature.md",
  "expected_behavior": [
    "Read the plan once and extract all tasks",
    "Dispatch a separate subagent for each task",
    "Answer subagent questions before proceeding",
    "Run spec review before code quality review",
    "Iterate on fixes until the reviewer passes"
  ]
}
```

## Supporting Skills

### using-git-worktrees

```json
{
  "skill": "using-git-worktrees",
  "query": "Create an isolated workspace to develop a new feature",
  "expected_behavior": [
    "Check existing .worktrees or worktrees directories",
    "Verify the directory is gitignored",
    "If not ignored, add it to .gitignore and commit",
    "Run project setup after creating the worktree",
    "Run tests to verify a clean baseline"
  ]
}
```

### finishing-development-branches

```json
{
  "skill": "finishing-development-branches",
  "query": "Development is complete, help me handle the branch",
  "expected_behavior": [
    "Run tests and verify they pass",
    "Do not offer completion options if tests fail",
    "Provide exactly 4 options",
    "Require confirmation when discarding",
    "Clean up the worktree correctly"
  ]
}
```

### dispatching-parallel-agents

```json
{
  "skill": "dispatching-parallel-agents",
  "query": "Five test files are failing, help me fix them",
  "expected_behavior": [
    "Identify whether failures are independent",
    "If independent, group them by problem domain",
    "Dispatch multiple agents in parallel",
    "Give each agent a clear scope and constraints",
    "Summarize results and verify no conflicts"
  ]
}
```

## Run the Evaluation

1. Run the query without the skill and record behavior
2. Enable the skill and run the same query
3. Compare behavior against expected_behavior
4. Record differences and iterate on the skill
