#!/usr/bin/env bash
# PreToolUse hook for Task tool - 强制模型选择提醒

echo "⚠️ PreToolUse(Task): 首次 Task 前必须先单独输出【CP1 评估】（含字段，且同消息不得包含 tool 调用）。" >&2