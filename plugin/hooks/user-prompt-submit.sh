#!/usr/bin/env bash
# UserPromptSubmit hook for superpowers-ccg plugin

set -euo pipefail

REMINDER_TEXT="【CP 协议门槛（必须）】

1) 首次调用 Task 前：先单独输出【CP1 评估】（此消息不得包含 tool 调用）
2) 声称完成/请求 review/宣称验证通过前：先单独输出【CP3 评估】（此消息不得包含 tool 调用）

【CP1 评估】
- 任务类型: [前端/后端/全栈/其他]
- 路由决策: [CLAUDE/CODEX/GEMINI/CROSS_VALIDATION]
- 理由: ...

【CP3 评估】
- 任务类型: [前端/后端/全栈/其他]
- 路由决策: [CLAUDE/CODEX/GEMINI/CROSS_VALIDATION]
- 理由: ...

不满足 → 立刻停止，先补齐 CP 块再继续。
"

# Claude Code hooks 的事件 JSON 通过 stdin 传入；UserPromptSubmit 的 stdout 会被追加到上下文。
# 因此这里直接输出提醒，不再依赖 /tmp/prompt.json。
printf '%s\n' "$REMINDER_TEXT"
