import { create } from "zustand";
import { addEdge, applyEdgeChanges, applyNodeChanges } from "@xyflow/react";
import { compatibleTypes } from "../icons";
import { applyCapabilityDefaults, capabilityContract } from "../models/modelCapabilities";
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
// A burst of rapid same-target edits (typing in one field, nudging one
// slider) shares a single undo checkpoint instead of one `structuredClone`
// of the whole graph per keystroke. Any edit outside the window - or with no
// `coalesceWith` key - always gets its own checkpoint, so unrelated actions
// (delete, connect, paste...) are never merged together.
const COALESCE_WINDOW_MS = 700;
let coalesceKey = /** @type {string | null} */ (null);
let coalesceStamp = 0;
/**
 * @param {EditorState} state
 * @param {Partial<EditorState>} patch
 * @param {string | null} [coalesceWith]
 */
const history = (state, patch, coalesceWith = null) => {
  const now = Date.now();
  const coalescing =
    coalesceWith != null &&
    coalesceWith === coalesceKey &&
    now - coalesceStamp < COALESCE_WINDOW_MS;
  coalesceKey = coalesceWith;
  coalesceStamp = now;
  return {
    ...patch,
    past: coalescing
      ? state.past
      : [...state.past.slice(-(MAX_HISTORY - 1)), snap(state)],
    future: [],
    dirty: true,
  };
};
/**
 * Push an undo checkpoint for the current state without changing anything -
 * used before a drag gesture starts, since drags update positions on every
 * pointer-move frame and only the pre-drag position should be undoable.
 * @param {EditorState} state
 */
const checkpoint = (state) => {
  coalesceKey = null;
  return {
    past: [...state.past.slice(-(MAX_HISTORY - 1)), snap(state)],
    future: [],
  };
};
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

/**
 * Attach/detach one declared companion (see NodeDefinition.companions) for a
 * host node, e.g. the Upscale node's SUPIR model wants a LLaVA Caption node
 * wired into its `llava` input whenever `useLlava` is on. Data-driven from
 * the backend node definition so the store never needs to know specific
 * schema/model ids itself.
 * @param {EditorState} state
 * @param {EditorNode[]} nodes
 * @param {EditorEdge[]} edges
 * @param {WorkflowGroup[]} groups
 * @param {string} hostId
 * @param {import("../types").NodeCompanion} companion
 */
function reconcileCompanion(state, nodes, edges, groups, hostId, companion) {
  const host = nodes.find((node) => node.id === hostId);
  if (!host) return { nodes, edges, groups };

  const connectedEdges = edges.filter(
    (edge) =>
      edge.target === hostId && edge.targetHandle === companion.targetPort,
  );
  const companionIds = new Set(
    connectedEdges.flatMap((edge) => {
      const source = nodes.find((node) => node.id === edge.source);
      return source?.data.schemaId === companion.schemaId ? [source.id] : [];
    }),
  );
  const shouldExist = (companion.when || []).every(
    (condition) =>
      host.data.parameters?.[condition.parameterId] === condition.equals,
  );

  if (shouldExist && !companionIds.size && !connectedEdges.length) {
    const definition = state.definitions.find(
      (item) => item.schemaId === companion.schemaId,
    );
    if (!definition) return { nodes, edges, groups };
    const companionNode = {
      ...createNode(definition, {
        x: host.position.x - 320,
        y: host.position.y + 32,
      }),
      selected: false,
    };
    const sourcePort = definition.outputs.find(
      (port) => port.id === companion.sourcePort,
    );
    const nextNodes = [...nodes, companionNode];
    const nextEdges = [
      ...edges,
      {
        id: crypto.randomUUID(),
        source: companionNode.id,
        sourceHandle: companion.sourcePort,
        target: hostId,
        targetHandle: companion.targetPort,
        type: "lluna",
        data: { portType: sourcePort?.type || "" },
      },
    ];
    const targetGroup = groups.find((group) =>
      group.nodeIds.includes(hostId),
    );
    const nextGroups = targetGroup
      ? groups.map((group) =>
          group.id === targetGroup.id
            ? expandFlowGroup(group, [companionNode.id], nextNodes, nextEdges)
            : group,
        )
      : groups;
    return { nodes: nextNodes, edges: nextEdges, groups: nextGroups };
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
      groups: refreshFlowGroups(groups, nextNodes, nextEdges),
    };
  }
  return { nodes, edges, groups };
}

