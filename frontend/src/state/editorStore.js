import { create } from "zustand";
import { addEdge, applyEdgeChanges, applyNodeChanges } from "@xyflow/react";
import { compatibleTypes } from "../icons";
/** @typedef {import("../types").EditorState} EditorState */
/** @typedef {import("../types").EditorNode} EditorNode */
/** @typedef {import("../types").EditorEdge} EditorEdge */
/** @typedef {import("../types").WorkflowGroup} WorkflowGroup */
/** @typedef {import("../types").NodeDefinition} NodeDefinition */
/** @typedef {import("../types").EditorSnapshot} EditorSnapshot */
const MAX_HISTORY = 100;
/** @type {{nodes: EditorNode[], edges: EditorEdge[]}} */
let clipboard = { nodes: [], edges: [] };
/** @param {EditorState} state @returns {EditorSnapshot} */
const snap = (state) => ({
  nodes: structuredClone(state.nodes),
  edges: structuredClone(state.edges),
  groups: structuredClone(state.groups),
});
/** @param {EditorState} state @param {Partial<EditorState>} patch */
const history = (state, patch) => ({
  ...patch,
  past: [...state.past.slice(-(MAX_HISTORY - 1)), snap(state)],
  future: [],
  dirty: true,
});
/** @param {NodeDefinition[]} definitions */
const definitionsById = (definitions) =>
  Object.fromEntries(definitions.map((value) => [value.schemaId, value]));
/** @param {NodeDefinition} definition */
const defaults = (definition) =>
  Object.fromEntries(
    definition.parameters.map((parameter) => [
      parameter.id,
      structuredClone(parameter.default),
    ]),
  );
/** @param {NodeDefinition | undefined} definition @param {Record<string, unknown>} [saved] */
const restoredParameters = (definition, saved = {}) => {
  if (!definition) return saved;
  const values = { ...defaults(definition), ...saved };
  for (const parameter of definition.parameters)
    if (parameter.type === "model" && !values[parameter.id])
      values[parameter.id] = structuredClone(parameter.default);
  return values;
};
export const DEFAULT_APPEARANCE = {
  cardStyle: "visual",
  imageEffect: "none",
  imageFit: "cover",
  imageRatio: "wide",
  showPreview: true,
};
/** @param {NodeDefinition} definition @param {{x: number, y: number}} position @returns {EditorNode} */
function createNode(definition, position) {
  const isSettingsCard = definition.schemaId === "lluna.input.llava";
  return {
    id: crypto.randomUUID(),
    type: "lluna",
    position,
    data: {
      schemaId: definition.schemaId,
      schemaVersion: definition.schemaVersion,
      label: definition.name,
      parameters: defaults(definition),
      appearance: {
        ...DEFAULT_APPEARANCE,
        ...(isSettingsCard
          ? { showPreview: false, cardStyle: "settings" }
          : {}),
      },
      definition,
    },
    selected: false,
  };
}

const UPSCALE_SCHEMA_ID = "lluna.image.upscale";
const LLAVA_SCHEMA_ID = "lluna.input.llava";

/**
 * Keep the SUPIR LLaVA toggle and its visible companion node in sync.
 * @param {EditorState} state
 * @param {EditorNode[]} nodes
 * @param {EditorEdge[]} edges
 * @param {string} upscaleId
 */
