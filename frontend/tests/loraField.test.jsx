import { expect, test } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NodeParameterField } from "../src/nodes/NodeParameterField";

const definition = {
  id: "loras",
  label: "LoRAs",
  type: "lora-list",
  default: [],
  description: "Adapters composed onto the model above.",
  options: [
    { value: "custom:style", label: "Style LoRA" },
    { value: "custom:subject", label: "Subject LoRA" },
  ],
};

/** @param {{value?: unknown, onChange?: (next: unknown) => void}} props */
function field({ value = [], onChange = () => {} }) {
  return render(
    <NodeParameterField
      definition={definition}
      value={value}
      onChange={onChange}
    />,
  );
}

test("explains how to get LoRAs when none are installed", () => {
  render(
    <NodeParameterField
      definition={{ ...definition, options: [] }}
      value={[]}
      onChange={() => {}}
    />,
  );
  expect(screen.getByText(/Settings → Models/)).toBeTruthy();
});

test("adding a LoRA starts it at full weight", async () => {
  const user = userEvent.setup();
  let next = null;
  field({ onChange: (value) => (next = value) });

  await user.click(screen.getByRole("button", { name: /Add LoRA/i }));

  expect(next).toEqual([{ modelId: "custom:style", weight: 1 }]);
});

test("several LoRAs stack, each with its own weight", async () => {
  const user = userEvent.setup();
  let next = null;
  field({
    value: [{ modelId: "custom:style", weight: 0.8 }],
    onChange: (value) => (next = value),
  });

  await user.click(screen.getByRole("button", { name: /Add LoRA/i }));

  expect(next).toEqual([
    { modelId: "custom:style", weight: 0.8 },
    { modelId: "custom:subject", weight: 1 },
  ]);
});

test("a row offers its own LoRA plus the unused ones, never another row's", () => {
  field({
    value: [
      { modelId: "custom:style", weight: 1 },
      { modelId: "custom:subject", weight: 1 },
    ],
  });

  const [first, second] = screen.getAllByRole("combobox", { name: /LoRA/i });
  /** @param {Element} select */
  const valuesOf = (select) =>
    [...select.querySelectorAll("option")].map((option) => option.value);

  // Each row can switch to itself, but not to the one the other row holds.
  expect(valuesOf(first)).toEqual(["custom:style"]);
  expect(valuesOf(second)).toEqual(["custom:subject"]);
});

test("the add button disappears once every LoRA is in use", () => {
  field({
    value: [
      { modelId: "custom:style", weight: 1 },
      { modelId: "custom:subject", weight: 1 },
    ],
  });

  expect(screen.queryByRole("button", { name: /Add LoRA/i })).toBeNull();
});

test("weight edits are reported for the right row", () => {
  /** @type {{modelId: string, weight: number}[]} */
  let next = [];
  field({
    value: [
      { modelId: "custom:style", weight: 1 },
      { modelId: "custom:subject", weight: 1 },
    ],
    onChange: (value) => {
      next = /** @type {{modelId: string, weight: number}[]} */ (value);
    },
  });

  const weights = screen.getAllByRole("spinbutton", { name: /Weight/i });
  fireEvent.change(weights[1], { target: { value: "0.5" } });

  expect(next[0].weight).toBe(1);
  expect(next[1]).toEqual({ modelId: "custom:subject", weight: 0.5 });
});

test("removing a row drops only that row", async () => {
  const user = userEvent.setup();
  let next = null;
  field({
    value: [
      { modelId: "custom:style", weight: 1 },
      { modelId: "custom:subject", weight: 0.4 },
    ],
    onChange: (value) => (next = value),
  });

  await user.click(screen.getAllByRole("button", { name: /Remove/i })[0]);

  expect(next).toEqual([{ modelId: "custom:subject", weight: 0.4 }]);
});
