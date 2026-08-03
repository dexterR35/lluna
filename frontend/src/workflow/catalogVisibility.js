const HIDDEN_PRIMITIVE_NODE_IDS = new Set([
  "midgard.input.boolean",
  "midgard.input.integer",
  "midgard.input.number",
]);

export function isVisibleCatalogNode(node) {
  return !HIDDEN_PRIMITIVE_NODE_IDS.has(node.schemaId);
}