function reconcileLlavaCompanion(state, nodes, edges, upscaleId) {
  const upscale = nodes.find((node) => node.id === upscaleId);
  if (!upscale || upscale.data.schemaId !== UPSCALE_SCHEMA_ID)
    return { nodes, edges, groups: state.groups };

  const connectedEdges = edges.filter(
    (edge) => edge.target === upscaleId && edge.targetHandle === "llava",
  );
  const companionIds = new Set(
    connectedEdges.flatMap((edge) => {
      const source = nodes.find((node) => node.id === edge.source);
      return source?.data.schemaId === LLAVA_SCHEMA_ID ? [source.id] : [];
    }),
  );
  const shouldExist =
    upscale.data.parameters?.model === "SUPIR" &&
    Boolean(upscale.data.parameters?.useLlava);

  if (shouldExist && !companionIds.size && !connectedEdges.length) {
    const definition = state.definitions.find(
      (item) => item.schemaId === LLAVA_SCHEMA_ID,
    );
    if (!definition) return { nodes, edges, groups: state.groups };
    const companion = {
      ...createNode(definition, {
        x: upscale.position.x - 320,
        y: upscale.position.y + 32,
      }),
      selected: false,
    };
    const nextNodes = [...nodes, companion];
    const nextEdges = [
      ...edges,
      {
        id: crypto.randomUUID(),
        source: companion.id,
        sourceHandle: "config",
        target: upscaleId,
        targetHandle: "llava",
        type: "lluna",
        data: { portType: "MODEL" },
      },
    ];
    let groups = state.groups;
    const targetGroup = state.groups.find((group) =>
      group.nodeIds.includes(upscaleId),
    );
    if (targetGroup)
      groups = state.groups.map((group) =>
        group.id === targetGroup.id
          ? expandFlowGroup(group, [companion.id], nextNodes, nextEdges)
          : group,
      );
    return { nodes: nextNodes, edges: nextEdges, groups };
  }

  if (!shouldExist && companionIds.size) {
    const nextNodes = nodes.filter((node) => !companionIds.has(node.id));
    const nextEdges = edges.filter(
      (edge) =>
        !companionIds.has(edge.source) && !companionIds.has(edge.target),
    );
    return {
      nodes: nextNodes,
      edges: nextEdges,
      groups: refreshFlowGroups(state.groups, nextNodes, nextEdges),
    };
  }
  return { nodes, edges, groups: state.groups };
}
/** @returns {import("../types").EditorProject} */
function projectTemplate() {
  const now = new Date().toISOString();
  return {
    format: "lluna-workflow",
    version: 1,
    projectId: crypto.randomUUID(),
    name: "Untitled workflow",
    createdAt: now,
    updatedAt: now,
    projectSettings: {},
    viewport: { x: 0, y: 0, zoom: 1 },
    metadata: {},
  };
}
/** @param {import("../types").WorkflowDocument} document @returns {import("../types").EditorProject} */
function projectFromDocument(document) {
  return {
    format: document.format,
    version: document.version,
    projectId: document.projectId,
    name: document.name,
    createdAt: document.createdAt,
    updatedAt: document.updatedAt,
    projectSettings: document.projectSettings,
    viewport: document.viewport,
    metadata: document.metadata,
  };
}

/** @param {string[]} seedIds @param {Array<{source: string, target: string}>} edges */
export function downstreamNodeIds(seedIds, edges) {
  const included = new Set(seedIds);
  const pending = [...seedIds];
  while (pending.length) {
    const source = pending.shift();
    for (const edge of edges) {
      if (edge.source !== source || included.has(edge.target)) continue;
      included.add(edge.target);
      pending.push(edge.target);
    }
  }
  return [...included];
}

/** @param {string} seedId @param {EditorEdge[]} edges @param {"upstream" | "downstream"} direction */
function linkedNodeIds(seedId, edges, direction) {
  const included = new Set([seedId]);
  const pending = [seedId];
  while (pending.length) {
    const current = pending.shift();
    for (const edge of edges) {
      const matches =
        direction === "upstream"
          ? edge.target === current
          : edge.source === current;
      if (!matches) continue;
      const next = direction === "upstream" ? edge.source : edge.target;
      if (!next || included.has(next)) continue;
      included.add(next);
      pending.push(next);
    }
  }
  return included;
}

/** @param {string} nodeId @param {EditorNode[]} nodes @param {EditorEdge[]} edges @param {NodeDefinition[]} definitions */
function hasBatchSource(nodeId, nodes, edges, definitions) {
  const map = definitionsById(definitions);
  const upstream = linkedNodeIds(nodeId, edges, "upstream");
  return [...upstream].some((id) => {
    const node = nodes.find((candidate) => candidate.id === id);
    const definition = node ? map[node.data.schemaId] : undefined;
    if (
      definition?.kind === "input" &&
      definition.outputs.some((port) => Boolean(port.multiple))
    )
      return true;
    return Boolean(
      definition?.inputs.some(
        (port) =>
          port.multiple &&
          edges.filter(
            (edge) => edge.target === id && edge.targetHandle === port.id,
          ).length > 1,
      ),
    );
  });
}

