#!/usr/bin/env bash
# UserPromptSubmit hook for superpowers-ccg plugin

set -euo pipefail

REMINDER_TEXT="⚠️ 多模型强制协议:
- Task工具: 代码实现→model:sonnet, 搜索探索→model:haiku
- 必须读取Skill coordinating-multi-model-work并评估CP1/CP2/CP3检查点
- 未遵守视为严重违规
"

# Claude Code hooks 的事件 JSON 通过 stdin 传入；UserPromptSubmit 的 stdout 会被追加到上下文。
# 因此这里直接输出提醒，不再依赖 /tmp/prompt.json。
printf '%s\n' "$REMINDER_TEXT"
