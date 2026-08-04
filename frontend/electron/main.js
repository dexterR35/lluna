/* global MAIN_WINDOW_VITE_DEV_SERVER_URL, MAIN_WINDOW_VITE_NAME */
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { app, BrowserWindow, dialog, ipcMain, powerSaveBlocker, shell } from "electron";

import { installNativeMenu } from "./native-menu.js";
import { startPythonControlPlane } from "./python-process.js";
import { installContentSecurityPolicy, installWindowSecurity, openApprovedExternal } from "./security.js";
import { createWindowStateStore } from "./window-state.js";

/** @typedef {Awaited<ReturnType<typeof startPythonControlPlane>>} BackendProcess */
/** @type {BrowserWindow | null} */
let mainWindow = null;
/** @type {BackendProcess | null} */
let backend = null;
/** @type {string | null} */
let currentWorkflowPath = null;
/** @type {number | null} */
let sleepBlockerId = null;
let shutdownStarted = false;
/** @type {Map<string, string>} */
const grants = new Map();

function workflowTemplate() {
  const now = new Date().toISOString();
  return { format: "midgard-workflow", version: 1, projectId: crypto.randomUUID(), name: "Untitled workflow", createdAt: now, updatedAt: now, nodes: [], edges: [], groups: [], projectSettings: {}, viewport: { x: 0, y: 0, zoom: 1 }, metadata: {} };
}

/** @param {string} filePath @param {"read" | "write" | "directory"} mode */
async function registerPathGrant(filePath, mode) {
  const activeBackend = backend;
  if (!activeBackend) throw new Error("Backend is not running");
  const response = await fetch(`${activeBackend.baseUrl}/api/desktop/grants`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Midgard-Token": activeBackend.token },
    body: JSON.stringify({ path: filePath, mode }),
  });
  if (!response.ok) throw new Error(`Could not register path grant (${response.status})`);
  const grant = await response.json();
  grants.set(grant.grantId, filePath);
  return grant;
}

/** @param {string} filePath @param {Record<string, any>} document */
async function writeWorkflow(filePath, document) {
  const normalized = filePath.endsWith(".midgard.json") ? filePath : `${filePath}.midgard.json`;
  const temporary = `${normalized}.tmp`;
  await fs.promises.mkdir(path.dirname(normalized), { recursive: true });
  await fs.promises.writeFile(temporary, `${JSON.stringify({ ...document, updatedAt: new Date().toISOString() }, null, 2)}
`, { encoding: "utf8", mode: 0o600 });
  await fs.promises.rename(temporary, normalized);
  currentWorkflowPath = normalized;
  await clearRecovery();
  return { saved: true, name: path.basename(normalized), displayPath: normalized };
}

/** @param {Record<string, any>} document */
async function saveAs(document) {
  if (!mainWindow) throw new Error("Main window is unavailable");
  const result = await dialog.showSaveDialog(mainWindow, { title: "Save Midgard Workflow", defaultPath: `${document.name || "workflow"}.midgard.json`, filters: [{ name: "Midgard Workflow", extensions: ["midgard.json", "json"] }] });
  if (result.canceled || !result.filePath) return null;
  return writeWorkflow(result.filePath, document);
}

function recoveryPath() { return path.join(app.getPath("userData"), "autosave", "last.midgard.json"); }
async function clearRecovery() { await fs.promises.unlink(recoveryPath()).catch(error => { if (!(error instanceof Error) || !("code" in error) || error.code !== "ENOENT") throw error; }); }
/** @param {Record<string, any>} document */
async function writeRecovery(document) { const target = recoveryPath(); await fs.promises.mkdir(path.dirname(target), { recursive: true }); const temporary = `${target}.tmp`; await fs.promises.writeFile(temporary, JSON.stringify(document), { encoding: "utf8", mode: 0o600 }); await fs.promises.rename(temporary, target); return true; }

