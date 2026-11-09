import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const port = process.env.E2E_PORT ?? "18765";
const serverDirectory = fileURLToPath(new URL("../", import.meta.url));
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  reporter: [["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL,
    headless: true,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "uv run python -m tests.e2e.serve_seeded",
    cwd: serverDirectory,
    url: `${baseURL}/dashboard/api/targets`,
    reuseExistingServer: !process.env.CI,
    gracefulShutdown: { signal: "SIGTERM", timeout: 15_000 },
    timeout: 120_000,
  },
});
