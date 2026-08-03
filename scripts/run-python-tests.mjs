import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const executableName = process.platform === "win32" ? "python.exe" : "python";
const executableIn = (directory) =>
  directory
    ? path.join(directory, process.platform === "win32" ? "Scripts" : "bin", executableName)
    : null;

let installedEnvironment = "midgardEnv";
try {
  const runtime = JSON.parse(fs.readFileSync(path.join(root, "midgard_runtime.json"), "utf8"));
  if (typeof runtime.venv === "string" && runtime.venv) installedEnvironment = runtime.venv;
} catch {
  // The runtime manifest is optional in source checkouts.
}

const localCandidates = [
  process.env.MIDGARD_PYTHON || null,
  executableIn(process.env.VIRTUAL_ENV),
  executableIn(path.join(root, installedEnvironment)),
  executableIn(path.join(root, ".venv")),
].filter(Boolean);
const localPython = localCandidates.find((candidate) => fs.existsSync(candidate));
const command = localPython || (process.platform === "win32" ? "py" : "python3.12");
const prefix = !localPython && process.platform === "win32" ? ["-3.12"] : [];
const pytestArgs = process.argv.slice(2);
const result = spawnSync(command, [...prefix, "-m", "pytest", ...(pytestArgs.length ? pytestArgs : ["-q"])], {
  cwd: root,
  env: process.env,
  stdio: "inherit",
});

if (result.error) {
  console.error(`Unable to start the supported Python 3.12 test runtime: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
