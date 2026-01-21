# Superpowers-CCG

中文 | [English](README.md)

Superpowers-CCG 是 [obra/superpowers](https://github.com/obra/superpowers) 的增强版本/变体，在同样的“skills 驱动开发工作流”基础上，加入了 CCG 多模型协作能力（Claude + Codex + Gemini）。

## 快速安装（Claude Code）

1）添加 marketplace

```bash
/plugin marketplace add https://github.com/BryanHoo/superpowers-ccg
```

2）安装插件

```bash
/plugin install superpowers-ccg@BryanHoo-superpowers-ccg
```

安装完成后，`codeagent-wrapper` 会自动配置到 `~/.claude/bin/`（无需手动复制）。

### 验证

- 确认 wrapper 存在：`~/.claude/bin/codeagent-wrapper`

## 与原版 Superpowers（obra/superpowers）的差异

- **CCG 多模型路由**：Superpowers-CCG 可以把任务路由给 **Codex**（后端）和 **Gemini**（前端）；复杂场景可做双模型交叉验证。
- **内置 `codeagent-wrapper`**：本仓库/插件随附用于调用外部模型的 wrapper；上游 Superpowers 不包含。
- **引入多模型协作检查点**：在关键 skills 中嵌入 CP1/CP2/CP3 检查点，让编排器能在合适时机决定是否调用 Codex/Gemini。
- **Skills 集合有差异（新增/改名）**：包含 `coordinating-multi-model-work` 等面向多模型协作的 skill，与上游命名与内容不完全一致。
- **模型间通信使用英文**：发送给 Codex/Gemini 的提示词通常要求使用英文以保证一致性（你与 agent 的对话仍可用中文）。
- **安装源不同**：从 `https://github.com/BryanHoo/superpowers-ccg` 安装，而不是 `obra/superpowers-marketplace`。

## 工作原理（简版）

- Claude 负责编排整体流程（需求澄清 -> 计划 -> 执行 -> 审查）。
- 对适配的任务，通过 `codeagent-wrapper` 调用 Codex/Gemini。
- 外部模型只返回 patch，由编排器审阅后再应用。

## 更新

```bash
/plugin update superpowers-ccg
```

## 许可证

MIT License - 详见 `LICENSE`。

## 支持

- Issues: https://github.com/BryanHoo/superpowers-ccg/issues

## 致谢

- [obra/superpowers](https://github.com/obra/superpowers) - 原始 Superpowers 项目
- [fengshao1227/ccg-workflow](https://github.com/fengshao1227/ccg-workflow) - CCG 工作流
- [cexll/myclaude](https://github.com/cexll/myclaude) - codeagent-wrapper
