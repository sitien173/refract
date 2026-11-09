import { spawnSync } from "node:child_process";
import { mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const committed = resolve(webRoot, "../src/refract/dashboard_static/app");
const tempRoot = mkdtempSync(join(tmpdir(), "refract-dashboard-bundle-"));
const output = join(tempRoot, "app");

function listFiles(root) {
  return readdirSync(root, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => relative(root, join(entry.parentPath, entry.name)).split("\\").join("/"))
    .sort();
}

try {
  const vite = join(webRoot, "node_modules/vite/bin/vite.js");
  const build = spawnSync(process.execPath, [vite, "build", "--outDir", output, "--emptyOutDir"], {
    cwd: webRoot,
    encoding: "utf8",
  });
  if (build.status !== 0) {
    process.stderr.write(build.stdout ?? "");
    process.stderr.write(build.stderr ?? "");
    process.exit(build.status ?? 1);
  }

  const expected = listFiles(committed);
  const actual = listFiles(output);
  const missing = expected.filter((name) => !actual.includes(name));
  const added = actual.filter((name) => !expected.includes(name));
  const changed = expected.filter((name) => actual.includes(name) && !readFileSync(join(committed, name)).equals(readFileSync(join(output, name))));
  if (missing.length || added.length || changed.length) {
    console.error("Committed dashboard bundle is stale.");
    if (missing.length) console.error(`Missing from build: ${missing.join(", ")}`);
    if (added.length) console.error(`Missing from committed bundle: ${added.join(", ")}`);
    if (changed.length) console.error(`Byte differences: ${changed.join(", ")}`);
    process.exitCode = 1;
  } else {
    console.log(`Dashboard bundle is current (${actual.length} files).`);
  }
} finally {
  rmSync(tempRoot, { recursive: true, force: true });
}
