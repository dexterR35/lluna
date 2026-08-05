import { create } from "zustand";

/** @type {import("../types").DesktopValues} */
const defaults = {
  libraryVisible: true,
  libraryCollapsed: false,
  drawerVisible: true,
  minimapVisible: true,
  settingsOpen: false,
  settingsSection: "editor",
  modelsOpen: false,
  drawerTab: "logs",
  libraryWidth: 248,
  drawerHeight: 190,
};

/** @returns {import("../types").DesktopValues} */
function load() {
  try {
    return { ...defaults, ...JSON.parse(localStorage.getItem("lluna-layout") || "{}") };
  } catch {
    return defaults;
  }
}

/** @type {import("zustand").StateCreator<import("../types").DesktopState>} */
const createDesktopState = (set, get) => ({
  ...load(),
  setValue: (key, value) => {
    if (get()[key] === value) return;
    set(/** @type {Partial<import("../types").DesktopState>} */ ({ [key]: value }));
    localStorage.setItem("lluna-layout", JSON.stringify({ ...get(), [key]: value, setValue: undefined, reset: undefined }));
  },
  toggle: (key) => {
    const current = get()[key];
    if (typeof current === "boolean") get().setValue(key, !current);
  },
  reset: () => {
    set(defaults);
    localStorage.removeItem("lluna-layout");
  },
});

export const useDesktopStore = create(createDesktopState);
