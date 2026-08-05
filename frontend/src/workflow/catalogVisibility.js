const HIDDEN_PRIMITIVE_NODE_IDS = new Set([
  "lluna.input.boolean",
  "lluna.input.integer",
  "lluna.input.number",
  "lluna.input.llava",
]);

/** @param {Pick<import("../types").NodeDefinition, "schemaId">} node */
export function isVisibleCatalogNode(node) {
  return !HIDDEN_PRIMITIVE_NODE_IDS.has(node.schemaId);
}
