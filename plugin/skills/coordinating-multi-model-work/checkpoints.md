# Collaboration Checkpoints

## Overview

检查点用于在技能执行的关键阶段决定是否需要外部模型，并强制执行统一的证据协议（Evidence / BLOCKED）。

## Checkpoints

### CP1: Task Analysis（开始前）

目标：决定是否需要外部模型。

- 收集：任务目标、涉及文件、技术栈、风险/不确定性
- 使用：`coordinating-multi-model-work/routing-decision.md` 做语义路由

**Early exposure:** 一旦决定 `Routing != CLAUDE`，立刻执行 `GATE.md`（拿到 Evidence 或输出 BLOCKED），不要先写方案/写代码。

### CP2: Mid-Review（关键决策点）

触发：

- 方案分叉（2+ 可行路径，代价/风险不同）
- 调试不确定（根因不清、出现互相矛盾证据）
- 出现安全/性能/数据一致性疑虑

行为：优先使用 `CROSS_VALIDATION`，并同样遵循 early exposure + evidence。

### CP3: Quality Gate（输出前）

目标：在"最终输出/最终结论/声称通过测试/请求 code review"前做最后一次专家复核。

- 若 `Routing != CLAUDE`：必须先有 Evidence
- 外部失败：必须 BLOCKED（fail-closed）

## User Override

用户可以明确覆盖路由：

- "用 Codex" / "用 Gemini" / "交叉验证" → 强制对应 Routing
- "不要用外部模型" → 强制 `Routing = CLAUDE`
