import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const root = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  root,
  base: "/dashboard/",
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": resolve(root, "src") } },
  build: {
    outDir: resolve(root, "../src/refract/dashboard_static/app"),
    emptyOutDir: true,
    assetsDir: "assets",
  },
  test: {
    environment: "jsdom",
    // Under Node the package resolves to its server build, which skips panel registration.
    // Tests must exercise the same browser build that Vite bundles.
    alias: {
      "react-resizable-panels": resolve(root, "node_modules/react-resizable-panels/dist/react-resizable-panels.browser.development.js"),
    },
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    maxWorkers: 2,
  },
});
