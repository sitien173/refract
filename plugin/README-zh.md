# Superpowers-CCG

中文 | [English](README.md)

Superpowers-CCG 是 [obra/superpowers](https://github.com/obra/superpowers) 的增强版本/变体：保留“skills 驱动开发工作流”，并加入 **CCG 多模型协作**——由 Claude 负责编排，在需要时把任务路由给 **Codex MCP**（后端）与 **Gemini MCP**（前端），复杂场景可进行交叉验证。

## 你会得到什么

- **CCG 多模型路由**：后端交给 Codex、前端交给 Gemini；不确定/高影响场景可用 **CROSS_VALIDATION**。
- **MCP 工具集成**：外部模型调用通过 MCP tools 完成：`mcp__codex__codex`、`mcp__gemini__gemini`。
- **协作检查点**：在关键 skills 中嵌入 CP1/CP2/CP3 检查点，用于决定何时调用外部模型并沉淀证据。

## 快速开始（Claude Code）

### 前置条件

- 已安装 Claude Code CLI（`claude --version` 可用）
- 本机可用 `uvx`（下方 MCP 安装命令会用到）

### 安装

1）添加 marketplace

```bash
/plugin marketplace add https://github.com/BryanHoo/superpowers-ccg
```

2）安装插件

```bash
/plugin install superpowers-ccg@BryanHoo-superpowers-ccg
```

### MCP 安装（必需）

安装完成后，需要配置 Codex MCP 和 Gemini MCP，编排器才能进行外部模型路由。

```bash
claude mcp add gemini -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/geminimcp.git geminimcp
claude mcp add codex -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/codexmcp.git codexmcp
```

## 如何调用 Codex / Gemini 能力

通常不需要你手动调用 MCP tools；你只要明确需求，Claude 会在工作流里决定是否调用外部模型。

- 后端任务："后端/API/数据库部分用 Codex MCP，返回 patch 即可。"
- 前端任务："UI/组件/样式用 Gemini MCP，返回 patch 即可。"
- 交叉验证："请用 CROSS_VALIDATION（Codex + Gemini）复核方案并对冲遗漏。"

注意：发送给 Codex/Gemini 的提示词通常要求使用**英文**以保持一致性（你与 Claude 的对话仍可用中文）。

## 按任务选择模型（建议）

| 任务类型 | 推荐路由 | 原因 |
|---|---|---|
| 后端（API、DB、鉴权、性能） | CODEX | 更擅长后端 patch 建议 |
| 前端（UI、组件、样式） | GEMINI | 更擅长 UI 细节与组件化 |
| 全栈/不确定/高影响改动 | CROSS_VALIDATION | 双模型复核，提高覆盖率 |
| 文档/小改动 | CLAUDE | 成本更低且足够 |

路由与检查点规则参考：`skills/coordinating-multi-model-work/`。

## 与原版 Superpowers（obra/superpowers）的差异

- **内置多模型路由**：通过 MCP tools（`mcp__codex__codex`、`mcp__gemini__gemini`）调用外部模型。
- **CP 检查点机制**：CP1/CP2/CP3 用于证据驱动协作与 Fail-Closed 约束。
- **Skills 集合调整**：新增/改名以适配 CCG 协作流程。
- **安装源不同**：从 `https://github.com/BryanHoo/superpowers-ccg` 安装。

## 更新

```bash
/plugin update superpowers-ccg
```

## 测试

Claude Code skills 测试说明见：`tests/claude-code/README.md`。

## 许可证

MIT License - 详见 `LICENSE`。

## 支持

- Issues: https://github.com/BryanHoo/superpowers-ccg/issues

## 致谢

- [obra/superpowers](https://github.com/obra/superpowers) - 原始 Superpowers 项目
- [fengshao1227/ccg-workflow](https://github.com/fengshao1227/ccg-workflow) - CCG 工作流
- [GuDaStudio/geminimcp](https://github.com/GuDaStudio/geminimcp) - Gemini MCP
- [GuDaStudio/codexmcp](https://github.com/GuDaStudio/codexmcp) - Codex MCP