function installIpc() {
  const activeBackend = backend;
  if (!activeBackend) throw new Error("Backend is not running");
  ipcMain.handle("backend:session", () => ({ baseUrl: activeBackend.baseUrl, token: activeBackend.token }));
  ipcMain.handle("workflow:new", async () => { currentWorkflowPath = null; await clearRecovery(); return workflowTemplate(); });
  ipcMain.handle("workflow:open", async () => {
    if (!mainWindow) throw new Error("Main window is unavailable");
    const result = await dialog.showOpenDialog(mainWindow, { title: "Open Midgard Workflow", properties: ["openFile"], filters: [{ name: "Midgard Workflow", extensions: ["json"] }] });
    if (result.canceled || !result.filePaths[0]) return null;
    const filePath = result.filePaths[0];
    const document = JSON.parse(await fs.promises.readFile(filePath, "utf8"));
    if (document.format !== "midgard-workflow") throw new Error("The selected file is not a Midgard workflow");
    currentWorkflowPath = filePath;
    return { document, name: path.basename(filePath), displayPath: filePath };
  });
  ipcMain.handle("workflow:save", (_event, document) => currentWorkflowPath ? writeWorkflow(currentWorkflowPath, document) : saveAs(document));
  ipcMain.handle("workflow:save-as", (_event, document) => saveAs(document));
  ipcMain.handle("workflow:autosave", (_event, document) => writeRecovery(document));
  ipcMain.handle("workflow:recover", async () => { try { return JSON.parse(await fs.promises.readFile(recoveryPath(), "utf8")); } catch (error) { if (error instanceof Error && "code" in error && error.code === "ENOENT") return null; throw error; } });
  ipcMain.handle("workflow:clear-recovery", () => clearRecovery());
  /** @param {string} kind @param {string[]} extensions */
  const chooseFiles = async (kind, extensions) => {
    if (!mainWindow) throw new Error("Main window is unavailable");
    const result = await dialog.showOpenDialog(mainWindow, { title: `Select ${kind}`, properties: ["openFile", "multiSelections"], filters: [{ name: kind, extensions }] });
    if (result.canceled) return [];
    return Promise.all(result.filePaths.map(async (filePath) => ({ ...(await registerPathGrant(filePath, "read")), name: path.basename(filePath) })));
  };
  ipcMain.handle("files:images", () => chooseFiles("Images", ["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"]));
  ipcMain.handle("files:dropped", async (_event, /** @type {string[]} */ paths) => Promise.all(paths.map(async (filePath) => ({ ...(await registerPathGrant(filePath, "read")), name: path.basename(filePath) }))));
  ipcMain.handle("files:videos", () => chooseFiles("Videos", ["mp4", "mov", "mkv", "webm", "avi"]));
  ipcMain.handle("files:mask", async () => (await chooseFiles("Mask", ["png", "jpg", "jpeg", "webp"])).at(0) || null);
  ipcMain.handle("files:directory", async () => {
    if (!mainWindow) throw new Error("Main window is unavailable");
    const result = await dialog.showOpenDialog(mainWindow, { properties: ["openDirectory", "createDirectory"] });
    return result.canceled ? null : registerPathGrant(result.filePaths[0], "directory");
  });
  ipcMain.handle("files:save", async (_event, kind) => {
    if (!mainWindow) throw new Error("Main window is unavailable");
    const video = kind === "video";
    const result = await dialog.showSaveDialog(mainWindow, { title: `Save ${video ? "Video" : "Image"}`, filters: [{ name: video ? "Video" : "Image", extensions: video ? ["mp4", "mkv"] : ["png", "jpg", "webp"] }] });
    return result.canceled || !result.filePath ? null : registerPathGrant(result.filePath, "write");
  });
  ipcMain.handle("files:write-in-directory", async (_event, directoryGrantId, fileName) => {
    const directoryPath = grants.get(directoryGrantId);
    if (!directoryPath) throw new Error("Unknown directory grant");
    const safeName = path.basename(String(fileName || "").trim());
    if (!safeName || safeName === "." || safeName === "..") {
      throw new Error("Invalid export file name");
    }
    const parsed = path.parse(safeName);
    let candidate = path.join(directoryPath, safeName);
    if (fs.existsSync(candidate)) {
      for (let number = 1; number < 10_000; number += 1) {
        const alternate = path.join(directoryPath, `${parsed.name}-${number}${parsed.ext}`);
        if (!fs.existsSync(alternate)) {
          candidate = alternate;
          break;
        }
      }
      if (fs.existsSync(candidate)) throw new Error("No available export file name in that folder");
    }
    return registerPathGrant(candidate, "write");
  });
  ipcMain.handle("native:reveal", async (_event, grantId) => {
    const filePath = grants.get(grantId);
    if (!filePath) throw new Error("Unknown path grant");
    shell.showItemInFolder(filePath);
    return true;
  });
  ipcMain.handle("native:external", (_event, id) => openApprovedExternal(id));
  ipcMain.handle("native:platform", () => ({ platform: process.platform, arch: process.arch, version: app.getVersion(), packaged: app.isPackaged }));
  ipcMain.on("run:progress", (_event, progress) => {
    const value = Number(progress);
    if (mainWindow && Number.isFinite(value)) mainWindow.setProgressBar(value < 0 ? -1 : Math.max(0, Math.min(1, value)));
    if (value >= 0 && value < 1 && sleepBlockerId === null) sleepBlockerId = powerSaveBlocker.start("prevent-app-suspension");
    if ((value < 0 || value >= 1) && sleepBlockerId !== null) { powerSaveBlocker.stop(sleepBlockerId); sleepBlockerId = null; }
  });
}

