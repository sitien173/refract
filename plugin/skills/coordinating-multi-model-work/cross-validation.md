# Cross-Validation Mechanism

## Trigger Conditions

### 1. Full-Stack Issues

**Definition**: Tasks involving both frontend and backend code or logic simultaneously.

**Identification Signals**:
- Files involved include both frontend and backend extensions
- Problem description involves frontend-backend interaction (e.g., "page doesn't update after API call")
- Modifications require adjusting both frontend and backend code

**Examples**:
- "White screen after login" - could be an API issue or frontend rendering problem
- "Form submission fails" - could be frontend validation, API processing, or database issue
- "Data displays incorrectly" - could be API return format or frontend parsing problem

### 2. High Uncertainty

**Definition**: Problems with multiple possible causes, difficult to determine root cause.

**Identification Signals**:
- Error messages are vague or missing
- Problem appears intermittently
- Multiple possible causes remain after preliminary analysis

**Examples**:
- "Page loads slowly sometimes" - could be frontend rendering, API response, or network issue
- "Data loss occurs occasionally" - could be frontend state, API processing, or database transaction issue

### 3. Design Decisions

**Definition**: Need to evaluate multiple architecture or technical solutions.

**Identification Signals**:
- Task involves new feature design
- Need to choose tech stack or architecture pattern
- Multiple viable options exist for the solution

**Examples**:
- "Design real-time notification system" - need to evaluate WebSocket/SSE + UI display solutions
- "Optimize search functionality" - need to evaluate backend search engine + frontend interaction experience

### 4. Complex Bugs

**Definition**: Hard-to-locate problems requiring multi-angle analysis.

**Identification Signals**:
- Conventional debugging methods ineffective
- Problem involves multiple system components
- Complex reproduction conditions

**Examples**:
- "Specific users cannot complete payment" - need to check user state, payment API, frontend flow
- "Mobile crashes on specific operations" - need to check frontend compatibility and backend data processing

### 5. Critical Path Modifications

**Definition**: Code changes affecting core functionality.

**Identification Signals**:
- Modifications involve core modules like authentication, payment, data security
- Changes affect multiple downstream features
- Modifications cannot be easily rolled back

**Examples**:
- "Refactor user authentication flow" - affects frontend login UI and backend authentication logic
- "Upgrade database schema" - affects backend models and frontend data display

## Validation Flow

### Phase 1: Parallel Invocation

**Default (2-way):** Send tasks to both Codex and Gemini simultaneously via MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`), each analyzing from their professional perspective.

**3-way escalation (optional):** For critical/high-uncertainty tasks involving DevOps, include Cursor (`mcp__cursor__cursor`) as a third perspective. Use 3-way only when the task has infrastructure/DevOps aspects alongside frontend/backend. When Cursor participates here, use `model: claude-4.5-opus-high-thinking`.

**Codex Task Template**:
```
## Background
[Problem/task description]

## Please analyze from backend/logic perspective

Focus on:
1. Whether API design and implementation are correct
2. Whether data flow and state management are reasonable
3. Performance bottlenecks and optimization opportunities
4. Security considerations
5. Error handling and edge cases

## Expected Output
- Analysis conclusion
- Issues found (if any)
- Suggested solutions
```

**Gemini Task Template**:
```
## Background
[Problem/task description]

## Please analyze from frontend/UI perspective

Focus on:
1. Whether component structure and rendering logic are correct
2. Whether user interaction and experience are smooth
3. Whether state management is reasonable
4. Styling and responsive design
5. Accessibility and compatibility

## Expected Output
- Analysis conclusion
- Issues found (if any)
- Suggested solutions
```

### Phase 2: Result Comparison

After collecting outputs from both models, perform comparative analysis:

```
┌─────────────────────────────────────────┐
│         Result Comparison Analysis      │
├─────────────────────────────────────────┤
│                                         │
│  Codex Conclusion   Gemini Conclusion   │
│      │                 │                │
│      └────────┬────────┘                │
│               │                         │
│      Comparative Analysis               │
│               │                         │
│      ┌────────┴────────┐                │
│      │                 │                │
│  Agreement        Divergence            │
│      │                 │                │
│      ▼                 ▼                │
│  Direct Adoption   Claude Arbitration   │
│                                         │
└─────────────────────────────────────────┘
```

### Phase 3: Comprehensive Conclusion

**Agreement Case**:
- Both models agree → direct adoption
- Record consensus conclusion, continue flow

**Divergence Case**:
- Models disagree → Claude arbitration
- Analyze reasons for divergence
- Combine both viewpoints to provide final conclusion
- Perform additional verification if necessary

## Output Format

### Standard Cross-Validation Report

```markdown
## Cross-Validation Report

