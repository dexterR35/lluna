import { contextBridge, ipcRenderer, webUtils } from "electron";

const menuListeners = new Set();
ipcRenderer.on("menu:command", (_event, command) => {
  for (const listener of menuListeners) listener(command);
});

contextBridge.exposeInMainWorld("midgardDesktop", Object.freeze({
  getBackendSession: () => ipcRenderer.invoke("backend:session"),
  newWorkflow: () => ipcRenderer.invoke("workflow:new"),
  openWorkflow: () => ipcRenderer.invoke("workflow:open"),
  saveWorkflow: (document) => ipcRenderer.invoke("workflow:save", document),
  saveWorkflowAs: (document) => ipcRenderer.invoke("workflow:save-as", document),
  autosaveWorkflow: (document) => ipcRenderer.invoke("workflow:autosave", document),
  recoverWorkflow: () => ipcRenderer.invoke("workflow:recover"),
  clearRecovery: () => ipcRenderer.invoke("workflow:clear-recovery"),
  selectImageFiles: () => ipcRenderer.invoke("files:images"),
  registerDroppedFiles: (files) => ipcRenderer.invoke("files:dropped", files.map(file => webUtils.getPathForFile(file))),
  selectVideoFiles: () => ipcRenderer.invoke("files:videos"),
  selectMaskFile: () => ipcRenderer.invoke("files:mask"),
  selectDirectory: () => ipcRenderer.invoke("files:directory"),
  selectSaveFile: (kind) => ipcRenderer.invoke("files:save", kind),
  revealPath: (grantId) => ipcRenderer.invoke("native:reveal", grantId),
  openExternal: (urlId) => ipcRenderer.invoke("native:external", urlId),
  getPlatformInfo: () => ipcRenderer.invoke("native:platform"),
  setRunProgress: (progress) => ipcRenderer.send("run:progress", progress),
  onMenuCommand: (callback) => {
    menuListeners.add(callback);
    return () => menuListeners.delete(callback);
  },
}));
