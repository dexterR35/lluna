import { create } from "zustand";
import { api } from "../api/client";

/** @type {import("zustand").StateCreator<import("../types").ServerState>} */
const createServerState = (set, get) => ({
  nodes: [],
  settings: null,
  models: [],
  capabilities: null,
  diagnostics: null,
  downloads: { active: [], pending: [], recent: [] },
  loading: false,
  error: null,
  async bootstrap() {
    set({ loading: true, error: null });
    try {
      const [nodes, settings, models, capabilities, diagnostics, downloads] = await Promise.all([
        api("/api/nodes"), api("/api/settings"), api("/api/models"),
        api("/api/capabilities"), api("/api/diagnostics"), api("/api/downloads"),
      ]);
      set({ nodes, settings, models, capabilities, diagnostics, downloads, loading: false });
    } catch (error) {
      set({ loading: false, error: error instanceof Error ? error.message : String(error) });
    }
  },
  async refreshModels() {
    const models = await api("/api/models");
    set({ models });
    return models;
  },
  async refreshNodes() {
    const nodes = await api("/api/nodes");
    set({ nodes });
    return nodes;
  },
  async refreshDownloads() {
    const downloads = await api("/api/downloads");
    set({ downloads });
    return downloads;
  },
  setModelLifecycleState(modelId, patch) {
    set((state) => ({
      models: state.models.map((model) =>
        model.id === modelId ? { ...model, ...patch } : model,
      ),
    }));
  },
  async updateSettings(patch) { set({ settings: await api("/api/settings", { method: "PUT", body: JSON.stringify(patch) }) }); },
  async resetSettings(section) { set({ settings: await api(`/api/settings/reset/${section}`, { method: "POST" }) }); },
  handleEvent(event) {
    if (event.type === "settings.changed") void get().bootstrap();
    if (event.type === "download.queue.updated") {
      set({
        downloads: {
          active: event.payload.active || [],
          pending: event.payload.pending || [],
          recent: event.payload.recent || [],
        },
      });
      return;
    }
    if (event.type === "download.queued") void get().refreshDownloads();
    if (
      [
        "download.completed",
        "download.failed",
        "download.cancelled",
        "model.changed",
        "model.action.failed",
      ].includes(event.type)
    ) {
      void get().refreshModels();
      if (event.type === "model.changed" || event.type === "download.completed") {
        void get().refreshNodes();
      }
      void get().refreshDownloads();
    }
  },
});

export const useServerStore = create(createServerState);
