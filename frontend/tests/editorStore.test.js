import { beforeEach, expect, test } from "vitest";
import { downstreamNodeIds, useEditorStore } from "../src/state/editorStore";
import { isVisibleCatalogNode } from "../src/workflow/catalogVisibility";
/** @type {import("../src/types").NodeDefinition} */
const definition = {
  schemaId: "test.number",
  schemaVersion: 1,
  name: "Number",
  parameters: [{ id: "value", label: "Value", type: "number", default: 1 }],
  inputs: [{ id: "value", label: "Value", type: "NUMBER" }],
  outputs: [{ id: "value", label: "Value", type: "INTEGER" }],
};

/** @param {string} [schemaId] @param {{x: number, y: number}} [position] */
function addNode(schemaId = "test.number", position) {
  const id = useEditorStore.getState().addNode(schemaId, position);
  if (!id) throw new Error(`Could not add ${schemaId}`);
  return id;
}

/** @param {string} id @param {string} source @param {string} target @returns {import("../src/types").EditorEdge} */
function edge(id, source, target) {
  return { id, source, target, sourceHandle: "value", targetHandle: "value", type: "midgard" };
}

/** @template T @param {T | null | undefined} value @returns {T} */
function required(value) {
  if (value == null) throw new Error("Expected test value");
  return value;
}
beforeEach(() =>
  useEditorStore.setState({
    nodes: [],
    edges: [],
    groups: [],
    selectedGroupId: null,
    past: [],
    future: [],
    definitions: [definition],
    dirty: false,
  }),
);
test("graph edits are undoable", () => {
  addNode("test.number", { x: 1, y: 2 });
  expect(useEditorStore.getState().nodes).toHaveLength(1);
  useEditorStore.getState().undo();
  expect(useEditorStore.getState().nodes).toHaveLength(0);
  useEditorStore.getState().redo();
  expect(useEditorStore.getState().nodes).toHaveLength(1);
});
test("serialization never copies backend definitions", () => {
  addNode();
  const document = useEditorStore.getState().serialize();
  expect(required(document.nodes[0]).schemaId).toBe("test.number");
  expect(required(document.nodes[0])).not.toHaveProperty("definition");
});
test("downstream flow selection stops at each connected end", () => {
  const edges = [
    { source: "a", target: "b" },
    { source: "b", target: "c" },
    { source: "a", target: "d" },
    { source: "x", target: "y" },
  ];
  expect(new Set(downstreamNodeIds(["a"], edges))).toEqual(
    new Set(["a", "b", "c", "d"]),
  );
});
test("flow boxes and node appearance are saved with the workflow", () => {
  const first = addNode("test.number", { x: 10, y: 20 });
  const second = addNode("test.number", { x: 320, y: 20 });
  useEditorStore.setState((state) => ({
    nodes: state.nodes.map((node) => ({
      ...node,
      selected: node.id === first,
    })),
    edges: [edge("edge", first, second)],
  }));
  useEditorStore
    .getState()
    .updateNode(first, {
      appearance: {
        cardStyle: "visual",
        imageEffect: "vivid",
        showPreview: true,
      },
    });
  const groupId = useEditorStore.getState().createFlowFromSelected();
  const document = useEditorStore.getState().serialize();
  expect(
    required(document.nodes.find((node) => node.id === first)).appearance?.imageEffect,
  ).toBe("vivid");
  expect(required(document.groups.find((group) => group.id === groupId)).nodeIds).toEqual(
    [first, second],
  );
  expect(
    required(document.groups.find((group) => group.id === groupId)).startNodeIds,
  ).toEqual([first]);
});
test("flow boxes follow new downstream connections", () => {
  const first = addNode();
  const second = addNode();
  const third = addNode();
  useEditorStore.setState((state) => ({
    nodes: state.nodes.map((node) => ({
      ...node,
      selected: node.id === first,
    })),
    edges: [edge("one", first, second)],
  }));
  const groupId = useEditorStore.getState().createFlowFromSelected();
  useEditorStore
    .getState()
    .connect({
      source: second,
      sourceHandle: "value",
      target: third,
      targetHandle: "value",
    });
  expect(
    required(useEditorStore.getState().groups.find((group) => group.id === groupId)).nodeIds,
  ).toEqual([first, second, third]);
});
test("a processor cannot repeat along the same linked path", () => {
  const remove = /** @type {import("../src/types").NodeDefinition} */ ({
    ...definition,
    schemaId: "test.remove-background",
    name: "Remove Background",
    kind: "processor",
  });
  const upscale = /** @type {import("../src/types").NodeDefinition} */ ({
    ...definition,
    schemaId: "test.upscale",
    name: "Upscale",
    kind: "processor",
  });
  useEditorStore.getState().setDefinitions([definition, remove, upscale]);
  const firstRemove = addNode(remove.schemaId);
  const scale = addNode(upscale.schemaId);
  const secondRemove = addNode(remove.schemaId);
  expect(
    useEditorStore.getState().connect({
      source: firstRemove,
      sourceHandle: "value",
      target: scale,
      targetHandle: "value",
    }).valid,
  ).toBe(true);
  const repeated = useEditorStore.getState().connect({
    source: scale,
    sourceHandle: "value",
    target: secondRemove,
    targetHandle: "value",
  });
  expect(repeated.valid).toBe(false);
  expect(repeated.reason).toBe(
    "Remove Background already exists in this linked path.",
  );
  expect(useEditorStore.getState().edges).toHaveLength(1);
});
test("unlinking a connection removes only that edge and refreshes its parent flow", () => {
  const first = addNode();
  const second = addNode();
  const third = addNode();
  useEditorStore.setState((state) => ({
    nodes: state.nodes.map((node) => ({
      ...node,
      selected: node.id === first,
    })),
    edges: [edge("remove-me", first, second), edge("keep-me", second, third)],
  }));
  const groupId = useEditorStore.getState().createFlowFromSelected();
  useEditorStore.getState().removeEdge("remove-me");
  const state = useEditorStore.getState();
  expect(state.edges.map((edge) => edge.id)).toEqual(["keep-me"]);
  expect(required(state.groups.find((group) => group.id === groupId)).nodeIds).toEqual([
    first,
  ]);
});
test("completed node artifacts survive workflow save and load", () => {
  const id = addNode();
  useEditorStore
    .getState()
    .recordNodeResult(id, {
      status: "SUCCEEDED",
      artifactIds: ["artifact-1"],
      completedAt: "2026-08-03T12:00:00Z",
    });
  const document = useEditorStore.getState().serialize();
  useEditorStore.getState().loadWorkflow(document, [definition]);
  expect(required(useEditorStore.getState().nodes[0]).data.result?.artifactIds).toEqual([
    "artifact-1",
  ]);
});
test("changing a node model preserves history and marks its output stale", () => {
  const id = addNode();
  useEditorStore.getState().recordNodeResult(id, {
    status: "SUCCEEDED",
    artifactIds: ["artifact-1"],
  });
  useEditorStore.getState().setNodeModel(id, "model-b");
  const changed = required(useEditorStore.getState().nodes[0]);
  expect(changed.data.parameters.model).toBe("model-b");
  expect(changed.data.result?.status).toBe("STALE");
  expect(changed.data.result?.artifactIds).toEqual(["artifact-1"]);
});
test("primitive value nodes stay out of the creation catalog", () => {
  expect(isVisibleCatalogNode({ schemaId: "midgard.input.boolean" })).toBe(
    false,
  );
  expect(isVisibleCatalogNode({ schemaId: "midgard.input.integer" })).toBe(
    false,
  );
  expect(isVisibleCatalogNode({ schemaId: "midgard.input.number" })).toBe(
    false,
  );
  expect(isVisibleCatalogNode({ schemaId: "midgard.input.prompt" })).toBe(true);
  expect(isVisibleCatalogNode({ schemaId: "midgard.image.generate" })).toBe(
    true,
  );
});
test("legacy bypass state is discarded when a workflow is loaded", () => {
  const document = /** @type {any} */ ({
    format: "midgard-workflow",
    version: 1,
    projectId: "project",
    name: "Legacy",
    nodes: [
      {
        id: "legacy",
        schemaId: "test.number",
        schemaVersion: 1,
        position: { x: 0, y: 0 },
        parameters: { value: 2 },
        bypass: true,
      },
    ],
    edges: [],
    groups: [],
  });
  useEditorStore.getState().loadWorkflow(document, [definition]);
  expect(required(useEditorStore.getState().nodes[0]).data).not.toHaveProperty("bypass");
  expect(required(useEditorStore.getState().serialize().nodes[0])).not.toHaveProperty(
    "bypass",
  );
});
