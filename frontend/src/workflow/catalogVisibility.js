const HIDDEN_PRIMITIVE_NODE_IDS = new Set([
  "midgard.input.boolean",
  "midgard.input.integer",
  "midgard.input.number",
]);

/** @param {Pick<import("../types").NodeDefinition, "schemaId">} node */
export function isVisibleCatalogNode(node) {
  return !HIDDEN_PRIMITIVE_NODE_IDS.has(node.schemaId);
}
