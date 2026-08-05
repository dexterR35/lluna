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
test("SUPIR LLaVA toggle adds and removes its companion node", () => {
  const upscale = /** @type {import("../src/types").NodeDefinition} */ ({
    ...definition,
    schemaId: "midgard.image.upscale",
    name: "Upscale Image",
    parameters: [
      {
        id: "model",
        label: "Model",
        type: "model",
        default: "RealESRGAN_x2plus",
      },
      {
        id: "useLlava",
        label: "Automatic LLaVA caption",
        type: "boolean",
        default: true,
      },
    ],
    inputs: [
      { id: "image", label: "Image", type: "IMAGE" },
      { id: "llava", label: "LLaVA settings", type: "MODEL" },
    ],
  });
  const llava = /** @type {import("../src/types").NodeDefinition} */ ({
    ...definition,
    schemaId: "midgard.input.llava",
    name: "LLaVA Caption",
    kind: "input",
    parameters: [
      { id: "temperature", label: "Temperature", type: "number", default: 0.2 },
    ],
    inputs: [],
    outputs: [{ id: "config", label: "LLaVA settings", type: "MODEL" }],
  });
  useEditorStore.getState().setDefinitions([upscale, llava]);
  const upscaleId = addNode(upscale.schemaId, { x: 500, y: 100 });

  useEditorStore.getState().setNodeModel(upscaleId, "SUPIR");
  let state = useEditorStore.getState();
  const llavaNode = required(
    state.nodes.find((node) => node.data.schemaId === llava.schemaId),
  );
  expect(llavaNode.position).toEqual({ x: 180, y: 132 });
  expect(state.edges).toContainEqual(
    expect.objectContaining({
      source: llavaNode.id,
      sourceHandle: "config",
      target: upscaleId,
      targetHandle: "llava",
    }),
  );

  const upscaleNode = required(state.nodes.find((node) => node.id === upscaleId));
  useEditorStore.getState().updateNode(upscaleId, {
    parameters: { ...upscaleNode.data.parameters, useLlava: false },
  });
  state = useEditorStore.getState();
  expect(
    state.nodes.some((node) => node.data.schemaId === llava.schemaId),
  ).toBe(false);
  expect(state.edges.some((item) => item.targetHandle === "llava")).toBe(false);

  const disabledUpscale = required(
    state.nodes.find((node) => node.id === upscaleId),
  );
  useEditorStore.getState().updateNode(upscaleId, {
    parameters: { ...disabledUpscale.data.parameters, useLlava: true },
  });
  expect(
    useEditorStore
      .getState()
      .nodes.some((node) => node.data.schemaId === llava.schemaId),
  ).toBe(true);

  useEditorStore.getState().setNodeModel(upscaleId, "RealESRGAN_x2plus");
  expect(
    useEditorStore
      .getState()
      .nodes.some((node) => node.data.schemaId === llava.schemaId),
  ).toBe(false);
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
test("known image queues connect only to batch-capable inputs", () => {
  const batchInput = /** @type {import("../src/types").NodeDefinition} */ ({
    ...definition,
    schemaId: "test.images",
    name: "Load Images",
    kind: "input",
    inputs: [],
    outputs: [{ id: "images", label: "Images", type: "IMAGE", multiple: true }],
  });
  const processor = /** @type {import("../src/types").NodeDefinition} */ ({
    ...definition,
    schemaId: "test.batch-processor",
    name: "Batch Processor",
    kind: "processor",
    inputs: [{ id: "image", label: "Images", type: "IMAGE", multiple: true }],
    outputs: [{ id: "image", label: "Images", type: "IMAGE", multiple: true }],
  });
  const scalarOutput = /** @type {import("../src/types").NodeDefinition} */ ({
    ...definition,
    schemaId: "test.scalar-output",
    name: "Single Save",
    kind: "output",
    inputs: [{ id: "image", label: "Image", type: "IMAGE" }],
    outputs: [],
  });
  useEditorStore
    .getState()
    .setDefinitions([batchInput, processor, scalarOutput]);
  const source = addNode(batchInput.schemaId);
  const process = addNode(processor.schemaId);
  const save = addNode(scalarOutput.schemaId);
  expect(
    useEditorStore.getState().connect({
      source,
      sourceHandle: "images",
      target: process,
      targetHandle: "image",
    }).valid,
  ).toBe(true);
  const invalid = useEditorStore.getState().connect({
    source: process,
    sourceHandle: "image",
    target: save,
    targetHandle: "image",
  });
  expect(invalid.valid).toBe(false);
  expect(invalid.reason).toContain("accepts one item");
});
test("one multiple input handle accepts several typed connections", () => {
  const imageInput = /** @type {import("../src/types").NodeDefinition} */ ({
    ...definition,
    schemaId: "test.image",
    name: "Image",
    kind: "input",
    inputs: [],
    outputs: [{ id: "image", label: "Image", type: "IMAGE" }],
  });
  const batchTarget = /** @type {import("../src/types").NodeDefinition} */ ({
    ...definition,
    schemaId: "test.batch-target",
    name: "Image Queue",
    kind: "output",
    inputs: [
      { id: "images", label: "Images", type: "IMAGE", multiple: true },
    ],
    outputs: [],
  });
  useEditorStore.getState().setDefinitions([imageInput, batchTarget]);
  const first = addNode(imageInput.schemaId);
  const second = addNode(imageInput.schemaId);
  const target = addNode(batchTarget.schemaId);

  for (const source of [first, second]) {
    expect(
      useEditorStore.getState().connect({
        source,
        sourceHandle: "image",
        target,
        targetHandle: "images",
      }).valid,
    ).toBe(true);
  }

  expect(useEditorStore.getState().edges).toHaveLength(2);
  expect(useEditorStore.getState().edges.every((item) => item.data?.portType === "IMAGE"))
    .toBe(true);
});
test("creating a flow with overlap expands the existing flow instead of nesting", () => {
  const first = addNode("test.number", { x: 10, y: 20 });
  const second = addNode("test.number", { x: 320, y: 20 });
  const third = addNode("test.number", { x: 630, y: 20 });
  useEditorStore.setState((state) => ({
    nodes: state.nodes.map((node) => ({
      ...node,
      selected: node.id === first,
    })),
    edges: [edge("one", first, second)],
  }));
  const groupId = useEditorStore.getState().createFlowFromSelected();
  expect(useEditorStore.getState().groups).toHaveLength(1);
  useEditorStore.setState((state) => ({
    nodes: state.nodes.map((node) => ({
      ...node,
      selected: [first, second, third].includes(node.id),
    })),
  }));
  const sameId = useEditorStore.getState().createFlowFromSelected();
  const state = useEditorStore.getState();
  expect(sameId).toBe(groupId);
  expect(state.groups).toHaveLength(1);
  expect(required(state.groups[0]).nodeIds).toEqual(
    expect.arrayContaining([first, second, third]),
  );
  expect(required(state.groups[0]).startNodeIds).toEqual(
    expect.arrayContaining([first, third]),
  );
});
test("dropping a node into a flow adds it to that flow", () => {
  const first = addNode("test.number", { x: 100, y: 100 });
  const second = addNode("test.number", { x: 400, y: 100 });
  useEditorStore.setState((state) => ({
    nodes: state.nodes.map((node) => ({
      ...node,
      selected: node.id === first,
    })),
    edges: [edge("one", first, second)],
  }));
  const groupId = required(
    useEditorStore.getState().createFlowFromSelected(),
  );
  const third = useEditorStore
    .getState()
    .addNode("test.number", { x: 200, y: 120 }, { flowId: groupId });
  expect(third).toBeTruthy();
  const group = required(
    useEditorStore.getState().groups.find((item) => item.id === groupId),
  );
  expect(group.nodeIds).toEqual(expect.arrayContaining([first, second, third]));
  expect(group.startNodeIds).toEqual(expect.arrayContaining([first, third]));
});
test("dragging a flow header moves every node in that flow", () => {
  const first = addNode("test.number", { x: 100, y: 100 });
  const second = addNode("test.number", { x: 400, y: 140 });
  const outsider = addNode("test.number", { x: 20, y: 20 });
  useEditorStore.setState((state) => ({
    nodes: state.nodes.map((node) => ({
      ...node,
      selected: node.id === first,
    })),
    edges: [edge("one", first, second)],
  }));
  const groupId = required(useEditorStore.getState().createFlowFromSelected());
  useEditorStore.getState().moveFlowBy(groupId, { x: 48, y: -16 });
  const state = useEditorStore.getState();
  expect(required(state.nodes.find((node) => node.id === first)).position).toEqual({
    x: 148,
    y: 84,
  });
  expect(required(state.nodes.find((node) => node.id === second)).position).toEqual({
    x: 448,
    y: 124,
  });
  expect(
    required(state.nodes.find((node) => node.id === outsider)).position,
  ).toEqual({ x: 20, y: 20 });
  expect(state.dirty).toBe(true);
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
  expect(isVisibleCatalogNode({ schemaId: "midgard.input.llava" })).toBe(
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
