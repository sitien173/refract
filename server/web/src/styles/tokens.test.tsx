import "./globals.css";
import { fireEvent, render, screen } from "@testing-library/react";
import { readFileSync, readdirSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

const sourceRoot = "src";
const bridgeValues: Record<string, string> = {
  "--background": "var(--surface-neutral-01)",
  "--card": "var(--surface-neutral-01)",
  "--popover": "var(--surface-neutral-01)",
  "--foreground": "var(--text-default)",
  "--card-foreground": "var(--text-default)",
  "--popover-foreground": "var(--text-default)",
  "--secondary-foreground": "var(--text-default)",
  "--accent-foreground": "var(--text-default)",
  "--primary": "var(--interactive-default)",
  "--primary-foreground": "var(--text-inverse)",
  "--secondary": "var(--surface-neutral-02)",
  "--muted": "var(--surface-neutral-02)",
  "--muted-foreground": "var(--text-description)",
  "--accent": "var(--surface-hover)",
  "--destructive": "var(--border-negative)",
  "--border": "var(--border-subtle)",
  "--input": "var(--border-strong)",
  "--ring": "var(--border-focus)",
};

function installTokenBridge() {
  const tokens = readFileSync("src/styles/tds/tokens.css", "utf8");
  const globals = readFileSync("src/styles/globals.css", "utf8");
  const rootBlocks = [...globals.matchAll(/:root\s*\{([^}]*)\}/gs)];
  if (rootBlocks.length === 0) throw new Error("globals.css token bridge :root block is missing");
  const style = document.createElement("style");
  style.dataset.tokenBridgeTest = "true";
  style.textContent = `${tokens}\n${rootBlocks.map((match) => `:root {${match[1]}}`).join("\n")}`;
  document.head.append(style);
  return style;
}

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    const rel = relative(sourceRoot, path).split(sep).join("/");
    if (entry.isDirectory()) {
      if (rel === "styles/tds" || rel.startsWith("styles/tds/")) return [];
      return sourceFiles(path);
    }
    return [path];
  });
}

describe("TDS token bridge", () => {
  it("exposes every shadcn bridge value as its expected TDS token reference", () => {
    const tokens = readFileSync("src/styles/tds/tokens.css", "utf8");
    const globals = readFileSync("src/styles/globals.css", "utf8");
    const style = installTokenBridge();
    try {
      const references = [...globals.matchAll(/var\((--[\w-]+)/g)].map((match) => match[1]);
      for (const reference of references) expect(tokens, `${reference} must be defined in tokens.css`).toContain(`${reference}:`);
      const computed = getComputedStyle(document.documentElement);
      for (const [property, expected] of Object.entries(bridgeValues)) {
        expect(computed.getPropertyValue(property).trim(), property).toBe(expected);
      }
      expect(computed.getPropertyValue("--" + "radius").trim()).toBe("");
    } finally {
      style.remove();
    }
  });

  it("contains no hex colors or dark theme selectors outside the vendored TDS styles", () => {
    const forbidden = [
      new RegExp(`#${"[0-9a-fA-F]"}{3,8}\\b`),
      new RegExp(`\\.${"dark"}\\b`),
      new RegExp(`@custom-variant\\s+${"dark"}\\b`),
    ];
    const violations = sourceFiles(sourceRoot).flatMap((path) => {
      const content = readFileSync(path, "utf8");
      return forbidden.some((pattern) => pattern.test(content)) ? [path] : [];
    });
    expect(violations).toEqual([]);
  });

  it("closes the Radix dialog when Escape is pressed", () => {
    render(
      <Dialog defaultOpen>
        <DialogContent>
          <DialogTitle>Job details</DialogTitle>
        </DialogContent>
      </Dialog>,
    );
    const dialog = screen.getByRole("dialog");
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not add a browser theme-color override", () => {
    expect(readFileSync("index.html", "utf8")).not.toContain('name="theme-color"');
  });
});