async function createWindow() {
  const stateStore = createWindowStateStore(app.getPath("userData"));
  const state = stateStore.load();
  const icon = app.isPackaged
    ? path.join(process.resourcesPath, "app-icon", "midgard.png")
    : path.join(app.getAppPath(), "assets", "app-icon", "midgard.png");
  mainWindow = new BrowserWindow({
    ...state, minWidth: 1100, minHeight: 700, show: false, backgroundColor: "#0b0f14",
    title: "Midgard", icon, autoHideMenuBar: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"), nodeIntegration: false,
      contextIsolation: true, sandbox: true, webSecurity: true,
    },
  });
  installWindowSecurity(mainWindow, MAIN_WINDOW_VITE_DEV_SERVER_URL);
  const window = mainWindow;
  window.on("close", () => stateStore.save(window));
  window.once("ready-to-show", () => { if (state.maximized) window.maximize(); window.show(); });
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) await window.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  else await window.loadFile(path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`));
  installNativeMenu(window, (command) => {
    if (command === "help:documentation") return void openApprovedExternal("documentation");
    if (command === "help:issues") return void openApprovedExternal("issues");
    if (command === "help:homepage") return void openApprovedExternal("homepage");
    window.webContents.send("menu:command", command);
  });
}

/** @param {unknown} error */
async function showStartupError(error) {
  const detail = "The local processing service did not become ready. Review backend.log in the Midgard logs directory, then restart the application.\n\n"
    + String(error instanceof Error ? error.message : error);
  dialog.showErrorBox("Midgard could not start", detail);
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on("second-instance", () => { if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); } });
  app.whenReady().then(async () => {
    try {
      installContentSecurityPolicy(MAIN_WINDOW_VITE_DEV_SERVER_URL);
      backend = await startPythonControlPlane();
      installIpc();
      await createWindow();
    } catch (error) {
      await showStartupError(error);
    }
  });
  app.on("before-quit", (event) => {
    if (shutdownStarted || !backend) return;
    event.preventDefault(); shutdownStarted = true;
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.close();
    void backend.stop().finally(() => app.quit());
  });
  app.on("window-all-closed", () => { if (!shutdownStarted && process.platform !== "darwin") app.quit(); });
}
