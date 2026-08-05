import { describe, expect, it } from "vitest";
import {
  applyCapabilityDefaults,
  parametersForCapabilities,
} from "../src/models/modelCapabilities";
import { capabilityIssues } from "../src/models/modelManifestCapabilities";

const parameters = [
  { id: "width", label: "Width", type: "integer", capability: "width" },
  { id: "steps", label: "Steps", type: "integer", capability: "steps" },
  { id: "guidance", label: "Guidance", type: "number", capability: "guidance" },
  { id: "negativePrompt", label: "Negative prompt", type: "textarea", capability: "negativePrompt" },
  { id: "seed", label: "Seed", type: "integer", capability: "seed" },
];

const distilled = {
  complete: true,
  supportedWidths: [512, 768],
  steps: { default: 4, minimum: 4, maximum: 4, values: [4] },
  guidance: false,
  negativePrompt: false,
  seed: true,
};

describe("model capability projection", () => {
  it("hides unsupported distilled controls and projects reviewed values", () => {
    const projected = parametersForCapabilities(parameters, distilled);
    expect(projected.map((item) => item.id)).toEqual(["width", "steps", "seed"]);
    expect(projected.find((item) => item.id === "steps")?.options).toEqual([
      { value: 4, label: "4" },
    ]);
  });

  it("clears stale base-model values when switching to distilled", () => {
    const values = applyCapabilityDefaults(
      { guidance: 7, negativePrompt: "noise", steps: 50 },
      distilled,
      "distilled",
    );
    expect(values).toEqual({ model: "distilled", width: 512, steps: 4, seed: -1 });
  });

  it("keeps incomplete manifests in configuration", () => {
    expect(
      capabilityIssues({
        task: "text-to-image",
        variant: { kind: "unknown" },
        capabilities: { provenance: "huggingface-metadata", tasks: ["text-to-image"], inputs: ["prompt"], outputs: ["image"] },
      }),
    ).toContain("variant");
  });

  it("shows professional controls only for their selected model", () => {
    const modelSpecific = [
      { id: "model", label: "Model", type: "model" },
      {
        id: "denoise",
        label: "Denoise",
        type: "boolean",
        visibleForModels: ["RealESRGAN_x2plus", "RealESRGAN_x4plus"],
      },
      {
        id: "supirPreset",
        label: "Quality · more detail",
        type: "select",
        visibleForModels: ["SUPIR"],
        options: [{ value: "quality", label: "Quality · more detail" }],
      },
      {
        id: "colorFixType",
        label: "Wavelet",
        type: "select",
        visibleForModels: ["SUPIR"],
        options: [{ value: "Wavelet", label: "Wavelet" }],
      },
      {
        id: "diffDtype",
        label: "FP32",
        type: "select",
        visibleForModels: ["SUPIR"],
        options: [{ value: "fp32", label: "FP32" }],
      },
    ];
    expect(
      parametersForCapabilities(modelSpecific, { complete: true }, "SUPIR").map(
        (item) => item.id,
      ),
    ).toEqual(["model", "supirPreset", "colorFixType", "diffDtype"]);
    expect(
      parametersForCapabilities(
        modelSpecific,
        { complete: true },
        "RealESRGAN_x2plus",
      ).map((item) => item.id),
    ).toEqual(["model", "denoise"]);
  });
});