### Validation Background
- **Trigger Reason**: [Full-stack issue/High uncertainty/Design decision/Complex bug/Critical modification]
- **Validation Scope**: [Files/modules involved]

### Codex Analysis (Backend Perspective via mcp__codex__codex)

#### Analysis Conclusion
[Codex's main conclusion]

#### Issues Found
1. [Issue 1]
2. [Issue 2]

#### Suggested Solution
[Codex's suggested solution]

### Gemini Analysis (Frontend Perspective via mcp__gemini__gemini)

#### Analysis Conclusion
[Gemini's main conclusion]

#### Issues Found
1. [Issue 1]
2. [Issue 2]

#### Suggested Solution
[Gemini's suggested solution]

### Comprehensive Conclusion

#### Points of Agreement
- [Consensus finding 1]
- [Consensus finding 2]

#### Points of Divergence
| Aspect | Codex View | Gemini View | Arbitration Conclusion |
|--------|-----------|-------------|------------------------|
| [Aspect 1] | [View] | [View] | [Conclusion] |

#### Final Recommendation
[Claude's final recommendation after synthesizing both analyses]

#### Follow-up Actions
1. [Action 1]
2. [Action 2]
```

### Divergence-Only Report (Default for Standard tasks)

For standard-complexity tasks, use this compact format that highlights only where models disagreed:

```text
## Cross-Validation Summary

**Agreement:** [1-2 sentence summary of shared conclusions]

**Divergences:**
| Aspect | Codex | Gemini | Resolution |
|--------|-------|--------|------------|
| [Only divergent points] | [View] | [View] | [Decision + rationale] |

**Action:** [What to do next based on resolution]
```

Use the full Standard Report format for Critical-complexity tasks or when divergences are extensive (3+ divergence rows).

### 3-Way Escalation Report (Optional)

When Cursor is included as a third perspective, extend the report:

```markdown
### Cursor Analysis (DevOps Perspective via mcp__cursor__cursor, `model: claude-4.5-opus-high-thinking`)

#### Analysis Conclusion
[Cursor's main conclusion]

#### Issues Found
1. [Issue 1]

#### Suggested Solution
[Cursor's suggested solution]

### Comprehensive Conclusion

#### Points of Divergence
| Aspect | Codex View | Gemini View | Cursor View | Arbitration Conclusion |
|--------|-----------|-------------|-------------|------------------------|
| [Aspect 1] | [View] | [View] | [View] | [Conclusion] |
```

## Quality Assurance

### Validation Result Credibility Assessment

| Situation | Credibility | Handling |
|-----------|-------------|----------|
| Both agree, sufficient evidence | High | Direct adoption |
| Both agree, insufficient evidence | Medium | Supplementary verification |
| Divergence, both reasonable | Medium | Claude arbitration |
| Divergence, one clearly wrong | Low (wrong side) | Adopt correct side |
| Both uncertain | Low | Need more information |

### Common Divergence Handling

1. **Technology Selection Divergence**
   - Evaluate pros and cons of each solution
   - Choose based on actual project situation

2. **Problem Location Divergence**
   - Verify in both directions
   - Determine true cause with evidence

3. **Solution Priority Divergence**
   - Evaluate impact scope and implementation cost
   - Choose solution with best cost-benefit ratio

## Performance Considerations

### Parallel Invocation Optimization

- Both MCP tool calls should execute in parallel to reduce wait time
- Use `&` background execution or MCP-aware parallel helpers

### Timeout Handling

- Single model call timeout: use completed result + Claude supplement (log which model timed out)
- Both timeout: BLOCKED — follow `GATE.md` fail-closed procedure (do not fall back to Claude independent analysis)

> **Note:** This aligns with the tiered failure policy in `GATE.md`. Cross-validation requires at least one external perspective to be meaningful.

### Cost Control

- Only trigger cross-validation when necessary
- Simple problems don't need dual-model verification
- Record validation history to avoid duplicate verification of same issues