/**
 * Return the repeated processor introduced when two existing paths are joined.
 * Parallel branches remain valid because only ancestors of the source and
 * descendants of the target can share the newly-created directed path.
 * @param {EditorNode[]} nodes
 * @param {EditorEdge[]} edges
 * @param {string} sourceId
 * @param {string} targetId
 * @param {NodeDefinition[]} definitions
 */
export function repeatedProcessorForConnection(
  nodes,
  edges,
  sourceId,
  targetId,
  definitions,
) {
  const nodeMap = Object.fromEntries(nodes.map((node) => [node.id, node]));
  const definitionMap = definitionsById(definitions);
  const upstream = linkedNodeIds(sourceId, edges, "upstream");
  const downstream = linkedNodeIds(targetId, edges, "downstream");
  for (const upstreamId of upstream) {
    const upstreamNode = nodeMap[upstreamId];
    const definition = upstreamNode
      ? definitionMap[upstreamNode.data.schemaId]
      : undefined;
    if (!definition || definition.kind !== "processor") continue;
    for (const downstreamId of downstream) {
      const downstreamNode = nodeMap[downstreamId];
      if (downstreamNode?.data.schemaId === upstreamNode.data.schemaId)
        return definition;
    }
  }
  return null;
}

/** @param {WorkflowGroup[]} groups @param {EditorNode[]} nodes @param {EditorEdge[]} edges */
function refreshFlowGroups(groups, nodes, edges) {
  const known = new Set(nodes.map((node) => node.id));
  return groups.flatMap((group) => {
    if (group.kind !== "flow" || !group.startNodeIds?.length) return [group];
    const startNodeIds = group.startNodeIds.filter((id) => known.has(id));
    if (!startNodeIds.length) return [];
    return [
      {
        ...group,
        startNodeIds,
        nodeIds: downstreamNodeIds(startNodeIds, edges).filter((id) =>
          known.has(id),
        ),
      },
    ];
  });
}

/**
 * When a free node is wired into a flow, absorb it so the box grows.
 * Upstream outsiders become extra start seeds; downstream outsiders are
 * picked up by refreshFlowGroups.
 * @param {WorkflowGroup[]} groups
 * @param {EditorNode[]} nodes
 * @param {EditorEdge[]} edges
 * @param {string} sourceId
 * @param {string} targetId
 */
function absorbConnectedIntoFlows(groups, nodes, edges, sourceId, targetId) {
  /** @param {string} nodeId */
  const memberFlows = (nodeId) =>
    groups.filter(
      (group) => group.kind === "flow" && group.nodeIds?.includes(nodeId),
    );
  const sourceFlows = memberFlows(sourceId);
  const targetFlows = memberFlows(targetId);
  let next = groups;

  // Outside → into a flow member: treat the outsider as a new flow start.
  if (!sourceFlows.length && targetFlows.length) {
    const absorbIds = new Set(targetFlows.map((group) => group.id));
    next = next.map((group) =>
      absorbIds.has(group.id)
        ? expandFlowGroup(group, [sourceId], nodes, edges)
        : group,
    );
  }

  return refreshFlowGroups(next, nodes, edges);
}

/** @param {EditorNode[]} nodes @param {string[]} nodeIds */
export function boundsForNodes(nodes, nodeIds) {
  const members = nodes.filter((node) => nodeIds.includes(node.id));
  if (!members.length)
    return { position: { x: 80, y: 80 }, width: 360, height: 240 };
  const minX = Math.min(...members.map((node) => node.position.x));
  const minY = Math.min(...members.map((node) => node.position.y));
  const maxX = Math.max(
    ...members.map(
      (node) => node.position.x + (node.measured?.width || node.width || 256),
    ),
  );
  const maxY = Math.max(
    ...members.map(
      (node) => node.position.y + (node.measured?.height || node.height || 190),
    ),
  );
  return {
    position: { x: minX - 44, y: minY - 72 },
    width: maxX - minX + 88,
    height: maxY - minY + 116,
  };
}

