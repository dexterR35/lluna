/** @param {...(string | false | null | undefined)} values */
export function cn(...values) { return values.filter(Boolean).join(" "); }
export const focusRing = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mg-focus focus-visible:ring-offset-2 focus-visible:ring-offset-mg-app";
