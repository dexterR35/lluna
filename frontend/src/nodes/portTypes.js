/** @type {Readonly<Record<string, string>>} */
export const PORT_COLORS = Object.freeze({
  IMAGE: "#64b5f6", VIDEO: "#9575cd", MASK: "#81c784", ALPHA: "#4db6ac",
  PROMPT: "#ffb74d", NUMBER: "#ffd54f", INTEGER: "#f06292", BOOLEAN: "#e57373",
  STRING: "#ba68c8", COLOR: "#4dd0e1", MODEL: "#90a4ae",
  DIRECTORY: "#aed581", FILE: "#dce775",
});
/** @param {string} source @param {string} target */
export function compatibleTypes(source, target) { return source === target || (source === "INTEGER" && target === "NUMBER"); }
