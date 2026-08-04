import { expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReactFlowProvider } from "@xyflow/react";
import { Dialog, ProgressBar, Switch } from "../src/components";
import { MidgardNode } from "../src/nodes/MidgardNode";
import { NodeParameterField } from "../src/nodes/NodeParameterField";
import { enabledModelOptions } from "../src/models/modelAvailability";
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
  const previousDesktop = window.midgardDesktop;
  window.midgardDesktop = /** @type {any} */ ({ registerDroppedFiles });
  const onChange = vi.fn();
  render(
    <NodeParameterField
      definition={{ id: "pathGrantId", label: "Image file", type: "file" }}
      nodeDefinition={{ schemaId: "midgard.input.image" }}
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
  window.midgardDesktop = previousDesktop;
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
      <MidgardNode
        id="node-1"
        type="midgard"
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
          modelInventory: /** @type {any} */ ([
            { id: "model-a", installed: true, enabled: false },
            { id: "model-b", installed: true, enabled: true },
          ]),
          nodeActions: { onModelChange },
        }}
      />
    </ReactFlowProvider>,
  );
  const selector = screen.getByRole("combobox", { name: "Model for Generate" });
  expect(selector.closest("header")).toBeNull();
  expect(selector.closest(".midgard-node")).not.toBeNull();
  expect(screen.getByRole("option", { name: "Model B" })).toBeEnabled();
  await user.selectOptions(selector, "b");
  expect(onModelChange).toHaveBeenCalledWith("node-1", "b");
});
