# CCG Workflow Architecture Diagrams

> Generated from CCG workflow analysis on 2026-03-24.
> Render with any Mermaid-compatible tool.

## 1. High-Level System Architecture

```mermaid
graph TB
    USER[User Request]
    CLAUDE[Claude Orchestrator]
    CODEX[Codex MCP<br/>Backend and Systems]
    GEMINI[Gemini MCP<br/>Frontend]
    CP4[Claude CP4<br/>Final Spec Review]

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
    TASK[Task] --> DECIDE{Domain}
    DECIDE -->|Backend, scripts, CI/CD, infra| CODEX_R[CODEX]
    DECIDE -->|UI, components, styling| GEMINI_R[GEMINI]
    DECIDE -->|Full-stack or unclear| CROSS[CROSS_VALIDATION]
    DECIDE -->|Docs only| CLAUDE_R[CLAUDE]
```

## 3. Checkpoint Flow

```mermaid
flowchart TD
    START[User Request] --> CP0[CP0: Context Acquisition]
    CP0 --> ARTIFACTS[CP0 Context Artifacts]
    ARTIFACTS --> CP1[CP1: Task Assessment & Routing]
    CP1 --> BUNDLE[Task Context Bundle]
    BUNDLE --> MODEL[External Model]
    MODEL --> CP2[CP2: External Execution]
    CP2 --> CP3[CP3: Reconciliation]
    CP3 --> CP4[CP4: Final Spec Review]
    CP4 --> DONE[Complete]
```
