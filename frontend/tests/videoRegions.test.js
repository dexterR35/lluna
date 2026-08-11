import { describe, expect, test } from "vitest";
import {
  normalizeSubtitleArea,
  subtitleAreaFromDrag,
  subtitleAreaStyle,
} from "../src/preview/videoRegions";

describe("video subtitle removal areas", () => {
  test("converts a reverse drag to backend y/y/x/x coordinate order", () => {
    expect(
      subtitleAreaFromDrag(
        { x: 1800, y: 980 },
        { x: 120, y: 720 },
        1920,
        1080,
      ),
    ).toEqual([720, 980, 120, 1800]);
  });

  test("bounds saved areas to the source frame", () => {
    expect(normalizeSubtitleArea([-20, 1200, -5, 2000], 1920, 1080)).toEqual([
      0, 1080, 0, 1920,
    ]);
  });

  test("rejects clicks and malformed areas", () => {
    expect(
      subtitleAreaFromDrag({ x: 10, y: 10 }, { x: 11, y: 11 }, 100, 100),
    ).toBeNull();
    expect(normalizeSubtitleArea([1, 2, "bad", 4], 100, 100)).toBeNull();
  });

  test("positions overlays as frame-relative percentages", () => {
    expect(subtitleAreaStyle([50, 100, 25, 125], 200, 200)).toEqual({
      left: "12.5%",
      top: "25%",
      width: "50%",
      height: "25%",
    });
  });
});
