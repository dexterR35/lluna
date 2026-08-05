import crypto from "node:crypto";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { spawn } from "node:child_process";
import { app } from "electron";

/** @returns {Promise<number>} */
function reservePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") return reject(new Error("Could not reserve backend port"));
      const port = address.port;
      server.close(() => resolve(port));
    });
  });
}

/** @param {string} startPath @returns {string | null} */
function findSourceRoot(startPath) {
  let candidate = path.resolve(startPath);
  while (true) {
    if (fs.existsSync(path.join(candidate, "backend", "api", "app.py"))) return candidate;
    const parent = path.dirname(candidate);
    if (parent === candidate) return null;
    candidate = parent;
  }
}

/** @param {string} projectRoot @returns {string[]} */
function installedVenvPython(projectRoot) {
  let venvName = "llunaEnv";
  try {
    const runtime = JSON.parse(fs.readFileSync(path.join(projectRoot, "lluna_runtime.json"), "utf8"));
    if (typeof runtime?.venv === "string" && runtime.venv) venvName = runtime.venv;
  } catch { /* Fall back to the installer default and .venv. */ }
  return process.platform === "win32"
    ? [
      path.join(projectRoot, venvName, "Scripts", "python.exe"),
      path.join(projectRoot, ".venv", "Scripts", "python.exe"),
    ]
    : [
      path.join(projectRoot, venvName, "bin", "python"),
      path.join(projectRoot, ".venv", "bin", "python"),
    ];
}

function resolveBackendCommand() {
  if (app.isPackaged) {
    const executable = process.platform === "win32" ? "lluna-backend.exe" : "lluna-backend";
    return { command: path.join(process.resourcesPath, "backend-sidecar", executable), args: [] };
  }
  const appRoot = app.getAppPath();
  const projectRoot = findSourceRoot(appRoot);
  if (!projectRoot) throw new Error(`Could not locate the Lluna source root from ${appRoot}`);
  const candidates = [
    ...installedVenvPython(projectRoot),
    ...(process.platform === "win32" ? ["python.exe"] : ["python3.12", "python3"]),
  ];
  const command = process.env.LLUNA_PYTHON || candidates.find((candidate) => !path.isAbsolute(candidate) || fs.existsSync(candidate)) || candidates.at(-1);
  if (!command) throw new Error("Could not resolve a Python executable");
  return { command, args: ["-m", "backend.api.app"], cwd: projectRoot };
}

/** @param {string} baseUrl @param {import("node:child_process").ChildProcess} child @param {number} [timeoutMs] */
async function waitForReady(baseUrl, child, timeoutMs = 30000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (child.exitCode !== null) throw new Error(`Python control plane exited with code ${child.exitCode}`);
    try {
      const response = await fetch(`${baseUrl}/ready`, { signal: AbortSignal.timeout(800) });
      if (response.ok && (await response.json()).ready) return;
    } catch { /* Best-effort fallback; the next state handles failure. */ }
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error("Python control plane did not become ready in time");
}

async function startPythonControlPlane() {
  const port = await reservePort();
  const token = crypto.randomBytes(48).toString("base64url");
  const baseUrl = `http://127.0.0.1:${port}`;
  const resolved = resolveBackendCommand();
  const logDir = app.getPath("logs");
  fs.mkdirSync(logDir, { recursive: true });
  const log = fs.createWriteStream(path.join(logDir, "backend.log"), { flags: "a" });
  const args = [...resolved.args, "--host", "127.0.0.1", "--port", String(port), "--token", token];
  const child = spawn(resolved.command, args, {
    cwd: resolved.cwd || process.resourcesPath,
    env: {
      ...process.env,
      LLUNA_SESSION_TOKEN: token,
      LLUNA_CONFIG_DIR: path.join(app.getPath("userData"), "config"),
      LLUNA_DATA_DIR: app.getPath("userData"),
      LLUNA_MODELS_DIR: path.join(app.getPath("userData"), "models"),
      PYTHONUNBUFFERED: "1",
    },
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout?.pipe(log, { end: false });
  child.stderr?.pipe(log, { end: false });
  try {
    await waitForReady(baseUrl, child);
  } catch (error) {
    child.kill();
    log.end();
    throw error;
  }
  async function stop() {
    if (child.exitCode !== null) return;
    child.kill("SIGTERM");
    await Promise.race([
      new Promise((resolve) => child.once("exit", resolve)),
      new Promise((resolve) => setTimeout(resolve, 3500)),
    ]);
    if (child.exitCode === null) child.kill("SIGKILL");
    log.end();
  }
  return { port, token, baseUrl, child, stop };
}

export { startPythonControlPlane };
