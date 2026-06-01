# PRD Blueprint

Use this blueprint as the default structure. Adapt to the user's domain and desired depth.

## 1. Title and Product Summary

Include:
- Product name or codename.
- Product type.
- Primary users.
- Platform/environment.
- Key technology or strategic decision.
- One paragraph explaining what the product does.

Template:

```markdown
# PRD: [Product Name]

**Product type:** [desktop app / api / saas / mobile app / internal tool]
**Primary users:** [user groups]
**Primary platform:** [platform]
**Strategic decision:** [main approach]

[One-paragraph summary of the product and why it exists.]
```

## 2. Reality Check / Key Recommendation

Use when the user asks for ambitious outcomes or there are external constraints.

Include:
- What the product can control.
- What it cannot guarantee.
- The recommended approach.
- The first validation milestone.

Example pattern:

```markdown
The product cannot guarantee [outcome] because [external dependency]. It can improve [measurable area] when [condition]. The MVP should therefore [recommended approach] and automatically fall back when [failure condition].
```

## 3. Problem Statement

Describe concrete pains, not generic market language. Include current workaround failures if known.

Good problem statements answer:
- Who has the problem?
- When does it happen?
- Why are existing options insufficient?
- What is the cost of not solving it?

## 4. Goals

Separate primary and secondary goals. Make them measurable or decision-oriented.

Good examples:
- Reduce p95 latency by [threshold] for qualifying users.
- Allow admins to restore network state in one action.
- Keep background CPU usage near zero when idle.

Bad examples:
- Be fast.
- Improve user experience.
- Make the product great.

## 5. Non-goals

Use non-goals aggressively to prevent scope creep. Include anything the user might assume but should not be included in MVP.

Examples:
- No custom kernel driver in MVP.
- No in-game overlay.
- No billing in beta.
- No multi-region routing until single-region validation succeeds.

## 6. Target Users and Personas

For each persona include:
- Profile.
- Context.
- Jobs-to-be-done.
- Needs.
- Constraints.
- Success definition.

Keep personas practical. Avoid fictional fluff unless the user asked for marketing personas.

## 7. Product Positioning

Useful for founder-facing PRDs or products with risky claims.

Include:
- Recommended claim.
- Claims to avoid.
- Trust-building language.

## 8. Success Metrics

Use several metric groups when appropriate:

```markdown
### Product metrics
| Metric | Target |
|---|---:|
| activation success rate | >95% |
| restore success rate | 100% in qa scenarios |

### Performance metrics
| Metric | Target |
|---|---:|
| idle cpu | ~0% |
| p95 latency | improves vs baseline for qualifying users |
```

Prefer p95/p99, failure rate, retention, time-to-value, correctness, or safety metrics over vanity metrics.

## 9. Core User Stories

Use IDs:

```markdown
**US-001 — [Story title]**
As a [persona], I want [capability] so that [outcome].
```

Include admin/operator stories when relevant.

## 10. Functional Requirements

Use requirement tables:

```markdown
| ID | Requirement | Priority |
|---|---|---|
| FR-001 | [Specific behavior] | P0 |
```

Break into areas:
- Client app
- Backend/api
- Data model
- Workflow
- Admin
- Integrations
- Diagnostics
- Billing
- Settings
- Notifications

Use only areas that fit the product.

## 11. Non-functional Requirements

Common groups:
- Performance
- Reliability
- Security
- Privacy
- Accessibility
- Compatibility
- Scalability
- Observability
- Compliance
- Safety/abuse prevention

Make targets concrete where possible.

## 12. Technical Architecture

For technical PRDs, include a text architecture diagram:

```text
+------------------+        +------------------+
| client           | -----> | backend api      |
| - ui             |        | - auth           |
| - local service  |        | - orchestration  |
+------------------+        +------------------+
          |                         |
          v                         v
+------------------+        +------------------+
| local subsystem  |        | database/cache   |
+------------------+        +------------------+
```

Then explain:
- Component responsibilities.
- Data flow.
- Control flow.
- Failure modes.
- Privilege boundaries.

## 13. MVP Scope

Include must-have and explicitly out-of-scope lists.

```markdown
### MVP must include
1. ...

### MVP should not include
1. ...
```

## 14. UX / User Flows

Include screen/menu sketches when helpful:

```text
Main screen
Status: [state]
Primary action: [button]
Metrics: [key metrics]
Secondary actions: [restore/export/settings]
```

Use simple state labels users can understand.

## 15. Decision Engine / Business Logic

Use when the product must choose among routes, plans, recommendations, risk levels, or automations.

Include:
- Inputs.
- Decision priority.
- Decision rules.
- Overrides.
- Cooldowns or anti-flapping rules.
- Failure handling.

## 16. Data, Privacy, Security, Compliance, and Safety

Include when relevant:
- What data is collected.
- What is explicitly not collected.
- Storage and retention.
- Access controls.
- Secret management.
- Audit logs.
- Regulatory constraints.
- Abuse prevention.
- Safety constraints.

## 17. Acceptance Criteria and Test Plan

Acceptance criteria should define what must be true before the MVP is accepted.

```markdown
MVP is acceptable when:
1. [User can complete key flow]
2. [System handles failure condition]
3. [Metrics meet threshold]
```

Test plan should include:
- Functional tests.
- Performance tests.
- Security/privacy tests.
- Failure/recovery tests.
- Compatibility tests.
- Beta validation.

## 18. Risk Register

Use a table:

```markdown
| Risk | Severity | Mitigation |
|---|---:|---|
| [risk] | High | [mitigation] |
```

High-quality risks are specific to the product, not generic.

## 19. Milestones / Rollout Plan

Use staged milestones:
- Manual validation
- Internal MVP
- Closed beta
- Public beta
- GA

Each milestone should have deliverables and exit criteria.

## 20. Open Questions

Open questions should be actionable and limited. Do not use them to avoid making necessary assumptions.

## 21. Final Decision

End with a clear product rule or recommendation:

```markdown
The MVP should be [specific approach].
The most important product rule is [rule].
The most important engineering rule is [rule].
```
