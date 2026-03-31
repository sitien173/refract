# Cross-Validation Mechanism

## Trigger Conditions

- Full-stack issues
- High uncertainty
- Design decisions
- Complex bugs
- Critical path modifications

## Validation Flow

### Phase 1: Parallel Invocation

Send the task to both Codex and Gemini simultaneously.

### Phase 2: Result Comparison

Compare shared conclusions and isolate divergences.

### Phase 3: Comprehensive Conclusion

- If both models agree, adopt the shared conclusion.
- If they diverge, Claude arbitrates and records the rationale.

## Output Format

```markdown
## Cross-Validation Report

### Codex Analysis
[Results]

### Gemini Analysis
[Results]

### Comprehensive Conclusion

- **Agreement**: [Shared findings]
- **Divergence**: [Differences]
- **Recommendation**: [Final determination]
```

## Performance Considerations

- Run Codex and Gemini in parallel.
- If one model times out, use the completed result plus Claude arbitration.
- If both time out, output `BLOCKED` and follow `GATE.md`.