/**
 * Reconcile every companion a node declares.
 * @param {EditorState} state
 * @param {EditorNode[]} nodes
 * @param {EditorEdge[]} edges
 * @param {string} hostId
 */
function reconcileCompanions(state, nodes, edges, hostId) {
  const host = nodes.find((node) => node.id === hostId);
  const companions = host?.data.definition?.companions;
  if (!host || !companions?.length)
    return { nodes, edges, groups: state.groups };
  return companions.reduce(
    (acc, companion) =>
      reconcileCompanion(state, acc.nodes, acc.edges, acc.groups, hostId, companion),
    { nodes, edges, groups: state.groups },
  );
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
  setDefinitions: (definitions) =>
    set((state) => {
      const map = definitionsById(definitions);
      const nodes = state.nodes.map((node) => {
        const next = map[node.data.schemaId];
        // A node placed before a model install/config change keeps whatever
        // NodeDefinition it was created with (LlunaNode.jsx reads
        // `data.definition`, not a live lookup) unless refreshed here.
        if (!next || next === node.data.definition) return node;
        return { ...node, data: { ...node.data, definition: next } };
      });
      return { definitions, nodes };
    }),
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
      const permanent = changes.some((change) => change.type === "remove");
      if (!permanent) return { edges };
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
      // Any parameter edit invalidates this node's last result (unless the
      // patch sets its own `result`, e.g. dropping a file that's already
      // loaded) and every downstream node's result, since they consumed the
      // now-stale output. Both editorStore's persisted `result.status` and
      // runStore's transient run state have to reflect this - see the
      // `downstreamNodeIds(...)` call at each `updateNode`/`setNodeModel`
      // call site, which clears the matching runStore entries.
      const staleDownstreamIds = patch.parameters
        ? new Set(
            downstreamNodeIds([id], state.edges).filter(
              (nodeId) => nodeId !== id,
            ),
          )
        : null;
      const nodes = state.nodes.map((node) => {
        if (node.id === id) {
          const nextResult =
            "result" in patch
              ? patch.result
              : patch.parameters && node.data.result
                ? { ...node.data.result, status: "STALE" }
                : node.data.result;
          return {
            ...node,
            data: {
              ...node.data,
              ...patch,
              parameters: patch.parameters ?? node.data.parameters,
              result: nextResult,
            },
          };
        }
        if (staleDownstreamIds?.has(node.id) && node.data.result) {
          return {
            ...node,
            data: {
              ...node.data,
              result: { ...node.data.result, status: "STALE" },
            },
          };
        }
        return node;
      });
      const synced = patch.parameters
        ? reconcileCompanions(state, nodes, state.edges, id)
        : { nodes, edges: state.edges, groups: state.groups };
      return history(state, synced, patch.parameters ? id : null);
    }),
  setNodeModel: (id, value) =>
    set((state) => {
      const staleDownstreamIds = new Set(
        downstreamNodeIds([id], state.edges).filter(
          (nodeId) => nodeId !== id,
        ),
      );
      const target = state.nodes.find((node) => node.id === id);
      const modelParameter = target?.data.definition?.parameters?.find(
        (parameter) => parameter.id === "model" || parameter.type === "model",
      );
      const selectedOption = modelParameter?.options?.find(
        (candidate) => String(candidate.value) === String(value),
      );
      const capabilities = capabilityContract(selectedOption);
      const nodes = state.nodes.map((node) => {
        if (node.id === id)
          return {
            ...node,
            data: {
              ...node.data,
              // Reset model-specific fields (steps/guidance/dtype/etc.) to
              // the newly selected model's defaults, same as the full node
              // editor dialog's model switcher (NodeEditorDialog.jsx) - this
              // compact footer selector used to only overwrite `model`,
              // leaving every other parameter tuned for the previous model.
              parameters: capabilities?.complete
                ? applyCapabilityDefaults(node.data.parameters || {}, capabilities, value)
                : { ...node.data.parameters, model: value },
              result: node.data.result
                ? { ...node.data.result, status: "STALE" }
                : node.data.result,
            },
          };
        if (staleDownstreamIds.has(node.id) && node.data.result)
          return {
            ...node,
            data: {
              ...node.data,
              result: { ...node.data.result, status: "STALE" },
            },
          };
        return node;
      });
      return history(
        state,
        reconcileCompanions(state, nodes, state.edges, id),
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
  /**
   * Drop a ready-made workflow onto the canvas without disturbing what is there.
   *
   * Unlike loadWorkflow, which replaces the document, a template is *added*: its
   * node ids are remapped to fresh ones so they cannot collide with existing
   * nodes, and it is placed below current content rather than on top of it. The
   * inserted nodes end up selected, so the next drag moves the template as one.
   *
   * @param {import("../types").WorkflowDocument} document
   */
  insertTemplate: (document) =>
    set((state) => {
      const definitions = definitionsById(state.definitions);
      const source = (document?.nodes || []).filter(
        (node) => definitions[node.schemaId],
      );
      if (!source.length) return state;
      const ids = new Map(source.map((node) => [node.id, crypto.randomUUID()]));
      const remap = (/** @type {string} */ id) => ids.get(id);
      // Clear of anything already on the canvas, so a template never lands on
      // top of the user's work.
      const bottom = state.nodes.reduce(
        (lowest, node) => Math.max(lowest, node.position?.y ?? 0),
        Number.NEGATIVE_INFINITY,
      );
      const offsetY = state.nodes.length ? bottom + 220 : 0;
      /** @type {EditorNode[]} */
      const nodes = source.map((node) => ({
        id: /** @type {string} */ (remap(node.id)),
        type: "lluna",
        position: {
          x: node.position?.x ?? 0,
          y: (node.position?.y ?? 0) + offsetY,
        },
        selected: true,
        data: {
          schemaId: node.schemaId,
          schemaVersion: definitions[node.schemaId]?.schemaVersion,
          label: definitions[node.schemaId]?.name || node.schemaId,
          parameters: restoredParameters(
            definitions[node.schemaId],
            node.parameters,
          ),
          appearance: { ...DEFAULT_APPEARANCE },
          result: null,
          definition: definitions[node.schemaId],
        },
      }));
      /** @type {EditorEdge[]} */
      const edges = (document?.edges || [])
        .filter((edge) => remap(edge.sourceNodeId) && remap(edge.targetNodeId))
        .map((edge) => {
          const sourceNode = source.find(
            (node) => node.id === edge.sourceNodeId,
          );
          const sourcePort = sourceNode
            ? definitions[sourceNode.schemaId]?.outputs.find(
                (port) => port.id === edge.sourcePortId,
              )
            : undefined;
          return {
            id: crypto.randomUUID(),
            source: /** @type {string} */ (remap(edge.sourceNodeId)),
            sourceHandle: edge.sourcePortId,
            target: /** @type {string} */ (remap(edge.targetNodeId)),
            targetHandle: edge.targetPortId,
            type: "lluna",
            data: { portType: sourcePort?.type || "" },
          };
        });
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
  checkpoint: () => set((state) => checkpoint(state)),
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
      if (!node.data.definition?.companions?.length) continue;
      synced = reconcileCompanions(
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