/**
 * @param {WorkflowGroup[]} groups
 * @param {EditorNode[]} nodes
 * @param {{x: number, y: number}} point
 * @param {string | null} [preferredId]
 */
export function findFlowContainingPoint(
  groups,
  nodes,
  point,
  preferredId = null,
) {
  const hits = groups.flatMap((group) => {
    if (group.kind !== "flow" || !group.nodeIds?.length) return [];
    const bounds = boundsForNodes(nodes, group.nodeIds);
    const inside =
      point.x >= bounds.position.x &&
      point.x <= bounds.position.x + bounds.width &&
      point.y >= bounds.position.y &&
      point.y <= bounds.position.y + bounds.height;
    if (!inside) return [];
    return [{ group, area: bounds.width * bounds.height }];
  });
  if (!hits.length) return null;
  if (preferredId) {
    const preferred = hits.find((hit) => hit.group.id === preferredId);
    if (preferred) return preferred.group;
  }
  hits.sort((a, b) => a.area - b.area);
  return hits[0]?.group ?? null;
}

/**
 * @param {WorkflowGroup} group
 * @param {string[]} nodeIds
 * @param {EditorNode[]} nodes
 * @param {EditorEdge[]} edges
 */
function expandFlowGroup(group, nodeIds, nodes, edges) {
  const known = new Set(group.nodeIds);
  const extraStarts = nodeIds.filter((id) => !known.has(id));
  const startNodeIds = [
    ...new Set([...(group.startNodeIds || []), ...extraStarts]),
  ];
  const nextNodeIds = downstreamNodeIds(startNodeIds, edges).filter((id) =>
    nodes.some((node) => node.id === id),
  );
  return {
    ...group,
    startNodeIds,
    nodeIds: nextNodeIds,
    ...boundsForNodes(nodes, nextNodeIds),
  };
}

/**
 * @param {WorkflowGroup[]} groups
 * @param {string[]} seedIds
 * @param {string | null} [preferredId]
 */
