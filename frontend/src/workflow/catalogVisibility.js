const HIDDEN_NODE_IDS = new Set([
  "lluna.input.boolean",
  "lluna.input.integer",
  "lluna.input.number",
  "lluna.input.llava",
  "lluna.output.preview_image",
  "lluna.output.preview_mask",
  "lluna.output.preview_alpha",
  "lluna.output.preview_video",
]);

/** @param {Pick<import("../types").NodeDefinition, "schemaId">} node */
export function isVisibleCatalogNode(node) {
  return !HIDDEN_NODE_IDS.has(node.schemaId);
}
