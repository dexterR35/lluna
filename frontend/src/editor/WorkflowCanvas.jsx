import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useKeyPress,
  useReactFlow,
  ViewportPortal,
} from "@xyflow/react";
import { Check, Layers3, Play, X, resolveFlowColor } from "../icons";
import "@xyflow/react/dist/style.css";
import { Badge, ContextMenu } from "../components";
import { useDesktopStore } from "../state/desktopStore";
import {
  boundsForNodes,
  downstreamNodeIds,
  findFlowContainingPoint,
  useEditorStore,
} from "../state/editorStore";
import { useRunStore } from "../state/runStore";
import { useServerStore } from "../state/serverStore";
import { useToast } from "../components/ToastContext";
import { LlunaEdge } from "./LlunaEdge";
import { LlunaNode } from "../nodes/LlunaNode";
import { NodeActionsProvider } from "../nodes/NodeActionsContext";
/** @typedef {import("../types").EditorNode} EditorNode */
/** @typedef {{onAdd: (position: {x: number, y: number}) => void, onRunFlow?: (ids: string[]) => void, onRunNode?: (id: string) => void, onOpenNode?: (id: string) => void, onPreviewNode?: (id: string) => void, onViewportChange?: (viewport: import("@xyflow/react").Viewport) => void}} CanvasProps */
/** @type {import("@xyflow/react").NodeTypes} */
const nodeTypes = { lluna: LlunaNode };
/** @type {import("@xyflow/react").EdgeTypes} */
const edgeTypes = { lluna: LlunaEdge };
const DEFAULT_VIEWPORT = { x: 0, y: 0, zoom: 0.78 };
const FIT_VIEW_OPTIONS = {
  padding: 0.3,
  minZoom: 0.2,
  maxZoom: 0.85,
  duration: 280,
};
const FOCUS_VIEW_OPTIONS = {
  padding: 0.5,
  minZoom: 0.2,
  maxZoom: 0.95,
  duration: 240,
};

/** @param {{group: import("../types").WorkflowGroup, nodes: EditorNode[], selected: boolean, onSelect: () => void, onRun: (ids: string[]) => void}} props */
function FlowBox({ group, nodes, selected, onSelect, onRun }) {
  const flow = useReactFlow();
  const dragRef = useRef(
    /** @type {{x: number, y: number} | null} */ (null),
  );
  const nodeStates = useRunStore((store) => store.nodeStates);
  const bounds = boundsForNodes(nodes, group.nodeIds);
  const members = group.nodeIds.flatMap((id) => {
    const node = nodes.find((candidate) => candidate.id === id);
    return node ? [node] : [];
  });
  const states = members
    .map((node) => {
      if (node.data.disabled) return { status: "DISABLED", artifactIds: [] };
      const live = nodeStates[node.id];
      return live?.status && live.status !== "IDLE"
        ? live
        : node.data.result || live;
    })
    .filter(Boolean);
  const failed = states.some((state) => state.status === "FAILED");
  const running = states.some((state) =>
    ["RUNNING", "QUEUED", "PAUSED", "PAUSE_REQUESTED"].includes(
      state.status || "",
    ),
  );
  const completed =
    states.length === members.length &&
    states.length > 0 &&
    states.every((state) =>
      ["SUCCEEDED", "CACHED", "DISABLED"].includes(state.status || ""),
    );
  const outputs = new Set(states.flatMap((state) => state.artifactIds || []))
    .size;
  const StatusIcon = failed ? X : completed ? Check : Layers3;
  const color = resolveFlowColor(group.color);
  const endFlowDrag = useCallback(
    (/** @type {import("react").PointerEvent<HTMLElement>} */ event) => {
      if (!dragRef.current) return;
      dragRef.current = null;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    },
    [],
  );
  return (
    <section
      aria-label={`${group.label} flow box`}
      className={`pointer-events-none absolute rounded-2xl border transition ${selected ? "" : "border-dashed"}`}
      style={{
        transform: `translate(${bounds.position.x}px,${bounds.position.y}px)`,
        width: bounds.width,
        height: bounds.height,
        borderColor: selected
          ? color
          : `color-mix(in srgb, ${color} 30%, transparent)`,
        background: `color-mix(in srgb, ${color} 2.5%, transparent)`,
      }}
    >
      <header
        className="pointer-events-auto absolute inset-x-0 top-0 flex h-10 cursor-grab items-center gap-2 border-b border-mg-border/60 px-2.5 touch-none select-none active:cursor-grabbing"
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          if (
            event.target instanceof Element &&
            event.target.closest("button")
          ) {
            return;
          }
          event.stopPropagation();
          event.preventDefault();
          onSelect();
          useEditorStore.getState().checkpoint();
          dragRef.current = { x: event.clientX, y: event.clientY };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          const drag = dragRef.current;
          if (!drag) return;
          const zoom = flow.getZoom() || 1;
          const dx = (event.clientX - drag.x) / zoom;
          const dy = (event.clientY - drag.y) / zoom;
          if (!dx && !dy) return;
          drag.x = event.clientX;
          drag.y = event.clientY;
          useEditorStore.getState().moveFlowBy(group.id, { x: dx, y: dy });
        }}
        onPointerUp={endFlowDrag}
        onPointerCancel={endFlowDrag}
      >
        <span
          className="grid size-6 place-items-center rounded-full"
          style={{
            color,
            background: `color-mix(in srgb, ${color} 14%, transparent)`,
          }}
        >
          <StatusIcon className={`ui-icon-sm ${running ? "animate-pulse" : ""}`} />
        </span>
        <span className="min-w-0 flex-1">
          <strong className="ui-copy-title block truncate text-[11px]">
            {group.label}
          </strong>
          <span className="ui-copy-muted block">
            {group.nodeIds.length} nodes{outputs ? ` · ${outputs} results` : ""}
          </span>
        </span>
        {completed && (
          <Badge tone="success" size="xs">
            Complete
          </Badge>
        )}
        <button
          type="button"
          className="nodrag grid size-7 place-items-center rounded-full text-white transition hover:brightness-110"
          style={{ background: color }}
          aria-label={`Run ${group.label} from start to end`}
          onClick={(event) => {
            event.stopPropagation();
            onRun(
              group.startNodeIds?.length
                ? group.startNodeIds
                : [group.nodeIds[0]],
            );
          }}
        >
          <Play className="ui-icon-sm fill-current" />
        </button>
      </header>
    </section>
  );
}

