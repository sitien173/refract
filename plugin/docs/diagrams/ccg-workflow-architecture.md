# CCG Workflow Architecture Diagrams

> Generated from CCG workflow analysis on 2026-03-24.
> Render with any Mermaid-compatible tool.

## 1. High-Level System Architecture

```mermaid
graph TB
    USER[User Request]
    CLAUDE[Claude Planner<br/>Reviewer<br/>Integrator]
    CODEX[Codex MCP<br/>Default Executor]
    GEMINI[Gemini MCP<br/>UI-heavy Executor]
    CP4[Claude CP4<br/>Phase Review]

    USER --> CLAUDE
    CLAUDE --> CODEX
    CLAUDE --> GEMINI
    CODEX --> CLAUDE
    GEMINI --> CLAUDE
    CLAUDE --> CP4
```

## 2. Routing Decision Tree

```mermaid
flowchart LR
    PHASE[Phase] --> DECIDE{Domain}
    DECIDE -->|Most implementation| CODEX_R[CODEX]
    DECIDE -->|UI-heavy visual work| GEMINI_R[GEMINI]
    DECIDE -->|Unresolved architecture| CROSS[CROSS_VALIDATION]
    DECIDE -->|Planning, review, docs| CLAUDE_R[CLAUDE]
```

## 3. Checkpoint Flow

```mermaid
flowchart TD
    START[User Request] --> CP0[CP0: Context Acquisition]
    CP0 --> ARTIFACTS[CP0 Context Artifacts]
    ARTIFACTS --> CP1[CP1: Phase Assessment & Routing]
    CP1 --> BUNDLE[Phase Context Bundle]
    BUNDLE --> MODEL[External Model]
    MODEL --> CP2[CP2: External Execution]
    CP2 --> CP3[CP3: Reconciliation]
    CP3 --> CP4[CP4: Phase Review]
    CP4 --> INTEGRATE[Integration Checks]
    INTEGRATE --> DONE[Complete]
```
