import path from "node:path";
import { fileURLToPath } from "node:url";
import { AGENT_LABELS } from "./constants.mjs";
import {
  chmodExecutable,
  copyDirectory,
  copyFile,
  ensureDir,
  pathExists,
  readJsonIfExists,
  writeJson
} from "./io.mjs";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function source(...segments) {
  return path.join(packageRoot, ...segments);
}

function claudeHooksSettings() {
  return {
    hooks: {
      SessionStart: [
        {
          matcher: "startup|resume|clear|compact",
          hooks: [
            {
              type: "command",
              command: "\".claude/hooks/run-hook.cmd\" session-start.sh"
            }
          ]
        }
      ],
      UserPromptSubmit: [
        {
          matcher: "*",
          hooks: [
            {
              type: "command",
              command: "\".claude/hooks/run-hook.cmd\" user-prompt-submit.sh"
            }
          ]
        }
      ],
      PreToolUse: [
        {
          matcher: "Task",
          hooks: [
            {
              type: "command",
              command: "\".claude/hooks/run-hook.cmd\" pre-tool-use-task.sh"
            }
          ]
        }
      ]
    }
  };
}

function mergeMcp(existing) {
  const base = existing && typeof existing === "object" ? existing : {};
  const baseServers = base.mcpServers && typeof base.mcpServers === "object" ? base.mcpServers : {};
  const desired = JSON.parse(
    JSON.stringify({
      codex: {
        command: "uvx",
        args: ["--from", "git+https://github.com/GuDaStudio/codexmcp.git", "codexmcp"],
        env: {
          OPENAI_API_KEY: "${OPENAI_API_KEY}"
        }
      },
      gemini: {
        command: "uvx",
        args: ["--from", "git+https://github.com/GuDaStudio/geminimcp.git", "geminimcp"],
        env: {
          GEMINI_API_KEY: "${GEMINI_API_KEY}"
        }
      }
    })
  );

  return {
    ...base,
    mcpServers: {
      ...desired,
      ...baseServers
    }
  };
}

function mergeHooks(existing, desired) {
  const base = existing && typeof existing === "object" ? existing : {};
  const baseHooks = base.hooks && typeof base.hooks === "object" ? base.hooks : {};
  return {
    ...base,
    hooks: {
      ...baseHooks,
      ...desired.hooks
    }
  };
}

async function installClaudeCode(targetRoot, options, summary) {
  await copyFile(source("CLAUDE.md"), path.join(targetRoot, "CLAUDE.md"), options);
  await ensureDir(path.join(targetRoot, ".claude"), options.dryRun);
  await copyDirectory(source("skills"), path.join(targetRoot, ".claude", "skills"), options);
  await copyDirectory(source("commands"), path.join(targetRoot, ".claude", "commands"), options);
  await copyDirectory(source("agents"), path.join(targetRoot, ".claude", "agents"), options);
  await copyDirectory(source("hooks"), path.join(targetRoot, ".claude", "hooks"), options);

  const hookTargets = [
    path.join(targetRoot, ".claude", "hooks", "run-hook.cmd"),
    path.join(targetRoot, ".claude", "hooks", "session-start.sh"),
    path.join(targetRoot, ".claude", "hooks", "user-prompt-submit.sh"),
    path.join(targetRoot, ".claude", "hooks", "pre-tool-use-task.sh")
  ];
  for (const hookTarget of hookTargets) {
    await chmodExecutable(hookTarget, options.dryRun);
  }

  const settingsPath = path.join(targetRoot, ".claude", "settings.json");
  const existingSettings = await readJsonIfExists(settingsPath);
  const mergedSettings = mergeHooks(existingSettings, claudeHooksSettings());
  await writeJson(settingsPath, mergedSettings, options.dryRun);

  const projectMcpPath = path.join(targetRoot, ".mcp.json");
  const existingMcp = await readJsonIfExists(projectMcpPath);
  await writeJson(projectMcpPath, mergeMcp(existingMcp), options.dryRun);

  summary.push(`${AGENT_LABELS["claude-code"]}: installed CLAUDE.md, .claude skills/commands/agents/hooks, .claude/settings.json, and .mcp.json`);
}

async function installCursor(targetRoot, options, summary) {
  await copyFile(source("AGENTS.md"), path.join(targetRoot, "AGENTS.md"), options);
  await copyDirectory(source(".cursor", "rules"), path.join(targetRoot, ".cursor", "rules"), options);
  await copyDirectory(source(".cursor", "commands"), path.join(targetRoot, ".cursor", "commands"), options);
  await copyDirectory(source(".cursor", "skills"), path.join(targetRoot, ".cursor", "skills"), options);
  await copyDirectory(source(".cursor", "agents"), path.join(targetRoot, ".cursor", "agents"), options);
  await copyDirectory(source(".cursor", "hook-scripts"), path.join(targetRoot, ".cursor", "hook-scripts"), options);

  const existingHooks = await readJsonIfExists(path.join(targetRoot, ".cursor", "hooks.json"));
  const desiredHooks = await readJsonIfExists(source(".cursor", "hooks.json"));
  await writeJson(path.join(targetRoot, ".cursor", "hooks.json"), mergeHooks(existingHooks, desiredHooks), options.dryRun);

  const existingMcp = await readJsonIfExists(path.join(targetRoot, ".cursor", "mcp.json"));
  await writeJson(path.join(targetRoot, ".cursor", "mcp.json"), mergeMcp(existingMcp), options.dryRun);

  summary.push(`${AGENT_LABELS.cursor}: installed AGENTS.md and .cursor rules/commands/skills/agents/hooks/mcp`);
}

async function installAntigravity(targetRoot, options, summary) {
  await copyFile(source("AGENTS.md"), path.join(targetRoot, "AGENTS.md"), options);
  await copyFile(source("GEMINI.md"), path.join(targetRoot, "GEMINI.md"), options);
  await copyDirectory(source(".agent", "skills"), path.join(targetRoot, ".agent", "skills"), options);
  await copyFile(
    source("config", "antigravity", "mcp_config.example.json"),
    path.join(targetRoot, "config", "antigravity", "mcp_config.example.json"),
    options
  );

  summary.push(`${AGENT_LABELS.antigravity}: installed AGENTS.md, GEMINI.md, .agent/skills, and Antigravity MCP config example`);
}

const installers = {
  "claude-code": installClaudeCode,
  cursor: installCursor,
  antigravity: installAntigravity
};

export async function installAgents(targetRoot, agents, options) {
  if (!(await pathExists(targetRoot))) {
    throw new Error(`Target directory does not exist: ${targetRoot}`);
  }

  const summary = [];

  for (const agent of agents) {
    const installer = installers[agent];
    if (!installer) {
      throw new Error(`Unsupported agent: ${agent}`);
    }
    await installer(targetRoot, options, summary);
  }

  return summary;
}