/** @param {CanvasProps} props */
function CanvasBody({
  onAdd,
  onRunFlow,
  onRunNode,
  onOpenNode,
  onPreviewNode,
  onViewportChange,
}) {
  const wrapper = useRef(/** @type {HTMLDivElement | null} */ (null));
  const flow = useReactFlow();
  const toast = useToast();
  const nodes = useEditorStore((store) => store.nodes);
  const models = useServerStore((store) => store.models);
  const edges = useEditorStore((store) => store.edges);
  const groups = useEditorStore((store) => store.groups);
  const selectedGroupId = useEditorStore((store) => store.selectedGroupId);
  const selectGroup = useEditorStore((store) => store.selectGroup);
  const onNodesChange = useEditorStore((store) => store.onNodesChange);
  const onEdgesChange = useEditorStore((store) => store.onEdgesChange);
  const connect = useEditorStore((store) => store.connect);
  const addNode = useEditorStore((store) => store.addNode);
  const setNodeModel = useEditorStore((store) => store.setNodeModel);
  const updateNode = useEditorStore((store) => store.updateNode);
  const setViewport = useEditorStore((store) => store.setViewport);
  const minimap = useDesktopStore((store) => store.minimapVisible);
  const [menu, setMenu] = useState(
    /** @type {{x: number, y: number, position: {x: number, y: number}} | null} */ (
      null
    ),
  );
  const spacePressed = useKeyPress("Space", { preventDefault: true });
  useEffect(() => {
    const fit = () => void flow.fitView(FIT_VIEW_OPTIONS);
    const focus = (/** @type {Event} */ event) => {
      const id = event instanceof CustomEvent ? event.detail?.id : null;
      if (typeof id !== "string") return;
      void flow.fitView({ ...FOCUS_VIEW_OPTIONS, nodes: [{ id }] });
    };
    window.addEventListener("lluna:fit", fit);
    window.addEventListener("lluna:focus-node", focus);
    return () => {
      window.removeEventListener("lluna:fit", fit);
      window.removeEventListener("lluna:focus-node", focus);
    };
  }, [flow]);
  const changeModel = useCallback(
    (/** @type {string} */ nodeId, /** @type {string | number} */ value) => {
      setNodeModel(nodeId, value);
      useRunStore
        .getState()
        .clearNodeResults(
          downstreamNodeIds([nodeId], useEditorStore.getState().edges),
        );
    },
    [setNodeModel],
  );
  const changeParameter = useCallback(
    (
      /** @type {string} */ nodeId,
      /** @type {string} */ key,
      /** @type {unknown} */ value,
    ) => {
      const current = useEditorStore
        .getState()
        .nodes.find((node) => node.id === nodeId);
      if (!current) return;
      updateNode(nodeId, {
        parameters: { ...current.data.parameters, [key]: value },
      });
      useRunStore
        .getState()
        .clearNodeResults(
          downstreamNodeIds([nodeId], useEditorStore.getState().edges),
        );
    },
    [updateNode],
  );
  // Node action callbacks and the model inventory are provided via context
  // (see NodeActionsProvider below) rather than merged into each node's
  // `data`, so editing one node doesn't force xyflow to see a new `data`
  // object - and therefore re-render - every other node on the canvas.
  const nodeActions = useMemo(
    () => ({
      onOpen: onOpenNode,
      onRun: onRunNode,
      onPreview: onPreviewNode,
      onModelChange: changeModel,
      onParameterChange: changeParameter,
    }),
    [changeModel, changeParameter, onOpenNode, onPreviewNode, onRunNode],
  );
  const nodeActionsValue = useMemo(
    () => ({ actions: nodeActions, modelInventory: models }),
    [nodeActions, models],
  );
  const drop = useCallback(
    async (/** @type {import("react").DragEvent<HTMLDivElement>} */ event) => {
      event.preventDefault();
      const position = flow.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      const editor = useEditorStore.getState();
      const targetFlow = findFlowContainingPoint(
        editor.groups,
        editor.nodes,
        position,
        editor.selectedGroupId,
      );
      const flowOptions = targetFlow ? { flowId: targetFlow.id } : undefined;
      const schemaId = event.dataTransfer.getData("application/x-lluna-node");
      if (schemaId) {
        addNode(schemaId, position, flowOptions);
        return;
      }
      const files = [...event.dataTransfer.files];
      if (files.length && window.llunaDesktop?.registerDroppedFiles) {
        try {
          const grants =
            await window.llunaDesktop.registerDroppedFiles(files);
          const videoGrants = grants.filter(
            (grant) =>
              grant.mediaType?.startsWith("video/") ||
              /\.(mp4|mov|mkv|webm|avi)$/i.test(grant.name),
          );
          const imageGrants = grants.filter(
            (grant) => !videoGrants.includes(grant),
          );
          let offset = 0;
          if (imageGrants.length) {
            const batch = imageGrants.length > 1;
            const id = addNode(
              batch ? "lluna.input.images" : "lluna.input.image",
              { x: position.x, y: position.y },
              flowOptions,
            );
            if (id) {
              useRunStore.getState().clearNodeResult(id);
              useEditorStore
                .getState()
                .updateNode(id, {
                  parameters: batch
                    ? {
                        pathGrantIds: imageGrants.map((grant) => grant.grantId),
                      }
                    : { pathGrantId: imageGrants[0].grantId },
                  result: {
                    status: "READY",
                    artifactIds: imageGrants.flatMap((grant) =>
                      grant.artifactId ? [grant.artifactId] : [],
                    ),
                    sourceName: batch
                      ? `${imageGrants.length} images`
                      : imageGrants[0].name,
                    completedAt: new Date().toISOString(),
                  },
                });
            }
            offset += 1;
          }
          videoGrants.forEach((grant, index) => {
            const id = addNode(
              "lluna.input.video",
              {
                x: position.x + (offset + index) * 28,
                y: position.y + (offset + index) * 28,
              },
              flowOptions,
            );
            if (!id) return;
            useRunStore.getState().clearNodeResult(id);
            useEditorStore.getState().updateNode(id, {
              parameters: { pathGrantId: grant.grantId },
              result: {
                status: "READY",
                artifactIds: grant.artifactId ? [grant.artifactId] : [],
                sourceName: grant.name,
                completedAt: new Date().toISOString(),
              },
            });
          });
        } catch (error) {
          toast.push(
            error instanceof Error
              ? error.message
              : "Could not load the dropped file",
            "error",
          );
        }
      }
    },
    [addNode, flow, toast],
  );
  return (
    <NodeActionsProvider value={nodeActionsValue}>
      <div
        ref={wrapper}
        className="relative h-full w-full"
        onContextMenu={(event) => {
          event.preventDefault();
          setMenu({
            x: event.clientX,
            y: event.clientY,
            position: flow.screenToFlowPosition({
              x: event.clientX,
              y: event.clientY,
            }),
          });
        }}
      >
        <ReactFlow
          className={spacePressed ? "artboard-panning" : ""}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onPaneClick={() => useEditorStore.getState().deselect()}
          onConnect={(connection) => {
            const result = connect(connection);
            if (!result.valid) toast.push(result.reason, "error");
          }}
          isValidConnection={(connection) =>
            useEditorStore.getState().canConnect(connection).valid
          }
          onDrop={drop}
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
          }}
          onNodeDragStart={() => useEditorStore.getState().checkpoint()}
          onNodeDragStop={(_, node) => {
            const editor = useEditorStore.getState();
            const alreadyInFlow = editor.groups.some(
              (group) =>
                group.kind === "flow" && group.nodeIds.includes(node.id),
            );
            if (alreadyInFlow) return;
            const center = {
              x:
                node.position.x +
                (node.measured?.width || node.width || 256) / 2,
              y:
                node.position.y +
                (node.measured?.height || node.height || 190) / 2,
            };
            const targetFlow = findFlowContainingPoint(
              editor.groups,
              editor.nodes,
              center,
              editor.selectedGroupId,
            );
            if (targetFlow) editor.addNodesToFlow(targetFlow.id, [node.id]);
          }}
          onMove={(_, viewport) => onViewportChange?.(viewport)}
          onMoveEnd={(_, viewport) => {
            setViewport(viewport);
            onViewportChange?.(viewport);
          }}
          defaultViewport={DEFAULT_VIEWPORT}
          fitView
          fitViewOptions={FIT_VIEW_OPTIONS}
          zoomOnDoubleClick={false}
          zoomOnScroll={false}
          zoomActivationKeyCode={["Control", "Meta"]}
          panOnScroll={false}
          panOnDrag={spacePressed}
          panActivationKeyCode={null}
          nodesDraggable={!spacePressed}
          elementsSelectable={!spacePressed}
          snapToGrid
          snapGrid={[16, 16]}
          selectionOnDrag={!spacePressed}
          deleteKeyCode={["Backspace", "Delete"]}
          multiSelectionKeyCode="Shift"
          minZoom={0.2}
          maxZoom={2}
          connectionRadius={26}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={24}
            size={1}
            color="#2a2f3a"
            bgColor="#0a0b0f"
          />
          <Controls showInteractive={false} />
          {minimap && (
            <MiniMap
              pannable
              zoomable
              nodeColor="#343844"
              maskColor="rgba(9,10,13,.76)"
            />
          )}
          <ViewportPortal>
            {groups.map((group) => (
              <FlowBox
                key={group.id}
                group={group}
                nodes={nodes}
                selected={selectedGroupId === group.id}
                onSelect={() => selectGroup(group.id)}
                onRun={(ids) => onRunFlow?.(ids)}
              />
            ))}
          </ViewportPortal>
        </ReactFlow>
        <ContextMenu
          open={Boolean(menu)}
          x={menu?.x || 0}
          y={menu?.y || 0}
          onClose={() => setMenu(null)}
          onSelect={(id) => {
            if (id === "add" && menu) onAdd(menu.position);
            if (id === "flow") {
              const created = useEditorStore.getState().createFlowFromSelected();
              if (!created) toast.push("Select a start node first", "error");
            }
            if (id === "fit") flow.fitView(FIT_VIEW_OPTIONS);
            if (id === "select") useEditorStore.getState().selectAll();
            if (id === "layout") useEditorStore.getState().autoLayout();
          }}
          items={[
            { id: "add", label: "Add node…" },
            { id: "flow", label: "Create flow box to end" },
            { id: "select", label: "Select all", shortcut: "Ctrl+A" },
            { id: "fit", label: "Fit workflow", shortcut: "F" },
            { id: "layout", label: "Auto layout" },
          ]}
        />
      </div>
    </NodeActionsProvider>
  );
}
/** @param {CanvasProps} props */
export function WorkflowCanvas(props) {
  return (
    <ReactFlowProvider>
      <CanvasBody {...props} />
    </ReactFlowProvider>
  );
}
