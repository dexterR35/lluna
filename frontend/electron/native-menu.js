import { Menu, app } from "electron";

const item = (label, command, accelerator, extra = {}) => ({ label, accelerator, click: () => extra.dispatch(command), ...extra });

function installNativeMenu(window, dispatch) {
  const options = { dispatch };
  const template = [
    { label: "File", submenu: [
      item("New Workflow", "workflow:new", "CmdOrCtrl+N", options), item("Open Workflow…", "workflow:open", "CmdOrCtrl+O", options),
      { label: "Open Recent", submenu: [{ label: "No recent workflows", enabled: false }] }, { type: "separator" },
      item("Save", "workflow:save", "CmdOrCtrl+S", options), item("Save As…", "workflow:save-as", "CmdOrCtrl+Shift+S", options),
      item("Import Workflow…", "workflow:import", undefined, options), item("Export Workflow…", "workflow:export", undefined, options), item("Export Canvas Image…", "canvas:export", undefined, options),
      { type: "separator" }, item("Reveal Project Folder", "project:reveal", undefined, options), { role: process.platform === "darwin" ? "close" : "quit" },
    ]},
    { label: "Edit", submenu: [
      item("Undo", "edit:undo", "CmdOrCtrl+Z", options), item("Redo", "edit:redo", "CmdOrCtrl+Shift+Z", options), { type: "separator" },
      item("Cut", "edit:cut", "CmdOrCtrl+X", options), item("Copy", "edit:copy", "CmdOrCtrl+C", options), item("Paste", "edit:paste", "CmdOrCtrl+V", options), item("Duplicate", "edit:duplicate", "CmdOrCtrl+D", options), item("Delete", "edit:delete", "Delete", options),
      { type: "separator" }, item("Select All", "edit:select-all", "CmdOrCtrl+A", options), item("Deselect All", "edit:deselect", "Escape", options), item("Find Node", "node:search", "Tab", options), item("Preferences", "view:settings", "CmdOrCtrl+,", options),
    ]},
    { label: "View", submenu: [
      item("Zoom In", "view:zoom-in", "CmdOrCtrl+=", options), item("Zoom Out", "view:zoom-out", "CmdOrCtrl+-", options), item("Actual Size", "view:actual-size", "CmdOrCtrl+0", options), item("Fit Workflow", "view:fit", "F", options), item("Center Selection", "view:center-selection", "Shift+F", options),
      { type: "separator" }, item("Toggle Node Library", "view:library", undefined, options), item("Toggle Minimap", "view:minimap", undefined, options), item("Toggle Logs", "view:logs", undefined, options), item("Toggle Downloads", "view:downloads", undefined, options), item("Reset Layout", "view:reset-layout", undefined, options),
      { role: "togglefullscreen", accelerator: "F11" }, ...(process.env.NODE_ENV === "development" ? [{ role: "toggleDevTools" }] : []),
    ]},
    { label: "Workflow", submenu: [
      item("Validate", "run:validate", undefined, options), item("Run", "run:start", "CmdOrCtrl+Enter", options), item("Run Selected", "run:selected", undefined, options), item("Run From Selected", "run:from-selected", undefined, options),
      { type: "separator" }, item("Pause", "run:pause", "Space", options), item("Resume", "run:resume", undefined, options), item("Stop", "run:stop", "Escape", options),
      { type: "separator" }, item("Clear Cache", "run:clear-cache", undefined, options), item("Clear Selected Cache", "run:clear-selected-cache", undefined, options), item("Release GPU Models", "models:release", undefined, options),
    ]},
    { label: "Nodes", submenu: [
      item("Add Node", "node:search", "Tab", options), item("Group Selection", "node:group", undefined, options), item("Ungroup", "node:ungroup", undefined, options), { type: "separator" },
      item("Enable", "node:enable", undefined, options), item("Disable", "node:disable", undefined, options), item("Collapse", "node:collapse", undefined, options), item("Expand", "node:expand", undefined, options), item("Auto Layout", "node:auto-layout", undefined, options),
    ]},
    { label: "Models", submenu: [item("Manage Models", "view:models", undefined, options), item("Download Queue", "view:downloads", undefined, options), item("Refresh Model Status", "models:refresh", undefined, options), item("Open Models Directory", "models:directory", undefined, options), item("Release Loaded Models", "models:release", undefined, options)] },
    { label: "Help", submenu: [item("Documentation", "help:documentation", undefined, options), item("Node Authoring Guide", "help:nodes", undefined, options), item("Keyboard Shortcuts", "help:shortcuts", undefined, options), item("Diagnostics", "view:diagnostics", undefined, options), item("Check for Updates", "updates:check", undefined, options), item("Report an Issue", "help:issues", undefined, options), item("Project Homepage", "help:homepage", undefined, options), { role: "about" }] },
  ];
  if (process.platform === "darwin") template.unshift({ label: app.name, submenu: [{ role: "about" }, { type: "separator" }, { role: "services" }, { type: "separator" }, { role: "hide" }, { role: "hideOthers" }, { role: "unhide" }, { type: "separator" }, { role: "quit" }] });
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

export { installNativeMenu };
