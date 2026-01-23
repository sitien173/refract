#!/usr/bin/env bash
# UserPromptSubmit hook for superpowers-ccg plugin

set -euo pipefail

REMINDER_TEXT="⚠️ 多模型强制协议:
- Task工具: 代码实现→model:sonnet, 搜索探索→model:haiku
- 必须读取Skill coordinating-multi-model-work并评估CP1/CP2/CP3检查点
- 未遵守视为严重违规
"

jq --arg remind "$REMINDER_TEXT" '.user_input = $remind + .user_input' /tmp/prompt.json > /tmp/prompt.json.tmp && mv /tmp/prompt.json.tmp /tmp/prompt.json