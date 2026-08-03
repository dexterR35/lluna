import fs from "node:fs";
import path from "node:path";
import { screen } from "electron";

/** @param {string} dataDir */
function createWindowStateStore(dataDir) {
  const file = path.join(dataDir, "window-state.json");
  function load() {
    try {
      const state = JSON.parse(fs.readFileSync(file, "utf8"));
      const displays = screen.getAllDisplays().map((item) => item.workArea);
      const visible = displays.some((area) => state.x < area.x + area.width && state.x + state.width > area.x && state.y < area.y + area.height && state.y + state.height > area.y);
      return visible ? state : { width: 1440, height: 900 };
    } catch {
      return { width: 1440, height: 900 };
    }
  }
  /** @param {import("electron").BrowserWindow} window */
  function save(window) {
    if (window.isDestroyed()) return;
    const bounds = window.getBounds();
    const state = { ...bounds, maximized: window.isMaximized() };
    fs.mkdirSync(dataDir, { recursive: true });
    const temporary = `${file}.tmp`;
    fs.writeFileSync(temporary, JSON.stringify(state));
    fs.renameSync(temporary, file);
  }
  return { load, save };
}

export { createWindowStateStore };
