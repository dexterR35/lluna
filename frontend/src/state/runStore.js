import { create } from "zustand";
import { api } from "../api/client";
import { useEditorStore } from "./editorStore";
/** @typedef {import("../types").RunState} RunState */
const terminal = new Set(["COMPLETED", "FAILED", "CANCELLED"]);
/** @type {Record<string, string>} */
const nodeStatus = {
  started: "RUNNING",
  progress: "RUNNING",
  completed: "SUCCEEDED",
  cached: "CACHED",
  failed: "FAILED",
  cancelled: "CANCELLED",
  queued: "QUEUED",
  paused: "PAUSED",
};
/** @type {import("zustand").StateCreator<RunState>} */
const createRunState = (set, get) => ({
  run: null,
  nodeStates: {},
  logs: [],
  connection: "connecting",
  setConnection: (connection) => set({ connection }),
  hydrateResults(nodes) {
    set({
      run: null,
      nodeStates: Object.fromEntries(
        nodes.flatMap((node) =>
          node.data?.result
            ? [
                [
                  node.id,
                  {
                    status: node.data.result.status || "SUCCEEDED",
                    progress: 100,
                    artifactIds: node.data.result.artifactIds || [],
                    completedAt: node.data.result.completedAt,
                  },
                ],
              ]
            : [],
        ),
      ),
      logs: [],
    });
  },
  clearResults() {
    set({ run: null, nodeStates: {}, logs: [] });
  },
  clearNodeResult(nodeId) {
    set((state) => {
      const nodeStates = { ...state.nodeStates };
      delete nodeStates[nodeId];
      return { nodeStates };
    });
  },
  async start(workflow, mode = "all", selectedNodeIds = []) {
    const run = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify({ workflow, mode, selectedNodeIds }),
    });
    set((state) => ({
      run,
      nodeStates: Object.fromEntries(
        Object.entries(run.nodes || {}).map(([id, next]) => [
          id,
          {
            ...next,
            artifactIds: next.artifactIds?.length
              ? next.artifactIds
              : state.nodeStates[id]?.artifactIds || [],
          },
        ]),
      ),
      logs: [],
    }));
    return run;
  },
  async pause() {
    const run = get().run;
    if (run)
      set({
        run: await api(`/api/runs/${run.runId}/pause`, { method: "POST" }),
      });
  },
  async resume() {
    const run = get().run;
    if (run)
      set({
        run: await api(`/api/runs/${run.runId}/resume`, { method: "POST" }),
      });
  },
  async cancel() {
    const run = get().run;
    if (run)
      set({
        run: await api(`/api/runs/${run.runId}/cancel`, { method: "POST" }),
      });
  },
  async clearCache() {
    const run = get().run;
    if (run)
      await api(`/api/runs/${run.runId}/clear-cache`, { method: "POST" });
  },
  handleEvent(event) {
    const current = get().run;
    if (event.runId && current && event.runId !== current.runId) return;
    if (event.type === "node.log")
      set((state) => ({
        logs: [
          ...state.logs.slice(-999),
          {
            id: event.eventId,
            nodeId: event.nodeId,
            message: event.payload.message,
            timestamp: event.timestamp,
          },
        ],
      }));
    if (event.nodeId && event.type.startsWith("node.")) {
      const nodeId = event.nodeId;
      const key = event.type.split(".")[1];
      const status = nodeStatus[key] || key.toUpperCase();
      const incomingArtifacts =
        event.payload.artifactIds ||
        (event.payload.artifactId ? [event.payload.artifactId] : null);
      set((state) => {
        const previous = state.nodeStates[nodeId] || {};
        const progress =
          event.payload.progress ??
          (["SUCCEEDED", "CACHED", "FAILED", "CANCELLED"].includes(status)
            ? status === "FAILED" || status === "CANCELLED"
              ? previous.progress || 0
              : 100
            : previous.progress || 0);
        const nodeStates = {
          ...state.nodeStates,
          [nodeId]: {
            ...previous,
            status,
            progress,
            message: event.payload?.message || previous.message,
            artifactIds: incomingArtifacts || previous.artifactIds || [],
            completedAt: ["SUCCEEDED", "CACHED"].includes(status)
              ? event.timestamp || new Date().toISOString()
              : previous.completedAt,
          },
        };
        const values = Object.values(nodeStates);
        const overall = values.length
          ? Math.round(
              values.reduce((sum, item) => sum + (item.progress || 0), 0) /
                values.length,
            )
          : 0;
        window.midgardDesktop?.setRunProgress(overall / 100);
        return {
          nodeStates,
          run: state.run ? { ...state.run, progress: overall } : state.run,
        };
      });
      if (["SUCCEEDED", "CACHED"].includes(status)) {
        const result = get().nodeStates[nodeId];
        useEditorStore
          .getState()
          .recordNodeResult(nodeId, {
            status,
            artifactIds: result?.artifactIds || [],
            completedAt:
              result?.completedAt ||
              event.timestamp ||
              new Date().toISOString(),
          });
      }
    }
    if (event.type.startsWith("run.")) {
      const key = event.type.split(".")[1];
      /** @type {Record<string, string>} */
      const runStatuses = {
        started: "RUNNING",
        pause_requested: "PAUSE_REQUESTED",
        resumed: "RUNNING",
      };
      const status = runStatuses[key] || key.toUpperCase();
      set((state) => {
        const error = status === "FAILED" ? event.payload : state.run?.error;
        const message = error?.message || event.payload?.message;
        const logs =
          message && (status === "FAILED" || status === "CANCELLED")
            ? [
                ...state.logs.slice(-999),
                {
                  id: event.eventId || `${event.type}-${Date.now()}`,
                  nodeId: event.nodeId,
                  message: `${error?.code || status}: ${message}`,
                  timestamp: event.timestamp || new Date().toISOString(),
                },
              ]
            : state.logs;
        return {
          logs,
          run: state.run
            ? {
                ...state.run,
                status,
                progress: status === "COMPLETED" ? 100 : state.run.progress,
                artifactIds: event.payload.artifactIds || state.run.artifactIds,
                error: status === "FAILED" ? event.payload : state.run.error,
              }
            : state.run,
        };
      });
      if (terminal.has(status)) window.midgardDesktop?.setRunProgress(-1);
    }
  },
});
export const useRunStore = create(createRunState);
