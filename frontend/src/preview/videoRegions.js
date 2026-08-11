/** @param {number} value @param {number} maximum */
function clamp(value, maximum) {
  return Math.max(0, Math.min(maximum, Number(value) || 0));
}

/**
 * Convert a drag gesture into the subtitle-remover coordinate order:
 * [yMin, yMax, xMin, xMax].
 *
 * @param {{x: number, y: number}} start
 * @param {{x: number, y: number}} end
 * @param {number} width
 * @param {number} height
 * @returns {number[] | null}
 */
export function subtitleAreaFromDrag(start, end, width, height) {
  if (!(width > 0) || !(height > 0)) return null;
  const x1 = Math.round(clamp(start.x, width));
  const x2 = Math.round(clamp(end.x, width));
  const y1 = Math.round(clamp(start.y, height));
  const y2 = Math.round(clamp(end.y, height));
  const xMin = Math.min(x1, x2);
  const xMax = Math.max(x1, x2);
  const yMin = Math.min(y1, y2);
  const yMax = Math.max(y1, y2);
  if (xMax - xMin < 2 || yMax - yMin < 2) return null;
  return [yMin, yMax, xMin, xMax];
}

/**
 * Return a safe, bounded subtitle area or null for malformed saved data.
 * @param {unknown} value
 * @param {number} width
 * @param {number} height
 * @returns {number[] | null}
 */
export function normalizeSubtitleArea(value, width, height) {
  if (!Array.isArray(value) || value.length < 4) return null;
  const [y1, y2, x1, x2] = value.map(Number);
  if (![y1, y2, x1, x2].every(Number.isFinite)) return null;
  return subtitleAreaFromDrag(
    { x: x1, y: y1 },
    { x: x2, y: y2 },
    width,
    height,
  );
}

/** @param {number[]} area @param {number} width @param {number} height */
export function subtitleAreaStyle(area, width, height) {
  const [yMin, yMax, xMin, xMax] = area;
  return {
    left: `${(xMin / width) * 100}%`,
    top: `${(yMin / height) * 100}%`,
    width: `${((xMax - xMin) / width) * 100}%`,
    height: `${((yMax - yMin) / height) * 100}%`,
  };
}
