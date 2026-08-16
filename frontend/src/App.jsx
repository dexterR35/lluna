import { useCallback, useEffect, useRef, useState } from "react";
import { resolveNodeIcon } from "./icons";
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
  const issuesRef = useRef(/** @type {import("./types").ValidationIssue[]} */ ([]));
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
  const [pendingRecovery, setPendingRecovery] = useState(
    /** @type {import("./types").WorkflowDocument | null} */ (null),
  );
  const [discardOpen, setDiscardOpen] = useState(false);
  useEffect(() => {
    void useServerStore.getState().bootstrap();
    void useRunStore.getState().loadActivity();
    let disposed = false;
    /** @type {(() => void) | undefined} */
    let stop;
    connectEvents(
      (event) => {
        useServerStore.getState().handleEvent(event);
        useRunStore.getState().handleEvent(event);
        if (
          event.type === "download.failed" ||
          event.type === "model.action.failed"
        ) {
          const modelId =
            typeof event.payload?.modelId === "string"
              ? event.payload.modelId
              : "Model";
          const message =
            typeof event.payload?.message === "string" && event.payload.message
              ? event.payload.message
              : `${modelId} action failed`;
          const desktop = useDesktopStore.getState();
          desktop.setValue("drawerVisible", true);
          desktop.setValue("drawerTab", "downloads");
          toast.push(message, "error");
        } else if (event.type === "download.cancelled") {
          const modelId =
            typeof event.payload?.modelId === "string"
              ? event.payload.modelId
              : "Model";
          toast.push(`${modelId} install cancelled`, "error");
        } else if (event.type === "download.completed") {
          const modelId =
            typeof event.payload?.modelId === "string"
              ? event.payload.modelId
              : null;
          if (modelId) toast.push(`Installed ${modelId}`);
        }
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
  }, [toast]);
  useEffect(() => {
    if (server.nodes.length)
      useEditorStore.getState().setDefinitions(server.nodes);
  }, [server.nodes]);
  useEffect(() => {
    if (!server.nodes.length || recoveryChecked.current) return;
    recoveryChecked.current = true;
    window.llunaDesktop?.recoverWorkflow().then((document) => {
      if (document) setPendingRecovery(document);
    });
  }, [server.nodes]);
  useEffect(() => {
    const timer = setInterval(() => {
      const state = useEditorStore.getState();
      if (state.dirty)
        void window.llunaDesktop?.autosaveWorkflow(state.serialize());
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
        issuesRef.current = result.issues || [];
        setIssues(issuesRef.current);
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
  /** @param {string} [mode] @param {string[]} [selectedNodeIds] @param {{queueFront?: boolean, force?: boolean}} [options] */
  const startRun = useCallback(
    async (
      mode = "all",
      /** @type {string[]} */ selectedNodeIds = [],
      /** @type {{queueFront?: boolean, force?: boolean}} */ options = {},
    ) => {
      const workflow = useEditorStore.getState().serialize();
      const valid = await validate({ silent: true });
      if (!valid && !options.force) {
        const desktop = useDesktopStore.getState();
        desktop.setValue("drawerVisible", true);
        desktop.setValue("drawerTab", "problems");
        toast.push(
          `${issuesRef.current.length} workflow problem(s) - fix them or run anyway`,
          "error",
        );
        return;
      }
      try {
        const run = await runStore.start(
          workflow,
          mode,
          selectedNodeIds,
          options,
        );
        // `null` means a run was already starting and this call was a no-op
        // (see runStore.start's re-entrant guard) - nothing new to report.
        if (!run) return;
        window.llunaDesktop?.setRunProgress((run.progress || 0) / 100);
        const desktop = useDesktopStore.getState();
        desktop.setValue("drawerVisible", true);
        desktop.setValue("drawerTab", run.status === "QUEUED" ? "queue" : "logs");
        toast.push(
          options.queueFront
            ? "Workflow queued to run next"
            : mode === "from"
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
  const resetWorkflow = useCallback(async () => {
    const doc = await window.llunaDesktop?.newWorkflow();
    useEditorStore.getState().newWorkflow(doc);
    useRunStore.getState().clearResults();
    setIssues([]);
  }, []);
  const actions = {
    newWorkflow: async () => {
      if (useEditorStore.getState().dirty) {
        setDiscardOpen(true);
        return;
      }
      await resetWorkflow();
    },
    openWorkflow: async () => {
      const result = await window.llunaDesktop?.openWorkflow();
      if (result) {
        editor.loadWorkflow(result.document);
        useRunStore.getState().hydrateResults(useEditorStore.getState().nodes);
      }
    },
    saveWorkflow: async () => {
      const result = await window.llunaDesktop?.saveWorkflow(
        editor.serialize(),
      );
      if (result) {
        editor.markSaved();
        toast.push(`Saved ${result.name}`);
      }
    },
    validate,
    run: () => void startRun("all"),
    runNext: () => void startRun("all", [], { queueFront: true }),
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
      const before = useEditorStore.getState().groups.length;
      const id = useEditorStore.getState().createFlowFromSelected();
      const after = useEditorStore.getState().groups.length;
      toast.push(
        id
          ? after > before
            ? "Created a flow box from the selection to its final outputs"
            : "Added the selection to the existing flow"
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
        const result = await window.llunaDesktop?.saveWorkflowAs(
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
      "view:fit": () => window.dispatchEvent(new Event("lluna:fit")),
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
      "view:settings": () => {
        d.setValue("settingsSection", "editor");
        d.setValue("settingsOpen", true);
      },
      "view:models": () => {
        d.setValue("settingsSection", "models");
        d.setValue("settingsOpen", true);
      },
      "view:reset-layout": d.reset,
      "run:validate": validate,
      "run:start": actions.run,
      "run:next": actions.runNext,
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
      window.llunaDesktop?.onMenuCommand((command) =>
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
        window.dispatchEvent(new Event("lluna:fit"));
      if (event.ctrlKey && event.altKey && event.key === "Enter") {
        event.preventDefault();
        executeRef.current?.("run:stop");
      } else if (event.ctrlKey && event.key === "Enter") {
        event.preventDefault();
        executeRef.current?.(event.shiftKey ? "run:next" : "run:start");
      }
    }
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  if (server.loading && !server.nodes.length)
    return <LoadingState label="Connecting to Lluna control plane…" />;
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
          gridTemplateColumns: `${layout.libraryVisible ? `${layout.libraryCollapsed ? 52 : layout.libraryWidth}px` : "0px"} minmax(0,1fr)`,
          gridTemplateRows: `minmax(0,1fr) ${layout.drawerVisible ? `${layout.drawerHeight}px` : "0px"}`,
        }}
      >
        {layout.libraryVisible && (
          <NodeLibrary />
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
              <IconTile size="sm">
                {(() => {
                  const NodeIcon = resolveNodeIcon(node.icon);
                  return <NodeIcon className="ui-icon" />;
                })()}
              </IconTile>
              <span>
                <strong className="ui-copy-title block text-[12px]">
                  {node.name}
                </strong>
                <span className="ui-copy-muted">{node.category}</span>
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
          layout.setValue("settingsSection", "models");
          layout.setValue("settingsOpen", true);
        }}
      />
      <NodePreviewDialog
        nodeId={previewNodeId}
        onClose={() => setPreviewNodeId(null)}
        onRun={runFromHere}
      />
      <SettingsDialog />
      <Dialog
        open={Boolean(pendingRecovery)}
        onClose={() => {
          setPendingRecovery(null);
          void window.llunaDesktop?.clearRecovery();
        }}
        title="Restore previous session?"
        description="A recent autosave is available. Recover it to continue where you left off, or start a new workflow."
        bodyClassName="!hidden"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setPendingRecovery(null);
                void window.llunaDesktop?.clearRecovery();
              }}
            >
              Start fresh
            </Button>
            <Button
              onClick={() => {
                if (!pendingRecovery) return;
                useEditorStore.getState().loadWorkflow(pendingRecovery);
                useRunStore
                  .getState()
                  .hydrateResults(useEditorStore.getState().nodes);
                setPendingRecovery(null);
              }}
            >
              Recover workflow
            </Button>
          </>
        }
      />
      <Dialog
        open={discardOpen}
        onClose={() => setDiscardOpen(false)}
        title="Start a new workflow?"
        description="Your current workflow has unsaved changes. They will be lost if you continue."
        bodyClassName="!hidden"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDiscardOpen(false)}>
              Keep editing
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                setDiscardOpen(false);
                void resetWorkflow();
              }}
            >
              Discard changes
            </Button>
          </>
        }
      />
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
