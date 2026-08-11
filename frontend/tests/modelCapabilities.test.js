import { describe, expect, it } from "vitest";
import {
  applyCapabilityDefaults,
  parametersForCapabilities,
} from "../src/models/modelCapabilities";

/**
 * @param {import("../src/types").ParameterDefinition | undefined} parameter
 * @returns {(string | number)[]}
 */
function optionValues(parameter) {
  if (!parameter?.options) throw new Error("Expected the parameter to declare options");
  return parameter.options.map((option) => option.value);
}

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

  it("filters dtype options to what the model declares, always keeping auto", () => {
    const dtypeParameters = [
      {
        id: "dtype",
        label: "Precision",
        type: "select",
        capability: "dtype",
        default: "auto",
        options: [
          { value: "auto", label: "Auto" },
          { value: "bf16", label: "BF16" },
          { value: "fp16", label: "FP16" },
          { value: "fp32", label: "FP32" },
          { value: "fp8", label: "FP8" },
        ],
      },
    ];
    const projected = parametersForCapabilities(dtypeParameters, {
      complete: true,
      dtypes: ["bf16", "fp16"],
    });
    expect(optionValues(projected[0])).toEqual(["auto", "bf16", "fp16"]);

    const fp8Only = parametersForCapabilities(dtypeParameters, {
      complete: true,
      dtypes: ["fp8"],
    });
    expect(optionValues(fp8Only[0])).toEqual(["auto", "fp8"]);
  });

  it("hides denoise strength unless the model declares it", () => {
    const editParameters = [
      {
        id: "denoiseStrength",
        label: "Denoise strength",
        type: "number",
        capability: "denoiseStrength",
        default: 0.65,
      },
    ];
    expect(
      parametersForCapabilities(editParameters, { complete: true }),
    ).toEqual([]);
    const projected = parametersForCapabilities(editParameters, {
      complete: true,
      denoiseStrength: { default: 0.5, minimum: 0.1, maximum: 1 },
    });
    expect(projected[0]).toMatchObject({ default: 0.5, minimum: 0.1, maximum: 1 });
  });

  it("clears stale base-model values when switching to distilled", () => {
    const values = applyCapabilityDefaults(
      { guidance: 7, negativePrompt: "noise", steps: 50 },
      distilled,
      "distilled",
    );
    expect(values).toEqual({ model: "distilled", width: 512, steps: 4, seed: -1 });
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

  it("shows temperature/top-p/max-tokens only when the model declares them", () => {
    const describeParameters = [
      { id: "model", label: "Model", type: "model" },
      { id: "instruction", label: "Instruction", type: "textarea" },
      {
        id: "temperature",
        label: "Temperature",
        type: "number",
        capability: "temperature",
        default: 0.2,
        minimum: 0,
        maximum: 1,
      },
      {
        id: "topP",
        label: "Top-p",
        type: "number",
        capability: "topP",
        default: 0.7,
        minimum: 0,
        maximum: 1,
      },
      {
        id: "maxNewTokens",
        label: "Max length",
        type: "integer",
        capability: "maxNewTokens",
        default: 200,
        minimum: 1,
        maximum: 2000,
      },
    ];
    const captioner = {
      // Deliberately omit `complete` - these settings aren't gated by the
      // generation-completeness contract the way width/steps/guidance are.
      temperature: { default: 0.5, minimum: 0, maximum: 1 },
      topP: { default: 0.9, minimum: 0, maximum: 1 },
      maxNewTokens: { default: 300, minimum: 1, maximum: 4000 },
    };
    const projected = parametersForCapabilities(describeParameters, captioner);
    expect(projected.map((item) => item.id)).toEqual([
      "model",
      "instruction",
      "temperature",
      "topP",
      "maxNewTokens",
    ]);
    expect(projected.find((item) => item.id === "temperature")).toMatchObject({
      default: 0.5,
      minimum: 0,
      maximum: 1,
    });
    expect(projected.find((item) => item.id === "maxNewTokens")).toMatchObject({
      default: 300,
      maximum: 4000,
    });

    const withoutSampling = parametersForCapabilities(describeParameters, {});
    expect(withoutSampling.map((item) => item.id)).toEqual(["model", "instruction"]);
  });

  it("applies temperature/top-p/max-tokens/instruction defaults for the selected model", () => {
    const values = applyCapabilityDefaults(
      { temperature: 0.9 },
      {
        temperature: { default: 0.4, minimum: 0, maximum: 1 },
        topP: { default: 0.6, minimum: 0, maximum: 1 },
        maxNewTokens: { default: 150, minimum: 1, maximum: 1000 },
        defaultInstruction: "Describe the scene.",
      },
      "custom:captioner",
    );
    expect(values).toEqual({
      model: "custom:captioner",
      temperature: 0.4,
      topP: 0.6,
      maxNewTokens: 150,
      instruction: "Describe the scene.",
    });
  });
});
