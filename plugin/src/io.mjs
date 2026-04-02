import { promises as fs } from "node:fs";
import path from "node:path";

export async function pathExists(targetPath) {
  try {
    await fs.access(targetPath);
    return true;
  } catch {
    return false;
  }
}

export async function ensureDir(targetPath, dryRun = false) {
  if (dryRun) {
    return;
  }
  await fs.mkdir(targetPath, { recursive: true });
}

export async function readJsonIfExists(targetPath) {
  if (!(await pathExists(targetPath))) {
    return null;
  }
  const content = await fs.readFile(targetPath, "utf8");
  return JSON.parse(content);
}

export async function writeJson(targetPath, value, dryRun = false) {
  if (dryRun) {
    return;
  }
  await fs.mkdir(path.dirname(targetPath), { recursive: true });
  await fs.writeFile(targetPath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

export async function copyFile(sourcePath, targetPath, { force = false, dryRun = false } = {}) {
  const exists = await pathExists(targetPath);
  if (exists && !force) {
    return "skipped";
  }
  if (!dryRun) {
    await fs.mkdir(path.dirname(targetPath), { recursive: true });
    await fs.copyFile(sourcePath, targetPath);
  }
  return exists ? "overwritten" : "created";
}

export async function copyDirectory(sourceDir, targetDir, options = {}) {
  const entries = await fs.readdir(sourceDir, { withFileTypes: true });
  const results = [];

  for (const entry of entries) {
    const sourcePath = path.join(sourceDir, entry.name);
    const targetPath = path.join(targetDir, entry.name);

    if (entry.isDirectory()) {
      if (!options.dryRun) {
        await fs.mkdir(targetPath, { recursive: true });
      }
      const nested = await copyDirectory(sourcePath, targetPath, options);
      results.push(...nested);
      continue;
    }

    const result = await copyFile(sourcePath, targetPath, options);
    results.push({ path: targetPath, result });
  }

  return results;
}

export async function chmodExecutable(targetPath, dryRun = false) {
  if (dryRun) {
    return;
  }
  try {
    await fs.chmod(targetPath, 0o755);
  } catch {
    // Ignore chmod failures on Windows and restricted filesystems.
  }
}
