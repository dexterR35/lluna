import { beforeEach, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEditorStore } from "../src/state/editorStore";

/** @type {import("../src/types").NodeDefinition[]} */
const definitions = /** @type {any} */ ([
  {
    schemaId: "lluna.input.image",
    name: "Load Image",
    category: "Input/Media",
    description: "",
    schemaVersion: 1,
    inputs: [],
    outputs: [{ id: "image", label: "Image", type: "IMAGE" }],
    parameters: [],
  },
  {
    schemaId: "lluna.output.save_image",
    name: "Save Image",
    category: "Output",
    description: "",
    schemaVersion: 1,
    inputs: [{ id: "image", label: "Image", type: "IMAGE", required: true }],
    outputs: [],
    parameters: [],
  },
]);

/** @type {import("../src/types").WorkflowDocument} */
const template = /** @type {any} */ ({
  format: "lluna-workflow",
  version: 1,
  name: "Cut out",
  nodes: [
    {
      id: "load",
      schemaId: "lluna.input.image",
      position: { x: 0, y: 0 },
      parameters: {},
    },
    {
      id: "save",
      schemaId: "lluna.output.save_image",
      position: { x: 320, y: 0 },
      parameters: {},
    },
  ],
  edges: [
    {
      sourceNodeId: "load",
      sourcePortId: "image",
      targetNodeId: "save",
      targetPortId: "image",
    },
  ],
});

beforeEach(() => {
  useEditorStore.setState({ nodes: [], edges: [], groups: [], definitions });
});

test("inserting a template adds its nodes and the edge between them", () => {
  useEditorStore.getState().insertTemplate(template);

  const { nodes, edges } = useEditorStore.getState();
  expect(nodes).toHaveLength(2);
  expect(edges).toHaveLength(1);
  const [edge] = edges;
  expect(edge?.source).toBe(nodes[0]?.id);
  expect(edge?.target).toBe(nodes[1]?.id);
  expect(edge?.data?.portType).toBe("IMAGE");
});

test("node ids are regenerated so two inserts cannot collide", () => {
  const store = useEditorStore.getState();
  store.insertTemplate(template);
  store.insertTemplate(template);

  const { nodes, edges } = useEditorStore.getState();
  expect(nodes).toHaveLength(4);
  expect(new Set(nodes.map((node) => node.id)).size).toBe(4);
  expect(edges).toHaveLength(2);
  // Each edge must connect its own copy, not bridge the two inserts.
  for (const edge of edges) {
    expect(edge.source).not.toBe(edge.target);
    expect(nodes.some((node) => node.id === edge.source)).toBe(true);
  }
});

test("a template lands below existing work instead of on top of it", () => {
  useEditorStore.setState({
    nodes: [
      {
        id: "existing",
        type: "lluna",
        position: { x: 0, y: 500 },
        data: /** @type {any} */ ({ schemaId: "lluna.input.image", parameters: {} }),
      },
    ],
    edges: [],
    groups: [],
    definitions,
  });

  useEditorStore.getState().insertTemplate(template);

  const inserted = useEditorStore
    .getState()
    .nodes.filter((node) => node.id !== "existing");
  expect(inserted.every((node) => node.position.y > 500)).toBe(true);
});

test("inserted nodes arrive selected and deselect existing ones", () => {
  useEditorStore.setState({
    nodes: [
      {
        id: "existing",
        type: "lluna",
        position: { x: 0, y: 0 },
        selected: true,
        data: /** @type {any} */ ({ schemaId: "lluna.input.image", parameters: {} }),
      },
    ],
    edges: [],
    groups: [],
    definitions,
  });

  useEditorStore.getState().insertTemplate(template);

  const { nodes } = useEditorStore.getState();
  expect(nodes.find((node) => node.id === "existing")?.selected).toBe(false);
  expect(nodes.filter((node) => node.selected)).toHaveLength(2);
});

test("nodes this build does not know are skipped rather than inserted broken", () => {
  useEditorStore.getState().insertTemplate(/** @type {any} */ ({
    ...template,
    nodes: [
      ...template.nodes,
      {
        id: "future",
        schemaId: "lluna.future.node",
        position: { x: 640, y: 0 },
        parameters: {},
      },
    ],
  }));

  const { nodes } = useEditorStore.getState();
  expect(nodes).toHaveLength(2);
  expect(nodes.every((node) => node.data.definition)).toBe(true);
});

test("an empty template leaves the canvas untouched", () => {
  useEditorStore
    .getState()
    .insertTemplate(/** @type {any} */ ({ nodes: [], edges: [] }));

  expect(useEditorStore.getState().nodes).toHaveLength(0);
});

test("the library offers templates and inserts the one clicked", async () => {
  vi.resetModules();
  vi.doMock("../src/api/client", () => ({
    api: vi.fn(async () => ({
      templates: [
        {
          id: "cutout-transparent",
          name: "Cut out a transparent subject",
          description: "Removes the background.",
          category: "Cut out",
          document: template,
        },
      ],
    })),
    MAX_BATCH_IMAGES: 10,
  }));
  // resetModules gives the component a fresh module graph, so the store it uses
  // is a different instance from the one imported at the top of this file.
  const { NodeLibrary } = await import("../src/workflow/NodeLibrary");
  const { useEditorStore: store } = await import("../src/state/editorStore");
  store.setState({ nodes: [], edges: [], groups: [], definitions });
  const user = userEvent.setup();

  render(<NodeLibrary />);

  const entry = await screen.findByText("Cut out a transparent subject");
  await user.click(entry);

  expect(store.getState().nodes).toHaveLength(2);
});
