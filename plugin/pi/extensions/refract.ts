// Pi adapter: registers the Refract MCP server and injects the SessionStart context.
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

export default function refract(pi: ExtensionAPI) {
  let context: string | undefined;
  pi.registerFlag("no-refract", { description: "Disable the Refract MCP server and coordinator context", type: "boolean" });
  // Flags are parsed after extensions load, so wait for session_start before reading them.
  pi.on("session_start", () => {
    if (context !== undefined) return;
    const disabled = pi.getFlag("no-refract") || /^(1|true|yes)$/i.test(process.env.REFRACT_DISABLE ?? "");
    const env = disabled ? { ...process.env, REFRACT_DISABLE: "1" } : process.env;
    // The hook skips the daemon check when disabled and returns a notice to ignore Refract.
    const hook = JSON.parse(execFileSync("python3", [resolve(root, "hooks/refract-session-start.py"), "--pi"], { encoding: "utf8", env }));
    context = hook.hookSpecificOutput.additionalContext;
    if (disabled) return;
    pi.registerMcpServer("refract", {
      url: process.env.REFRACT_URL ?? "http://127.0.0.1:8765/mcp",
      exposure: "direct",
    });
  });
  pi.on("before_agent_start", (event) => (context ? { systemPrompt: event.systemPrompt + "\n\n" + context } : undefined));
}
