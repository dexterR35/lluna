/** Model-specific parameter projection. The backend remains the enforcement boundary. */

/** @param {import("../types").ParameterOption | undefined} option */
export function capabilityContract(option) {
  const value = option?.capabilities;
  return value && typeof value === "object" ? value : null;
}

/** @param {import("../types").ParameterDefinition} parameter @param {Record<string, any> | null} capabilities */
export function parameterForCapabilities(parameter, capabilities, model = "") {
  if (
    parameter.visibleForModels?.length &&
    !parameter.visibleForModels.includes(String(model))
  )
    return null;
  if (!parameter.capability) return parameter;
  if (!capabilities?.complete) return null;
  const key = parameter.capability;
  if (["negativePrompt", "guidance", "seed"].includes(key) && capabilities[key] !== true)
    return null;
  if (key === "steps" && !capabilities.steps) return null;

  if (key === "width" || key === "height") {
    const values = capabilities[key === "width" ? "supportedWidths" : "supportedHeights"] || [];
    const multiple = capabilities[key === "width" ? "widthMultiple" : "heightMultiple"];
    if (values.length) {
      return {
        ...parameter,
        type: "select",
        default: values[0],
        options: values.map((/** @type {number} */ value) => ({ value, label: String(value) })),
      };
    }
    return multiple
      ? { ...parameter, description: `${parameter.description || ""} Must be a multiple of ${multiple}.`.trim() }
      : null;
  }

  const numeric = key === "steps" ? capabilities.steps : key === "guidance" ? capabilities.guidanceScale : null;
  if (numeric) {
    const values = numeric.values || [];
    return {
      ...parameter,
      default: numeric.default,
      minimum: numeric.minimum,
      maximum: numeric.maximum,
      ...(values.length
        ? { type: "select", options: values.map((/** @type {number} */ value) => ({ value, label: String(value) })) }
        : {}),
    };
  }
  return parameter;
}

/**
 * @param {import("../types").ParameterDefinition[]} parameters
 * @param {Record<string, any> | null} capabilities
 * @returns {import("../types").ParameterDefinition[]}
 */
export function parametersForCapabilities(parameters, capabilities, model = "") {
  return parameters
    .map((parameter) =>
      parameterForCapabilities(parameter, capabilities, model),
    )
    .filter((parameter) => parameter !== null);
}

/** @param {Record<string, any>} current @param {Record<string, any>} capabilities @param {string | number} model */
export function applyCapabilityDefaults(current, capabilities, model) {
  /** @type {Record<string, any>} */
  const next = { ...current, model };
  for (const key of ["width", "height", "steps", "guidance", "negativePrompt", "seed"])
    delete next[key];
  const widths = capabilities.supportedWidths || [];
  const heights = capabilities.supportedHeights || [];
  if (widths.length) next.width = widths[0];
  if (heights.length) next.height = heights[0];
  if (capabilities.steps) next.steps = capabilities.steps.default;
  if (capabilities.guidance === true && capabilities.guidanceScale)
    next.guidance = capabilities.guidanceScale.default;
  if (capabilities.negativePrompt === true) next.negativePrompt = "";
  if (capabilities.seed === true) next.seed = -1;
  return next;
}