function findOverlappingFlow(groups, seedIds, preferredId = null) {
  const seeds = new Set(seedIds);
  const hits = groups.filter(
    (group) =>
      group.kind === "flow" &&
      group.nodeIds?.some((id) => seeds.has(id)),
  );
  if (!hits.length) return null;
  if (preferredId) {
    const preferred = hits.find((group) => group.id === preferredId);
    if (preferred) return preferred;
  }
  return [...hits].sort((a, b) => {
    const overlapA = a.nodeIds.filter((id) => seeds.has(id)).length;
    const overlapB = b.nodeIds.filter((id) => seeds.has(id)).length;
    return overlapB - overlapA;
  })[0];
}
/** @type {import("zustand").StateCreator<EditorState>} */
const createEditorState = (set, get) => ({
  nodes: [],
  edges: [],
  groups: [],
  selectedGroupId: null,
  past: [],
  future: [],
  dirty: false,
  project: projectTemplate(),
  definitions: [],
  setDefinitions: (definitions) => set({ definitions }),
  addNode: (schemaId, position = { x: 120, y: 120 }, options = {}) => {
    const definition = get().definitions.find(
      (value) => value.schemaId === schemaId,
    );
    if (!definition) return null;
    const node = createNode(definition, position);
    const flowId = options?.flowId;
    set((state) => {
      const nodes = [
        ...state.nodes.map((value) => ({ ...value, selected: false })),
        { ...node, selected: true },
      ];
      const groups =
        flowId && state.groups.some((group) => group.id === flowId)
          ? state.groups.map((group) =>
              group.id === flowId
                ? expandFlowGroup(group, [node.id], nodes, state.edges)
                : group,
            )
          : state.groups;
      return history(state, { nodes, groups });
    });
    return node.id;
  },
  addNodesToFlow: (flowId, nodeIds) => {
    if (!flowId || !nodeIds?.length) return null;
    const state = get();
    if (!state.groups.some((group) => group.id === flowId)) return null;
    set((current) => ({
      ...history(current, {
        groups: current.groups.map((group) =>
          group.id === flowId
            ? expandFlowGroup(group, nodeIds, current.nodes, current.edges)
            : group,
        ),
      }),
      selectedGroupId: flowId,
    }));
    return flowId;
  },
  onNodesChange: (changes) =>
    set((state) => {
      const changed = applyNodeChanges(changes, state.nodes);
      const permanent = changes.some((change) => change.type === "remove");
      const remainingEdges = permanent
        ? state.edges.filter(
            (edge) =>
              changed.some((node) => node.id === edge.source) &&
              changed.some((node) => node.id === edge.target),
          )
        : state.edges;
      const groups = permanent
        ? refreshFlowGroups(state.groups, changed, remainingEdges)
        : state.groups;
      const patch = permanent
        ? history(state, { nodes: changed, edges: remainingEdges, groups })
        : {
            nodes: changed,
            dirty:
              state.dirty ||
              changes.some((change) => change.type === "position"),
          };
      return {
        ...patch,
        selectedGroupId:
          groups.some((group) => group.id === state.selectedGroupId) &&
          !changes.some((change) => change.type === "select" && change.selected)
            ? state.selectedGroupId
            : null,
      };
    }),
  onEdgesChange: (changes) =>
    set((state) => {
      const edges = applyEdgeChanges(changes, state.edges);
      return history(state, {
        edges,
        groups: refreshFlowGroups(state.groups, state.nodes, edges),
      });
    }),
  canConnect: (connection) => {
    const state = get();
    const map = definitionsById(state.definitions);
    const source = state.nodes.find((node) => node.id === connection.source);
    const target = state.nodes.find((node) => node.id === connection.target);
    if (!source || !target || source.id === target.id)
      return {
        valid: false,
        reason: "Connections require two different nodes.",
      };
    const sourcePort = map[source.data.schemaId]?.outputs.find(
      (port) => port.id === connection.sourceHandle,
    );
    const targetPort = map[target.data.schemaId]?.inputs.find(
      (port) => port.id === connection.targetHandle,
    );
    if (!sourcePort || !targetPort)
      return { valid: false, reason: "The selected port no longer exists." };
    if (!compatibleTypes(sourcePort.type, targetPort.type))
      return {
        valid: false,
        reason: `${sourcePort.type} cannot connect to ${targetPort.type}.`,
      };
    if (
      !targetPort.multiple &&
      hasBatchSource(
        source.id,
        state.nodes,
        state.edges,
        state.definitions,
      )
    )
      return {
        valid: false,
        reason: `${targetPort.label} accepts one item, but this output contains a queue.`,
      };
    if (
      !targetPort.multiple &&
      state.edges.some(
        (edge) =>
          edge.target === target.id && edge.targetHandle === targetPort.id,
      )
    )
      return {
        valid: false,
        reason: `${targetPort.label} already has a connection.`,
      };
    if (linkedNodeIds(target.id, state.edges, "downstream").has(source.id))
      return {
        valid: false,
        reason: "This connection would create a cycle.",
      };
    const repeated = repeatedProcessorForConnection(
      state.nodes,
      state.edges,
      source.id,
      target.id,
      state.definitions,
    );
    if (repeated)
      return {
        valid: false,
        reason: `${repeated.name} already exists in this linked path.`,
      };
    return { valid: true, reason: "" };
  },
  connect: (connection) => {
    const result = get().canConnect(connection);
    if (!result.valid) return result;
    set((state) => {
      const source = state.nodes.find((node) => node.id === connection.source);
      const sourceDefinition = source
        ? definitionsById(state.definitions)[source.data.schemaId]
        : undefined;
      const sourcePort = sourceDefinition?.outputs.find(
        (port) => port.id === connection.sourceHandle,
      );
      const edges = addEdge(
        {
          ...connection,
          id: crypto.randomUUID(),
          type: "lluna",
          data: { portType: sourcePort?.type || "" },
        },
        state.edges,
      );
      return history(state, {
        edges,
        groups: absorbConnectedIntoFlows(
          state.groups,
          state.nodes,
          edges,
          connection.source,
          connection.target,
        ),
      });
    });
    return result;
  },
  removeEdge: (id) =>
    set((state) => {
      const edges = state.edges.filter((edge) => edge.id !== id);
      return history(state, {
        edges,
        groups: refreshFlowGroups(state.groups, state.nodes, edges),
      });
    }),
  updateNode: (id, patch) =>
    set((state) => {
      const nodes = state.nodes.map((node) =>
        node.id === id
          ? {
              ...node,
              data: {
                ...node.data,
                ...patch,
                parameters: patch.parameters ?? node.data.parameters,
              },
            }
          : node,
      );
      const synced = patch.parameters
        ? reconcileLlavaCompanion(state, nodes, state.edges, id)
        : { nodes, edges: state.edges, groups: state.groups };
      return history(state, synced);
    }),
  setNodeModel: (id, value) =>
    set((state) => {
      const nodes = state.nodes.map((node) =>
        node.id === id
          ? {
              ...node,
              data: {
                ...node.data,
                parameters: { ...node.data.parameters, model: value },
                result: node.data.result
                  ? { ...node.data.result, status: "STALE" }
                  : node.data.result,
              },
            }
          : node,
      );
      return history(
        state,
        reconcileLlavaCompanion(state, nodes, state.edges, id),
      );
    }),
  recordNodeResult: (id, result) =>
    set((state) => ({
      nodes: state.nodes.map((node) =>
        node.id === id
          ? {
              ...node,
              data: {
                ...node.data,
                result: { ...node.data.result, ...result },
              },
            }
          : node,
      ),
      dirty: true,
    })),
  selectAll: () =>
    set((state) => ({
      nodes: state.nodes.map((node) => ({ ...node, selected: true })),
      edges: state.edges,
      selectedGroupId: null,
    })),
  deselect: () =>
    set((state) => ({
      nodes: state.nodes.map((node) => ({ ...node, selected: false })),
      edges: state.edges.map((edge) => ({ ...edge, selected: false })),
      selectedGroupId: null,
    })),
  focusNode: (id) => {
    set((state) => ({
      nodes: state.nodes.map((node) => ({ ...node, selected: node.id === id })),
      edges: state.edges.map((edge) => ({ ...edge, selected: false })),
      selectedGroupId: null,
    }));
    window.dispatchEvent(
      new CustomEvent("lluna:focus-node", { detail: { id } }),
    );
  },
  deleteSelected: () =>
    set((state) => {
      const ids = new Set(
        state.nodes.filter((node) => node.selected).map((node) => node.id),
      );
      if (!ids.size && !state.edges.some((edge) => edge.selected))
        return state.selectedGroupId
          ? {
              ...history(state, {
                groups: state.groups.filter(
                  (group) => group.id !== state.selectedGroupId,
                ),
              }),
              selectedGroupId: null,
            }
          : state;
      const nodes = state.nodes.filter((node) => !ids.has(node.id));
      const edges = state.edges.filter(
        (edge) =>
          !edge.selected && !ids.has(edge.source) && !ids.has(edge.target),
      );
      const groups = refreshFlowGroups(state.groups, nodes, edges);
      return {
        ...history(state, { nodes, edges, groups }),
        selectedGroupId: groups.some(
          (group) => group.id === state.selectedGroupId,
        )
          ? state.selectedGroupId
          : null,
      };
    }),
  copySelected: () => {
    const state = get();
    const ids = new Set(
      state.nodes.filter((node) => node.selected).map((node) => node.id),
    );
    clipboard = {
      nodes: structuredClone(state.nodes.filter((node) => ids.has(node.id))),
      edges: structuredClone(
        state.edges.filter(
          (edge) => ids.has(edge.source) && ids.has(edge.target),
        ),
      ),
    };
  },
  duplicateSelected: () => {
    get().copySelected();
    get().paste();
  },
  paste: () =>
    set((state) => {
      if (!clipboard.nodes.length) return state;
      const ids = new Map(
        clipboard.nodes.map((node) => [node.id, crypto.randomUUID()]),
      );
    const remap = (/** @type {string} */ id) => {
        const mapped = ids.get(id);
        if (!mapped) throw new Error(`Missing clipboard node ${id}`);
        return mapped;
      };
      /** @type {EditorNode[]} */ const nodes = clipboard.nodes.map((node) => ({
        ...structuredClone(node),
        id: remap(node.id),
        position: { x: node.position.x + 32, y: node.position.y + 32 },
        selected: true,
      }));
      /** @type {EditorEdge[]} */ const edges = clipboard.edges.map((edge) => ({
        ...structuredClone(edge),
        id: crypto.randomUUID(),
        source: remap(edge.source),
        target: remap(edge.target),
        selected: false,
      }));
      clipboard = {
        nodes: structuredClone(nodes),
        edges: structuredClone(edges),
      };
      return history(state, {
        nodes: [
          ...state.nodes.map((node) => ({ ...node, selected: false })),
          ...nodes,
        ],
        edges: [...state.edges, ...edges],
      });
    }),
  groupSelected: () => get().createFlowFromSelected(),
  createFlowFromSelected: () => {
    const state = get();
    const seeds = state.nodes
      .filter((node) => node.selected)
      .map((node) => node.id);
    if (!seeds.length) return null;
    const existing = findOverlappingFlow(
      state.groups,
      seeds,
      state.selectedGroupId,
    );
    if (existing) {
      set((current) => ({
        ...history(current, {
          groups: current.groups.map((group) =>
            group.id === existing.id
              ? expandFlowGroup(group, seeds, current.nodes, current.edges)
              : group,
          ),
          nodes: current.nodes.map((node) => ({ ...node, selected: false })),
        }),
        selectedGroupId: existing.id,
      }));
      return existing.id;
    }
    const nodeIds = downstreamNodeIds(seeds, state.edges);
    const bounds = boundsForNodes(state.nodes, nodeIds);
    const id = crypto.randomUUID();
    const group = {
      id,
      kind: "flow",
      label: `Flow ${state.groups.length + 1}`,
      nodeIds,
      startNodeIds: seeds,
      ...bounds,
      color: "teal",
      appearance: { imageEffect: "none" },
    };
    set((current) => ({
      ...history(current, {
        groups: [...current.groups, group],
        nodes: current.nodes.map((node) => ({ ...node, selected: false })),
      }),
      selectedGroupId: id,
    }));
    return id;
  },
  selectGroup: (id) =>
    set((state) => ({
      selectedGroupId: id,
      nodes: state.nodes.map((node) => ({ ...node, selected: false })),
      edges: state.edges.map((edge) => ({ ...edge, selected: false })),
    })),
  moveFlowBy: (flowId, delta) =>
    set((state) => {
      const group = state.groups.find((item) => item.id === flowId);
      if (!group || (!delta.x && !delta.y)) return state;
      const ids = new Set(group.nodeIds);
      return {
        nodes: state.nodes.map((node) =>
          ids.has(node.id)
            ? {
                ...node,
                position: {
                  x: node.position.x + delta.x,
                  y: node.position.y + delta.y,
                },
              }
            : node,
        ),
        dirty: true,
      };
    }),
  updateGroup: (id, patch) =>
    set((state) =>
      history(state, {
        groups: state.groups.map((group) =>
          group.id === id
            ? {
                ...group,
                ...patch,
                appearance: patch.appearance ?? group.appearance,
              }
            : group,
        ),
      }),
    ),
  fitGroup: (id) =>
    set((state) => {
      const group = state.groups.find((item) => item.id === id);
      if (!group) return state;
      const bounds = boundsForNodes(state.nodes, group.nodeIds);
      return history(state, {
        groups: state.groups.map((item) =>
          item.id === id ? { ...item, ...bounds } : item,
        ),
      });
    }),
  removeGroup: (id) =>
    set((state) => ({
      ...history(state, {
        groups: state.groups.filter((group) => group.id !== id),
      }),
      selectedGroupId:
        state.selectedGroupId === id ? null : state.selectedGroupId,
    })),
  autoLayout: () =>
    set((state) =>
      history(state, {
        nodes: state.nodes.map((node, index) => ({
          ...node,
          position: { x: (index % 4) * 330, y: Math.floor(index / 4) * 240 },
        })),
      }),
    ),
  undo: () =>
    set((state) => {
      if (!state.past.length) return state;
      const previous = state.past.at(-1);
      return {
        ...previous,
        past: state.past.slice(0, -1),
        future: [snap(state), ...state.future],
        dirty: true,
      };
    }),
  redo: () =>
    set((state) => {
      if (!state.future.length) return state;
      const next = state.future[0];
      return {
        ...next,
        past: [...state.past, snap(state)],
        future: state.future.slice(1),
        dirty: true,
      };
    }),
  markSaved: () => set({ dirty: false }),
  setViewport: (viewport) =>
    set((state) => ({ project: { ...state.project, viewport } })),
  setProjectName: (name) =>
    set((state) => ({ project: { ...state.project, name }, dirty: true })),
  newWorkflow: (document) =>
    set({
      nodes: [],
      edges: [],
      groups: [],
      selectedGroupId: null,
      past: [],
      future: [],
      dirty: false,
      project: document ? projectFromDocument(document) : projectTemplate(),
    }),
  loadWorkflow: (document, definitions = get().definitions) => {
    const map = definitionsById(definitions);
    /** @type {EditorNode[]} */
    const nodes = document.nodes.map((node) => ({
      id: node.id,
      type: "lluna",
      position: node.position,
      data: {
        schemaId: node.schemaId,
        schemaVersion: node.schemaVersion,
        label: node.label || map[node.schemaId]?.name || node.schemaId,
        parameters: restoredParameters(map[node.schemaId], node.parameters),
        appearance: { ...DEFAULT_APPEARANCE, ...node.appearance },
        result: node.result || null,
        definition: map[node.schemaId],
        disabled: node.disabled,
        collapsed: node.collapsed,
      },
    }));
    /** @type {EditorEdge[]} */
    const edges = document.edges.map((edge) => {
      const sourceNode = document.nodes.find(
        (node) => node.id === edge.sourceNodeId,
      );
      const sourcePort = sourceNode
        ? map[sourceNode.schemaId]?.outputs.find(
            (port) => port.id === edge.sourcePortId,
          )
        : undefined;
      return {
        id: edge.id,
        source: edge.sourceNodeId,
        sourceHandle: edge.sourcePortId,
        target: edge.targetNodeId,
        targetHandle: edge.targetPortId,
        type: "lluna",
        data: { portType: sourcePort?.type || "" },
      };
    });
    let synced = {
      nodes,
      edges,
      groups: refreshFlowGroups(document.groups || [], nodes, edges),
    };
    for (const node of nodes) {
      if (node.data.schemaId !== UPSCALE_SCHEMA_ID) continue;
      synced = reconcileLlavaCompanion(
        { ...get(), definitions, groups: synced.groups },
        synced.nodes,
        synced.edges,
        node.id,
      );
    }
    set({
      project: projectFromDocument(document),
      nodes: synced.nodes,
      edges: synced.edges,
      groups: synced.groups,
      selectedGroupId: null,
      past: [],
      future: [],
      dirty: synced.nodes.length !== nodes.length,
    });
  },
  serialize: () => {
    const state = get();
    return {
      ...state.project,
      updatedAt: new Date().toISOString(),
      nodes: state.nodes.map((node) => ({
        id: node.id,
        schemaId: node.data.schemaId,
        schemaVersion: node.data.schemaVersion,
        label: node.data.label,
        position: node.position,
        parameters: node.data.parameters || {},
        appearance: { ...DEFAULT_APPEARANCE, ...node.data.appearance },
        result: node.data.result || undefined,
        disabled: Boolean(node.data.disabled),
        collapsed: Boolean(node.data.collapsed),
      })),
      edges: state.edges.map((edge) => ({
        id: edge.id,
        sourceNodeId: edge.source,
        sourcePortId: String(edge.sourceHandle || ""),
        targetNodeId: edge.target,
        targetPortId: String(edge.targetHandle || ""),
      })),
      groups: state.groups,
    };
  },
});
export const useEditorStore = create(createEditorState);
