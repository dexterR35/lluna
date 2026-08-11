import { expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReactFlowProvider } from "@xyflow/react";
import { Dialog, ProgressBar, Switch } from "../src/components";
import { LlunaNode } from "../src/nodes/LlunaNode";
import { NodeActionsProvider } from "../src/nodes/NodeActionsContext";
import { NodeParameterField } from "../src/nodes/NodeParameterField";
import { enabledModelOptions } from "../src/models/modelAvailability";
import { NodeLibrary } from "../src/workflow/NodeLibrary";
import { useDesktopStore } from "../src/state/desktopStore";
import { useEditorStore } from "../src/state/editorStore";
test("switch is keyboard operable and reports state", async () => {
  const user = userEvent.setup();
  let value = false;
  const { rerender } = render(
    <Switch
      label="Show previews"
      checked={value}
      onChange={(next) => {
        value = next;
      }}
    />,
  );
  const control = screen.getByRole("switch", { name: "Show previews" });
  await user.click(control);
  expect(value).toBe(true);
  rerender(<Switch label="Show previews" checked={value} />);
  expect(control).toHaveAttribute("aria-checked", "true");
});
test("dialog closes with escape", async () => {
  const user = userEvent.setup();
  let closed = false;
  render(
    <Dialog
      open
      title="Settings"
      onClose={() => {
        closed = true;
      }}
    >
      <button>Focusable</button>
    </Dialog>,
  );
  await user.keyboard("{Escape}");
  expect(closed).toBe(true);
});
test("progress bar distinguishes unknown progress from zero percent", () => {
  const { rerender } = render(
    <ProgressBar value={null} label="Preparing model" showLabel />,
  );
  const progress = screen.getByRole("progressbar", {
    name: "Preparing model",
  });
  expect(progress).not.toHaveAttribute("aria-valuenow");
  expect(screen.getByText("Working…")).toBeInTheDocument();

  rerender(<ProgressBar value={0} label="Downloading model" showLabel />);
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  expect(screen.getByText("0%")).toBeInTheDocument();
});
test("image parameter accepts a dropped file and returns its preview artifact", async () => {
  const registerDroppedFiles = vi
    .fn()
    .mockResolvedValue([
      {
        grantId: "grant-1",
        artifactId: "artifact-1",
        name: "portrait.png",
        mediaType: "image/png",
      },
    ]);
  const previousDesktop = window.llunaDesktop;
  window.llunaDesktop = /** @type {any} */ ({ registerDroppedFiles });
  const onChange = vi.fn();
  render(
    <NodeParameterField
      definition={{ id: "pathGrantId", label: "Image file", type: "file" }}
      nodeDefinition={{ schemaId: "lluna.input.image" }}
      onChange={onChange}
    />,
  );
  const file = new File(["image"], "portrait.png", { type: "image/png" });
  fireEvent.drop(screen.getByRole("button", { name: "Drop image file" }), {
    dataTransfer: { files: [file] },
  });
  await waitFor(() =>
    expect(onChange).toHaveBeenCalledWith(
      "grant-1",
      expect.objectContaining({
        artifactId: "artifact-1",
        name: "portrait.png",
      }),
    ),
  );
  expect(registerDroppedFiles).toHaveBeenCalledWith([file]);
  window.llunaDesktop = previousDesktop;
});
test("multi-image parameter preserves the dropped file order", async () => {
  const registerDroppedFiles = vi.fn().mockResolvedValue([
    {
      grantId: "grant-1",
      artifactId: "artifact-1",
      name: "first.png",
      mediaType: "image/png",
    },
    {
      grantId: "grant-2",
      artifactId: "artifact-2",
      name: "second.png",
      mediaType: "image/png",
    },
  ]);
  const previousDesktop = window.llunaDesktop;
  window.llunaDesktop = /** @type {any} */ ({ registerDroppedFiles });
  const onChange = vi.fn();
  render(
    <NodeParameterField
      definition={{ id: "pathGrantIds", label: "Images", type: "files" }}
      nodeDefinition={{ schemaId: "lluna.input.images" }}
      onChange={onChange}
    />,
  );
  const first = new File(["first"], "first.png", { type: "image/png" });
  const second = new File(["second"], "second.png", { type: "image/png" });
  fireEvent.drop(screen.getByRole("button", { name: "Drop image files" }), {
    dataTransfer: { files: [first, second] },
  });
  await waitFor(() =>
    expect(onChange).toHaveBeenCalledWith(
      ["grant-1", "grant-2"],
      expect.arrayContaining([
        expect.objectContaining({ artifactId: "artifact-1" }),
        expect.objectContaining({ artifactId: "artifact-2" }),
      ]),
    ),
  );
  expect(registerDroppedFiles).toHaveBeenCalledWith([first, second]);
  window.llunaDesktop = previousDesktop;
});
test("node selectors include only installed and enabled models", () => {
  const options = [
    { value: "a", label: "A", modelId: "model-a" },
    { value: "b", label: "B", modelId: "model-b" },
    { value: "c", label: "C", modelId: "model-c" },
  ];
  const models = /** @type {any} */ ([
    { id: "model-a", installed: true, enabled: true },
    { id: "model-b", installed: true, enabled: false },
    { id: "model-c", installed: false, enabled: true },
  ]);
  expect(enabledModelOptions(options, models).map((option) => option.value)).toEqual(["a"]);
});

