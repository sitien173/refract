import path from "node:path";
import process from "node:process";
import { AGENT_LABELS, SUPPORTED_AGENTS } from "./constants.mjs";
import { installAgents } from "./install.mjs";

function printHelp() {
  console.log(`superpowers-ccg

Install Superpowers CCG workflows at project level for supported agents.

Usage:
  superpowers-ccg setup [target] [--agent claude-code] [--agent cursor] [--agent antigravity] [--force] [--dry-run]
  superpowers-ccg list
  superpowers-ccg --help

Options:
  --agent <name>   Install for a specific agent. Repeatable or comma-separated.
  --all            Install for all supported agents (default when no --agent is given).
  --force          Overwrite existing files when needed.
  --dry-run        Print intended work without writing files.
  -h, --help       Show this help.

Supported agents:
  ${SUPPORTED_AGENTS.map((agent) => `${agent} (${AGENT_LABELS[agent]})`).join("\n  ")}
`);
}

function parseArgs(argv) {
  const parsed = {
    command: "setup",
    target: process.cwd(),
    agents: [],
    force: false,
    dryRun: false
  };

  const positionals = [];

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];

    if (arg === "-h" || arg === "--help") {
      parsed.command = "help";
      continue;
    }

    if (arg === "list") {
      parsed.command = "list";
      continue;
    }

    if (arg === "setup") {
      parsed.command = "setup";
      continue;
    }

    if (arg === "--force") {
      parsed.force = true;
      continue;
    }

    if (arg === "--dry-run") {
      parsed.dryRun = true;
      continue;
    }

    if (arg === "--all") {
      parsed.agents = [...SUPPORTED_AGENTS];
      continue;
    }

    if (arg === "--agent") {
      const next = argv[i + 1];
      if (!next) {
        throw new Error("--agent requires a value");
      }
      parsed.agents.push(...next.split(",").map((value) => value.trim()).filter(Boolean));
      i += 1;
      continue;
    }

    if (arg.startsWith("--agent=")) {
      parsed.agents.push(...arg.slice("--agent=".length).split(",").map((value) => value.trim()).filter(Boolean));
      continue;
    }

    if (arg.startsWith("-")) {
      throw new Error(`Unknown option: ${arg}`);
    }

    positionals.push(arg);
  }

  if (positionals.length > 0) {
    parsed.target = path.resolve(positionals[0]);
  }

  if (parsed.command === "setup" && parsed.agents.length === 0) {
    parsed.agents = [...SUPPORTED_AGENTS];
  }

  parsed.agents = [...new Set(parsed.agents)];

  for (const agent of parsed.agents) {
    if (!SUPPORTED_AGENTS.includes(agent)) {
      throw new Error(`Unsupported agent: ${agent}`);
    }
  }

  return parsed;
}

function printList() {
  console.log("Supported agents:");
  for (const agent of SUPPORTED_AGENTS) {
    console.log(`- ${agent}: ${AGENT_LABELS[agent]}`);
  }
}

function printNextSteps(selectedAgents) {
  console.log("\nNext steps:");

  if (selectedAgents.includes("claude-code")) {
    console.log("- Claude Code: open the project and verify `.claude/settings.json` and `.mcp.json` were picked up.");
  }

  if (selectedAgents.includes("cursor")) {
    console.log("- Cursor: reload the window after installation so `.cursor` changes are loaded.");
  }

  if (selectedAgents.includes("antigravity")) {
    console.log("- Antigravity: paste `config/antigravity/mcp_config.example.json` into the raw MCP config UI.");
  }
}

export async function runCli(argv) {
  const parsed = parseArgs(argv);

  if (parsed.command === "help") {
    printHelp();
    return;
  }

  if (parsed.command === "list") {
    printList();
    return;
  }

  const summary = await installAgents(parsed.target, parsed.agents, {
    force: parsed.force,
    dryRun: parsed.dryRun
  });

  if (parsed.dryRun) {
    console.log(`Dry run for ${parsed.target}`);
  } else {
    console.log(`Installed Superpowers CCG into ${parsed.target}`);
  }

  for (const line of summary) {
    console.log(`- ${line}`);
  }

  printNextSteps(parsed.agents);
}
