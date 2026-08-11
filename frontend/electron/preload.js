import { contextBridge, ipcRenderer, webUtils } from "electron";

/** @type {Set<(command: string) => void>} */
const menuListeners = new Set();
ipcRenderer.on("menu:command", (_event, command) => {
  for (const listener of menuListeners) listener(command);
});

contextBridge.exposeInMainWorld("llunaDesktop", Object.freeze({
  getBackendSession: () => ipcRenderer.invoke("backend:session"),
  newWorkflow: () => ipcRenderer.invoke("workflow:new"),
  openWorkflow: () => ipcRenderer.invoke("workflow:open"),
  saveWorkflow: (/** @type {unknown} */ document) => ipcRenderer.invoke("workflow:save", document),
  saveWorkflowAs: (/** @type {unknown} */ document) => ipcRenderer.invoke("workflow:save-as", document),
  autosaveWorkflow: (/** @type {unknown} */ document) => ipcRenderer.invoke("workflow:autosave", document),
  recoverWorkflow: () => ipcRenderer.invoke("workflow:recover"),
  clearRecovery: () => ipcRenderer.invoke("workflow:clear-recovery"),
  selectImageFiles: () => ipcRenderer.invoke("files:images"),
  registerDroppedFiles: (/** @type {File[]} */ files) => ipcRenderer.invoke("files:dropped", files.map(file => webUtils.getPathForFile(file))),
  selectVideoFiles: () => ipcRenderer.invoke("files:videos"),
  selectMaskFile: () => ipcRenderer.invoke("files:mask"),
  selectModelFile: () => ipcRenderer.invoke("models:file"),
  selectModelFolder: () => ipcRenderer.invoke("models:folder"),
  selectDirectory: () => ipcRenderer.invoke("files:directory"),
  selectSaveFile: (/** @type {"image" | "video"} */ kind) => ipcRenderer.invoke("files:save", kind),
  writeGrantInDirectory: (
    /** @type {string} */ directoryGrantId,
    /** @type {string} */ fileName,
  ) => ipcRenderer.invoke("files:write-in-directory", directoryGrantId, fileName),
  prepareDirectoryWrites: (
    /** @type {string} */ directoryGrantId,
    /** @type {string[]} */ fileNames,
  ) => ipcRenderer.invoke("files:prepare-directory-writes", directoryGrantId, fileNames),
  openExternal: (/** @type {string} */ urlId) => ipcRenderer.invoke("native:external", urlId),
  openHuggingFace: (/** @type {string} */ url) => ipcRenderer.invoke("native:huggingface", url),
  setRunProgress: (/** @type {number} */ progress) => ipcRenderer.send("run:progress", progress),
  onMenuCommand: (/** @type {(command: string) => void} */ callback) => {
    menuListeners.add(callback);
    return () => menuListeners.delete(callback);
  },
}));
