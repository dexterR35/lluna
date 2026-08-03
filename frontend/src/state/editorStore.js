import { create } from "zustand";
import { addEdge, applyEdgeChanges, applyNodeChanges } from "@xyflow/react";
const MAX_HISTORY = 100;
let clipboard = { nodes: [], edges: [] };
const snap = state => ({ nodes: structuredClone(state.nodes), edges: structuredClone(state.edges), groups: structuredClone(state.groups) });
const history = (state, patch) => ({ ...patch, past: [...state.past.slice(-(MAX_HISTORY - 1)), snap(state)], future: [], dirty: true });
const definitionsById = definitions => Object.fromEntries(definitions.map(value => [value.schemaId, value]));
const defaults = definition => Object.fromEntries(definition.parameters.map(parameter => [parameter.id, structuredClone(parameter.default)]));
const restoredParameters = (definition, saved = {}) => {
  if (!definition) return saved;
  const values = { ...defaults(definition), ...saved };
  for (const parameter of definition.parameters) if (parameter.type === "model" && !values[parameter.id]) values[parameter.id] = structuredClone(parameter.default);
  return values;
};
export const DEFAULT_APPEARANCE = {
  cardStyle: "visual",
  imageEffect: "none",
  imageFit: "cover",
  imageRatio: "wide",
  accent: "teal",
  showPreview: true,
};
function createNode(definition, position) { return { id: crypto.randomUUID(), type: "midgard", position, data: { schemaId: definition.schemaId, schemaVersion: definition.schemaVersion, label: definition.name, parameters: defaults(definition), appearance: { ...DEFAULT_APPEARANCE }, definition }, selected: false }; }
function projectTemplate() { const now = new Date().toISOString(); return { format: "midgard-workflow", version: 1, projectId: crypto.randomUUID(), name: "Untitled workflow", createdAt: now, updatedAt: now, projectSettings: {}, viewport: { x: 0, y: 0, zoom: 1 }, metadata: {} }; }

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

function refreshFlowGroups(groups, nodes, edges) {
  const known = new Set(nodes.map(node => node.id));
  return groups.flatMap(group => {
    if (group.kind !== "flow" || !group.startNodeIds?.length) return [group];
    const startNodeIds = group.startNodeIds.filter(id => known.has(id));
    if (!startNodeIds.length) return [];
    return [{ ...group, startNodeIds, nodeIds: downstreamNodeIds(startNodeIds, edges).filter(id => known.has(id)) }];
  });
}

