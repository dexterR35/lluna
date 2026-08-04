import { useCallback, useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { api, connectEvents } from "./api/client";
import {
  Button,
  Dialog,
  EmptyState,
  ErrorBoundary,
  IconTile,
  LoadingState,
  SearchInput,
  ToastProvider,
  useToast,
} from "./components";
import { BottomDrawer } from "./diagnostics/BottomDrawer";
import { WorkflowCanvas } from "./editor/WorkflowCanvas";
import { ModelsDialog } from "./models/ModelsDialog";
import { SettingsDialog } from "./settings/SettingsDialog";
import { useDesktopStore } from "./state/desktopStore";
import { useEditorStore } from "./state/editorStore";
import { useRunStore } from "./state/runStore";
import { useServerStore } from "./state/serverStore";
import { StatusBar } from "./app/StatusBar";
import { EditorToolbar } from "./workflow/EditorToolbar";
import { NodeLibrary } from "./workflow/NodeLibrary";
import { isVisibleCatalogNode } from "./workflow/catalogVisibility";
import { NodeEditorDialog } from "./nodes/NodeEditorDialog";
import { NodePreviewDialog } from "./nodes/NodePreviewDialog";
function EditorApp() {
  const recoveryChecked = useRef(false);
  const executeRef = useRef(
    /** @type {((command: string) => void) | null} */ (null),
  );
  const failedRunToastRef = useRef(/** @type {string | null} */ (null));
  const toast = useToast();
  const server = useServerStore();
  const layout = useDesktopStore();
  const editor = useEditorStore();
  const runStore = useRunStore();
  const [issues, setIssues] = useState(
    /** @type {import("./types").ValidationIssue[]} */ ([]),
  );
  const [search, setSearch] = useState(
    /** @type {{open: boolean, query: string, position: {x: number, y: number} | null}} */ ({
      open: false,
      query: "",
      position: null,
    }),
  );
  const [editingNodeId, setEditingNodeId] = useState(
    /** @type {string | null} */ (null),
  );
  const [previewNodeId, setPreviewNodeId] = useState(
    /** @type {string | null} */ (null),
  );
  const [zoom, setZoom] = useState(0.78);
  useEffect(() => {
    void useServerStore.getState().bootstrap();
    let disposed = false;
    /** @type {(() => void) | undefined} */
    let stop;
    connectEvents(
      (event) => {
        useServerStore.getState().handleEvent(event);
        useRunStore.getState().handleEvent(event);
      },
      (value) => useRunStore.getState().setConnection(value),
    ).then((value) => {
      if (disposed) value();
      else stop = value;
    });
    return () => {
      disposed = true;
      stop?.();
    };
  }, []);
  useEffect(() => {
    if (server.nodes.length)
      useEditorStore.getState().setDefinitions(server.nodes);
  }, [server.nodes]);
  useEffect(() => {
    if (!server.nodes.length || recoveryChecked.current) return;
    recoveryChecked.current = true;
    window.midgardDesktop?.recoverWorkflow().then((document) => {
      if (document && confirm("Recover the last autosaved workflow?")) {
        useEditorStore.getState().loadWorkflow(document);
        useRunStore.getState().hydrateResults(useEditorStore.getState().nodes);
      } else if (document) void window.midgardDesktop?.clearRecovery();
    });
  }, [server.nodes]);
  useEffect(() => {
    const timer = setInterval(() => {
      const state = useEditorStore.getState();
      if (state.dirty)
        void window.midgardDesktop?.autosaveWorkflow(state.serialize());
    }, 30000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const run = runStore.run;
    if (run?.status !== "FAILED" || !run.error?.message) return;
    if (failedRunToastRef.current === run.runId) return;
    failedRunToastRef.current = run.runId;
    const desktop = useDesktopStore.getState();
    desktop.setValue("drawerVisible", true);
    desktop.setValue("drawerTab", "logs");
    toast.push(run.error.message, "error");
  }, [runStore.run, toast]);
  const validate = useCallback(
    async ({ silent = false } = {}) => {
      try {
        const result = await api("/api/workflows/validate", {
          method: "POST",
          body: JSON.stringify(useEditorStore.getState().serialize()),
        });
        setIssues(result.issues || []);
        const desktop = useDesktopStore.getState();
        if (!silent) desktop.setValue("drawerTab", "problems");
        if (result.valid) {
          if (!silent) toast.push("Workflow is valid");
        } else if (!silent) {
          desktop.setValue("drawerVisible", true);
          desktop.setValue("drawerTab", "problems");
          toast.push(`${result.issues.length} workflow problem(s)`, "error");
        }
        return result.valid;
      } catch (error) {
        toast.push(
          error instanceof Error ? error.message : String(error),
          "error",
        );
        return false;
      }
    },
    [toast],
  );
  /** @param {string} [mode] @param {string[]} [selectedNodeIds] */
  const startRun = useCallback(
    async (mode = "all", /** @type {string[]} */ selectedNodeIds = []) => {
      const workflow = useEditorStore.getState().serialize();
      void validate({ silent: true });
      try {
        const run = await runStore.start(
          workflow,
          mode,
          selectedNodeIds,
        );
        window.midgardDesktop?.setRunProgress((run.progress || 0) / 100);
        const desktop = useDesktopStore.getState();
        desktop.setValue("drawerVisible", true);
        desktop.setValue("drawerTab", "logs");
        toast.push(
          mode === "from"
            ? "Running from selected node"
            : mode === "selected"
              ? "Running selected node"
              : "Workflow run started",
        );
      } catch (error) {
        toast.push(
          error instanceof Error ? error.message : String(error),
          "error",
        );
      }
    },
    [validate, runStore, toast],
  );
  /** @param {string | string[] | undefined} nodeId */
  const runFromHere = useCallback(
    (/** @type {string | string[] | undefined} */ nodeId) => {
      const ids = Array.isArray(nodeId)
        ? nodeId
        : nodeId
          ? [nodeId]
          : useEditorStore
              .getState()
              .nodes.filter((node) => node.selected)
              .map((node) => node.id);
      if (!ids.length) {
        toast.push("Select a node first", "error");
        return;
      }
      void startRun("from", ids);
    },
    [startRun, toast],
  );
  const openNodeOptions = useCallback(
    (/** @type {string} */ id) => setEditingNodeId(id),
    [],
  );
  const openNodePreview = useCallback(
    (/** @type {string} */ id) => setPreviewNodeId(id),
    [],
  );
  const updateZoom = useCallback(
    (/** @type {import("@xyflow/react").Viewport} */ viewport) =>
      setZoom(viewport.zoom),
    [],
  );
  const actions = {
    newWorkflow: async () => {
      if (editor.dirty && !confirm("Discard unsaved workflow changes?")) return;
      const doc = await window.midgardDesktop?.newWorkflow();
      editor.newWorkflow(doc);
      useRunStore.getState().clearResults();
      setIssues([]);
    },
    openWorkflow: async () => {
      const result = await window.midgardDesktop?.openWorkflow();
      if (result) {
        editor.loadWorkflow(result.document);
        useRunStore.getState().hydrateResults(useEditorStore.getState().nodes);
      }
    },
    saveWorkflow: async () => {
      const result = await window.midgardDesktop?.saveWorkflow(
        editor.serialize(),
      );
      if (result) {
        editor.markSaved();
        toast.push(`Saved ${result.name}`);
      }
    },
    validate,
    run: () => void startRun("all"),
    runSelected: () => {
      const ids = useEditorStore
        .getState()
        .nodes.filter((node) => node.selected)
        .map((node) => node.id);
      if (!ids.length) {
        toast.push("Select a node first", "error");
        return;
      }
      void startRun("selected", ids);
    },
    runFromHere,
    createFlow: () => {
      const id = useEditorStore.getState().createFlowFromSelected();
      toast.push(
        id
          ? "Created a flow box from the selection to its final outputs"
          : "Select a start node first",
        id ? "success" : "error",
      );
    },
  };
  executeRef.current = (command) => {
    const e = useEditorStore.getState(),
      d = useDesktopStore.getState();
    /** @type {Record<string, () => unknown>} */
    const handlers = {
      "workflow:new": actions.newWorkflow,
      "workflow:open": actions.openWorkflow,
      "workflow:save": actions.saveWorkflow,
      "workflow:save-as": async () => {
        const result = await window.midgardDesktop?.saveWorkflowAs(
          e.serialize(),
        );
        if (result) e.markSaved();
      },
      "edit:undo": e.undo,
      "edit:redo": e.redo,
      "edit:copy": e.copySelected,
      "edit:paste": e.paste,
      "edit:duplicate": e.duplicateSelected,
      "edit:delete": e.deleteSelected,
      "edit:select-all": e.selectAll,
      "edit:deselect": e.deselect,
      "node:group": e.groupSelected,
      "node:auto-layout": e.autoLayout,
      "node:search": () => setSearch({ open: true, query: "", position: null }),
      "view:fit": () => window.dispatchEvent(new Event("midgard:fit")),
      "view:library": () => d.toggle("libraryVisible"),
      "view:minimap": () => d.toggle("minimapVisible"),
      "view:logs": () => d.toggle("drawerVisible"),
      "view:downloads": () => {
        d.setValue("drawerVisible", true);
        d.setValue("drawerTab", "downloads");
      },
      "view:diagnostics": () => {
        d.setValue("drawerVisible", true);
        d.setValue("drawerTab", "diagnostics");
      },
      "view:settings": () => d.setValue("settingsOpen", true),
      "view:models": () => d.setValue("modelsOpen", true),
      "view:reset-layout": d.reset,
      "run:validate": validate,
      "run:start": actions.run,
      "run:selected": actions.runSelected,
      "run:from-selected": () => runFromHere(undefined),
      "run:pause": runStore.pause,
      "run:resume": runStore.resume,
      "run:stop": runStore.cancel,
      "run:clear-cache": runStore.clearCache,
      "models:refresh": server.refreshModels,
      "models:release": () =>
        api("/api/system/release-models", { method: "POST" }),
    };
    handlers[command]?.();
  };
  useEffect(
    () =>
      window.midgardDesktop?.onMenuCommand((command) =>
        executeRef.current?.(command),
      ),
    [],
  );
  useEffect(() => {
    function key(/** @type {KeyboardEvent} */ event) {
      if (
        ["INPUT", "TEXTAREA", "SELECT"].includes(
          document.activeElement?.tagName || "",
        )
      )
        return;
      if (event.key === "Tab") {
        event.preventDefault();
        setSearch({ open: true, query: "", position: null });
      }
      if (event.key.toLowerCase() === "f")
        window.dispatchEvent(new Event("midgard:fit"));
    }
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  if (server.loading && !server.nodes.length)
    return <LoadingState label="Connecting to Midgard control plane…" />;
  if (server.error)
    return (
      <EmptyState
        title="Backend connection failed"
        description={server.error}
        action={<Button onClick={() => void server.bootstrap()}>Retry</Button>}
      />
    );
  const filtered = server.nodes
    .filter(isVisibleCatalogNode)
    .filter((node) =>
      `${node.name} ${node.category}`
        .toLowerCase()
        .includes(search.query.toLowerCase()),
    )
    .slice(0, 30);
  return (
    <div className="grid h-full grid-rows-[2.75rem_minmax(0,1fr)_1.5rem] bg-mg-app">
      <EditorToolbar actions={actions} />
      <main
        className="grid min-h-0"
        style={{
          gridTemplateColumns: `${layout.libraryVisible ? `${layout.libraryWidth}px` : "0px"} minmax(0,1fr)`,
          gridTemplateRows: `minmax(0,1fr) ${layout.drawerVisible ? `${layout.drawerHeight}px` : "0px"}`,
        }}
      >
        {layout.libraryVisible && (
          <NodeLibrary onAdd={(schemaId) => editor.addNode(schemaId)} />
        )}
        <WorkflowCanvas
          onAdd={(position) => setSearch({ open: true, query: "", position })}
          onRunFlow={runFromHere}
          onRunNode={runFromHere}
          onOpenNode={openNodeOptions}
          onPreviewNode={openNodePreview}
          onViewportChange={updateZoom}
        />
        {layout.drawerVisible && (
          <div className="col-span-2 min-h-0">
            <BottomDrawer issues={issues} />
          </div>
        )}
      </main>
      <StatusBar zoom={zoom} />
      <Dialog
        open={search.open}
        onClose={() => setSearch((value) => ({ ...value, open: false }))}
        title="Add a node"
        description="Search the backend-owned node catalog."
      >
        <SearchInput
          autoFocus
          value={search.query}
          onChange={(query) => setSearch((value) => ({ ...value, query }))}
        />
        <div className="mt-3 grid max-h-80 gap-1 overflow-auto">
          {filtered.map((node) => (
            <button
              key={node.schemaId}
              type="button"
              onClick={() => {
                editor.addNode(node.schemaId, search.position || undefined);
                setSearch((value) => ({ ...value, open: false }));
              }}
              className="ui-row"
            >
              <IconTile>
                <Search className="size-3.5" />
              </IconTile>
              <span>
                <strong className="block text-[12px] font-medium tracking-tight">
                  {node.name}
                </strong>
                <span className="text-[10px] text-mg-muted">
                  {node.category}
                </span>
              </span>
            </button>
          ))}
        </div>
      </Dialog>
      <NodeEditorDialog
        nodeId={editingNodeId}
        onClose={() => setEditingNodeId(null)}
        onManageModels={() => {
          setEditingNodeId(null);
          layout.setValue("modelsOpen", true);
        }}
      />
      <NodePreviewDialog
        nodeId={previewNodeId}
        onClose={() => setPreviewNodeId(null)}
      />
      <SettingsDialog />
      <ModelsDialog />
    </div>
  );
}
export default function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <EditorApp />
      </ToastProvider>
    </ErrorBoundary>
  );
}
