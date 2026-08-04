/** @param {Record<string, any>} manifest */
export function capabilityIssues(manifest) {
  const caps = manifest?.capabilities || {};
  const variant = manifest?.variant || {};
  const task = manifest?.task || "custom";
  const issues = [];
  const validRange = (/** @type {Record<string, any> | null | undefined} */ value) => {
    if (!value) return false;
    const minimum = Number(value.minimum), maximum = Number(value.maximum), defaultValue = Number(value.default);
    return [minimum, maximum, defaultValue].every(Number.isFinite) && minimum <= defaultValue && defaultValue <= maximum;
  };
  if (!caps.provenance || caps.provenance === "unknown") issues.push("capability source");
  if (!(caps.tasks || []).includes(task)) issues.push("task confirmation");
  if (!(caps.inputs || []).length) issues.push("inputs");
  if (!(caps.outputs || []).length) issues.push("outputs");
  if (["text-to-image", "image-to-image", "inpainting"].includes(task)) {
    if (!variant.kind || variant.kind === "unknown") issues.push("variant");
    if (!validRange(caps.steps)) issues.push("steps");
    for (const key of ["guidance", "negativePrompt", "seed"])
      if (typeof caps[key] !== "boolean") issues.push(key);
    if (!(caps.supportedWidths || []).length && !caps.widthMultiple) issues.push("widths");
    if (!(caps.supportedHeights || []).length && !caps.heightMultiple) issues.push("heights");
    if (!(caps.dtypes || []).length) issues.push("dtypes");
    if (task === "inpainting" && !validRange(caps.denoiseStrength)) issues.push("denoise strength");
    if (caps.guidance === true && !validRange(caps.guidanceScale)) issues.push("guidance range");
  }
  if (task === "image-upscaling" && !(caps.scales || []).length) issues.push("scales");
  if (variant.kind === "quantized" && !variant.quantization) issues.push("quantization");
  if (["lora", "controlnet"].includes(variant.kind) && !variant.baseModel) issues.push("base model");
  if (variant.kind === "lora" && !validRange(caps.loraStrength)) issues.push("LoRA strength");
  if (variant.kind === "controlnet") {
    if (!validRange(caps.controlStrength)) issues.push("control strength");
    if (!validRange(caps.controlStart)) issues.push("control start");
    if (!validRange(caps.controlEnd)) issues.push("control end");
  }
  return [...new Set(issues)];
}