export function boundsForNodes(nodes, nodeIds) {
  const members = nodes.filter(node => nodeIds.includes(node.id));
  if (!members.length) return { position: { x: 80, y: 80 }, width: 360, height: 240 };
  const minX = Math.min(...members.map(node => node.position.x));
  const minY = Math.min(...members.map(node => node.position.y));
  const maxX = Math.max(...members.map(node => node.position.x + (node.measured?.width || node.width || 256)));
  const maxY = Math.max(...members.map(node => node.position.y + (node.measured?.height || node.height || 190)));
  return { position: { x: minX - 44, y: minY - 72 }, width: maxX - minX + 88, height: maxY - minY + 116 };
}
export const useEditorStore = create((set, get) => ({
  nodes: [], edges: [], groups: [], selectedGroupId: null, past: [], future: [], dirty: false, project: projectTemplate(), definitions: [],
  setDefinitions: definitions => set({ definitions }),
  addNode: (schemaId, position = { x: 120, y: 120 }) => { const definition = get().definitions.find(value => value.schemaId === schemaId); if (!definition) return null; const node = createNode(definition, position); set(state => history(state, { nodes: [...state.nodes.map(value => ({ ...value, selected: false })), { ...node, selected: true }] })); return node.id; },
  onNodesChange: changes => set(state => { const changed = applyNodeChanges(changes, state.nodes); const permanent = changes.some(change => change.type === "remove"); const remainingEdges = permanent ? state.edges.filter(edge => changed.some(node => node.id === edge.source) && changed.some(node => node.id === edge.target)) : state.edges; const groups = permanent ? refreshFlowGroups(state.groups, changed, remainingEdges) : state.groups; const patch = permanent ? history(state, { nodes: changed, edges: remainingEdges, groups }) : { nodes: changed, dirty: state.dirty || changes.some(change => change.type === "position") }; return { ...patch, selectedGroupId: groups.some(group => group.id === state.selectedGroupId) && !changes.some(change => change.type === "select" && change.selected) ? state.selectedGroupId : null }; }),
  onEdgesChange: changes => set(state => { const edges = applyEdgeChanges(changes, state.edges); return history(state, { edges, groups: refreshFlowGroups(state.groups, state.nodes, edges) }); }),
  canConnect: connection => { const state = get(); const map = definitionsById(state.definitions); const source = state.nodes.find(node => node.id === connection.source); const target = state.nodes.find(node => node.id === connection.target); if (!source || !target || source.id === target.id) return { valid: false, reason: "Connections require two different nodes." }; const sourcePort = map[source.data.schemaId]?.outputs.find(port => port.id === connection.sourceHandle); const targetPort = map[target.data.schemaId]?.inputs.find(port => port.id === connection.targetHandle); if (!sourcePort || !targetPort) return { valid: false, reason: "The selected port no longer exists." }; if (!(sourcePort.type === targetPort.type || (sourcePort.type === "INTEGER" && targetPort.type === "NUMBER"))) return { valid: false, reason: `${sourcePort.type} cannot connect to ${targetPort.type}.` }; if (state.edges.some(edge => edge.target === target.id && edge.targetHandle === targetPort.id)) return { valid: false, reason: `${targetPort.label} already has a connection.` }; return { valid: true, reason: "" }; },
  connect: connection => { const result = get().canConnect(connection); if (!result.valid) return result; set(state => { const edges = addEdge({ ...connection, id: crypto.randomUUID(), type: "midgard" }, state.edges); return history(state, { edges, groups: refreshFlowGroups(state.groups, state.nodes, edges) }); }); return result; },
  removeEdge: id => set(state => { const edges = state.edges.filter(edge => edge.id !== id); return history(state, { edges, groups: refreshFlowGroups(state.groups, state.nodes, edges) }); }),
  updateNode: (id, patch) => set(state => history(state, { nodes: state.nodes.map(node => node.id === id ? { ...node, data: { ...node.data, ...patch, parameters: patch.parameters ?? node.data.parameters } } : node) })),
  recordNodeResult: (id, result) => set(state => ({ nodes: state.nodes.map(node => node.id === id ? { ...node, data: { ...node.data, result: { ...node.data.result, ...result } } } : node), dirty: true })),
  selectAll: () => set(state => ({ nodes: state.nodes.map(node => ({ ...node, selected: true })), edges: state.edges, selectedGroupId: null })),
  deselect: () => set(state => ({ nodes: state.nodes.map(node => ({ ...node, selected: false })), edges: state.edges.map(edge => ({ ...edge, selected: false })), selectedGroupId: null })),
  focusNode: id => { set(state => ({ nodes: state.nodes.map(node => ({ ...node, selected: node.id === id })), edges: state.edges.map(edge => ({ ...edge, selected: false })), selectedGroupId: null })); window.dispatchEvent(new CustomEvent("midgard:focus-node", { detail: { id } })); },
  deleteSelected: () => set(state => {
    const ids = new Set(state.nodes.filter(node => node.selected).map(node => node.id));
    if (!ids.size && !state.edges.some(edge => edge.selected)) return state.selectedGroupId ? { ...history(state, { groups: state.groups.filter(group => group.id !== state.selectedGroupId) }), selectedGroupId: null } : state;
    const nodes = state.nodes.filter(node => !ids.has(node.id));
    const edges = state.edges.filter(edge => !edge.selected && !ids.has(edge.source) && !ids.has(edge.target));
    const groups = refreshFlowGroups(state.groups, nodes, edges);
    return { ...history(state, { nodes, edges, groups }), selectedGroupId: groups.some(group => group.id === state.selectedGroupId) ? state.selectedGroupId : null };
  }),
  copySelected: () => { const state = get(); const ids = new Set(state.nodes.filter(node => node.selected).map(node => node.id)); clipboard = { nodes: structuredClone(state.nodes.filter(node => ids.has(node.id))), edges: structuredClone(state.edges.filter(edge => ids.has(edge.source) && ids.has(edge.target))) }; },
  duplicateSelected: () => { get().copySelected(); get().paste(); },
  paste: () => set(state => { if (!clipboard.nodes.length) return state; const ids = new Map(clipboard.nodes.map(node => [node.id, crypto.randomUUID()])); const nodes = clipboard.nodes.map(node => ({ ...structuredClone(node), id: ids.get(node.id), position: { x: node.position.x + 32, y: node.position.y + 32 }, selected: true })); const edges = clipboard.edges.map(edge => ({ ...structuredClone(edge), id: crypto.randomUUID(), source: ids.get(edge.source), target: ids.get(edge.target), selected: false })); clipboard = { nodes: structuredClone(nodes), edges: structuredClone(edges) }; return history(state, { nodes: [...state.nodes.map(node => ({ ...node, selected: false })), ...nodes], edges: [...state.edges, ...edges] }); }),
  groupSelected: () => get().createFlowFromSelected(),
  createFlowFromSelected: () => {
    const state = get();
    const seeds = state.nodes.filter(node => node.selected).map(node => node.id);
    if (!seeds.length) return null;
    const nodeIds = downstreamNodeIds(seeds, state.edges);
    const bounds = boundsForNodes(state.nodes, nodeIds);
    const id = crypto.randomUUID();
    const group = { id, kind: "flow", label: `Flow ${state.groups.length + 1}`, nodeIds, startNodeIds: seeds, ...bounds, color: "teal", appearance: { imageEffect: "none" } };
    set(current => ({ ...history(current, { groups: [...current.groups, group], nodes: current.nodes.map(node => ({ ...node, selected: false })) }), selectedGroupId: id }));
    return id;
  },
  selectGroup: id => set(state => ({ selectedGroupId: id, nodes: state.nodes.map(node => ({ ...node, selected: false })), edges: state.edges.map(edge => ({ ...edge, selected: false })) })),
  updateGroup: (id, patch) => set(state => history(state, { groups: state.groups.map(group => group.id === id ? { ...group, ...patch, appearance: patch.appearance ?? group.appearance } : group) })),
  fitGroup: id => set(state => { const group = state.groups.find(item => item.id === id); if (!group) return state; const bounds = boundsForNodes(state.nodes, group.nodeIds); return history(state, { groups: state.groups.map(item => item.id === id ? { ...item, ...bounds } : item) }); }),
  removeGroup: id => set(state => ({ ...history(state, { groups: state.groups.filter(group => group.id !== id) }), selectedGroupId: state.selectedGroupId === id ? null : state.selectedGroupId })),
  autoLayout: () => set(state => history(state, { nodes: state.nodes.map((node, index) => ({ ...node, position: { x: (index % 4) * 330, y: Math.floor(index / 4) * 240 } })) })),
  undo: () => set(state => { if (!state.past.length) return state; const previous = state.past.at(-1); return { ...previous, past: state.past.slice(0, -1), future: [snap(state), ...state.future], dirty: true }; }),
  redo: () => set(state => { if (!state.future.length) return state; const next = state.future[0]; return { ...next, past: [...state.past, snap(state)], future: state.future.slice(1), dirty: true }; }),
  markSaved: () => set({ dirty: false }), setViewport: viewport => set(state => ({ project: { ...state.project, viewport } })), setProjectName: name => set(state => ({ project: { ...state.project, name }, dirty: true })),
  newWorkflow: document => set({ nodes: [], edges: [], groups: [], selectedGroupId: null, past: [], future: [], dirty: false, project: document || projectTemplate() }),
  loadWorkflow: (document, definitions = get().definitions) => {
    const map = definitionsById(definitions);
    const nodes = document.nodes.map(node => ({ id: node.id, type: "midgard", position: node.position, data: { schemaId: node.schemaId, schemaVersion: node.schemaVersion, label: node.label || map[node.schemaId]?.name || node.schemaId, parameters: restoredParameters(map[node.schemaId], node.parameters), appearance: { ...DEFAULT_APPEARANCE, ...node.appearance }, result: node.result || null, definition: map[node.schemaId], disabled: node.disabled, collapsed: node.collapsed } }));
    const edges = document.edges.map(edge => ({ id: edge.id, source: edge.sourceNodeId, sourceHandle: edge.sourcePortId, target: edge.targetNodeId, targetHandle: edge.targetPortId, type: "midgard" }));
    set({ project: { ...document, nodes: undefined, edges: undefined, groups: undefined }, nodes, edges, groups: refreshFlowGroups(document.groups || [], nodes, edges), selectedGroupId: null, past: [], future: [], dirty: false });
  },
  serialize: () => { const state = get(); return { ...state.project, updatedAt: new Date().toISOString(), nodes: state.nodes.map(node => ({ id: node.id, schemaId: node.data.schemaId, schemaVersion: node.data.schemaVersion, label: node.data.label, position: node.position, parameters: node.data.parameters || {}, appearance: { ...DEFAULT_APPEARANCE, ...node.data.appearance }, result: node.data.result || undefined, disabled: Boolean(node.data.disabled), collapsed: Boolean(node.data.collapsed) })), edges: state.edges.map(edge => ({ id: edge.id, sourceNodeId: edge.source, sourcePortId: edge.sourceHandle, targetNodeId: edge.target, targetPortId: edge.targetHandle })), groups: state.groups }; },
}));