test("model selection is in the node body and reacts to enabled inventory", async () => {
  const user = userEvent.setup();
  const onModelChange = vi.fn();
  const definition = /** @type {any} */ ({
    schemaId: "test.generate",
    schemaVersion: 1,
    name: "Generate",
    category: "Image/Generate",
    inputs: [{ id: "prompt", label: "Prompt", type: "PROMPT" }],
    outputs: [{ id: "image", label: "Image", type: "IMAGE" }],
    parameters: [
      {
        id: "model",
        label: "Model",
        type: "model",
        default: "a",
        options: [
          { value: "a", label: "Model A", modelId: "model-a" },
          { value: "b", label: "Model B", modelId: "model-b" },
        ],
      },
    ],
  });
  render(
    <ReactFlowProvider>
      <NodeActionsProvider
        value={{
          actions: { onModelChange },
          modelInventory: /** @type {any} */ ([
            { id: "model-a", installed: true, enabled: false },
            { id: "model-b", installed: true, enabled: true },
          ]),
        }}
      >
        <LlunaNode
          id="node-1"
          type="lluna"
          draggable
          dragging={false}
          selectable
          deletable
          zIndex={0}
          isConnectable
          positionAbsoluteX={0}
          positionAbsoluteY={0}
          selected={false}
          data={{
            schemaId: definition.schemaId,
            schemaVersion: 1,
            label: "Generate",
            definition,
            parameters: { model: "a" },
            appearance: { cardStyle: "visual", showPreview: false },
          }}
        />
      </NodeActionsProvider>
    </ReactFlowProvider>,
  );
  const selector = screen.getByRole("combobox", { name: "Model for Generate" });
  expect(selector.closest("header")).toBeNull();
  expect(selector.closest(".lluna-node")).not.toBeNull();
  expect(screen.getByRole("option", { name: "Model B" })).toBeEnabled();
  await user.selectOptions(selector, "b");
  expect(onModelChange).toHaveBeenCalledWith("node-1", "b");
});

test("generate image nodes expose model-supported steps in the toolbar", async () => {
  const user = userEvent.setup();
  const onParameterChange = vi.fn();
  const definition = /** @type {any} */ ({
    schemaId: "lluna.generate.image",
    schemaVersion: 1,
    name: "Generate Image",
    category: "Image/Generate",
    inputs: [{ id: "prompt", label: "Prompt", type: "PROMPT" }],
    outputs: [{ id: "image", label: "Image", type: "IMAGE" }],
    parameters: [
      {
        id: "model",
        label: "Model",
        type: "model",
        default: "flux-base-4b",
        options: [
          {
            value: "flux-base-4b",
            label: "FLUX.2 Klein Base 4B",
            modelId: "flux-base-4b",
            capabilities: {
              complete: true,
              steps: { default: 50, minimum: 20, maximum: 50 },
            },
          },
        ],
      },
      {
        id: "steps",
        label: "Steps",
        type: "integer",
        default: 4,
        minimum: 1,
        maximum: 250,
        capability: "steps",
      },
    ],
  });
  render(
    <ReactFlowProvider>
      <NodeActionsProvider
        value={{
          actions: { onParameterChange },
          modelInventory: /** @type {any} */ ([
            { id: "flux-base-4b", installed: true, enabled: true },
          ]),
        }}
      >
        <LlunaNode
          id="node-steps"
          type="lluna"
          draggable
          dragging={false}
          selectable
          deletable
          zIndex={0}
          isConnectable
          positionAbsoluteX={0}
          positionAbsoluteY={0}
          selected={false}
          data={{
            schemaId: definition.schemaId,
            schemaVersion: 1,
            label: "Generate Image",
            definition,
            parameters: { model: "flux-base-4b", steps: 4 },
            appearance: { cardStyle: "visual", showPreview: false },
          }}
        />
      </NodeActionsProvider>
    </ReactFlowProvider>,
  );

  const selector = screen.getByRole("combobox", { name: "Steps" });
  expect(
    screen.getByRole("option", { name: "4 steps (unsupported)" }),
  ).toBeDisabled();
  expect(screen.getByRole("option", { name: "20 steps" })).toBeEnabled();
  expect(screen.getByRole("option", { name: "50 steps" })).toBeEnabled();

  await user.selectOptions(selector, "20");
  expect(onParameterChange).toHaveBeenCalledWith("node-steps", "steps", 20);
});

test("library nodes use shared icons and can only be added by dragging", () => {
  useDesktopStore.setState({ libraryCollapsed: false });
  useEditorStore.setState({
    definitions: [
      {
        schemaId: "test.image",
        schemaVersion: 1,
        name: "Image Tool",
        category: "Image/Test",
        description: "Test image operation",
        icon: "image",
        inputs: [],
        outputs: [],
        parameters: [],
      },
    ],
  });
  const setData = vi.fn();
  render(<NodeLibrary />);

  const label = screen.getByText("Image Tool");
  const item = label.closest("[draggable='true']");
  if (!item) throw new Error("Expected draggable library item");
  expect(item.tagName).toBe("DIV");
  expect(item.querySelector("svg")).not.toBeNull();
  expect(screen.queryByRole("button", { name: "Image Tool" })).toBeNull();

  fireEvent.dragStart(item, { dataTransfer: { setData } });
  expect(setData).toHaveBeenCalledWith(
    "application/x-lluna-node",
    "test.image",
  );
});
