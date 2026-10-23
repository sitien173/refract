// Pi adapter: registers the Refract MCP server and injects the SessionStart context.
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const hook = JSON.parse(execFileSync(resolve(root, "hooks/refract-session-start.sh"), { encoding: "utf8" }));
const context: string = hook.hookSpecificOutput.additionalContext;

export default function refract(pi: ExtensionAPI) {
  pi.registerMcpServer("refract", {
    url: process.env.REFRACT_URL ?? "http://127.0.0.1:8765/mcp",
    exposure: "direct",
  });
  pi.on("before_agent_start", (event) => ({
    systemPrompt: event.systemPrompt + "\n\n" + context,
  }));
}
