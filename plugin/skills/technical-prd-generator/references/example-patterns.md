# Example Patterns

Use these patterns to match the desired PRD style.

## Strong Opening

```markdown
# PRD: [Product]

**Product type:** [type]
**Primary users:** [users]
**Primary platform:** [platform]
**Strategic decision:** [decision]

[Product] helps [users] solve [problem] by [mechanism]. The MVP should focus on [scope] and avoid [scope creep].
```

## Reality Check

```markdown
A desktop app cannot guarantee lower latency for every player. It can only improve latency when its route is better than the user's direct ISP route. The product must measure both paths and automatically choose Direct mode when the optimized path is worse.
```

Adapt the example to the user's domain.

## Recommendation Table

```markdown
| Approach | Verdict | Reason |
|---|---|---|
| option a | best default | satisfies the key constraints with lowest complexity |
| option b | later/fallback | useful only when a specific failure mode appears |
| option c | avoid | conflicts with the core goal or adds unacceptable risk |
```

## Requirement Table

```markdown
| ID | Requirement | Priority |
|---|---|---|
| FR-001 | Provide a one-click primary action for the core workflow. | P0 |
| FR-002 | Show clear state labels for active, testing, error, and restored states. | P0 |
| FR-003 | Export diagnostics with secrets redacted. | P1 |
```

## User Story

```markdown
**US-001 — One-click setup**
As a [persona], I want to start [workflow] with one action so that I can get value without understanding the underlying technical system.
```

## Architecture Diagram

```text
+------------------+       +-------------------+
| user interface   | ----> | privileged service|
+------------------+       +-------------------+
                              |
                              v
                       +---------------+
                       | subsystem/api |
                       +---------------+
```

## Risk Register

```markdown
| Risk | Severity | Mitigation |
|---|---:|---|
| product worsens the user's baseline experience | High | measure baseline first and auto-disable when worse |
| external platform policy changes | High | cite official policies and keep compliance requirements explicit |
```

## Final Decision

```markdown
The MVP should be [specific build].
The most important product rule is [rule protecting user value].
The most important engineering rule is [rule protecting reliability/safety].
```
