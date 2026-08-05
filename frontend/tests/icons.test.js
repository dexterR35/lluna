import { expect, test } from "vitest";
import {
  FLOW_COLORS,
  Image,
  Film,
  Scan,
  Type,
  AudioLines,
  resolveCategoryColor,
  resolveCategoryIcon,
  resolveNodeIcon,
  resolvePortColor,
  resolvePortIcon,
} from "../src/icons";

test("same concept shares one icon and color across nodes, ports, and categories", () => {
  expect(resolvePortIcon("IMAGE")).toBe(Image);
  expect(resolveNodeIcon("image")).toBe(Image);
  expect(resolveCategoryIcon("Image")).toBe(Image);
  expect(resolvePortColor("IMAGE")).toBe(FLOW_COLORS.blue);
  expect(resolveCategoryColor("Image")).toBe(FLOW_COLORS.blue);

  expect(resolvePortIcon("VIDEO")).toBe(Film);
  expect(resolveNodeIcon("film")).toBe(Film);
  expect(resolveCategoryIcon("Video")).toBe(Film);
  expect(resolvePortColor("VIDEO")).toBe(FLOW_COLORS.violet);
  expect(resolveCategoryColor("Video")).toBe(FLOW_COLORS.violet);

  expect(resolvePortIcon("MASK")).toBe(Scan);
  expect(resolveNodeIcon("scan")).toBe(Scan);
  expect(resolveCategoryIcon("Mask")).toBe(Scan);
  expect(resolvePortColor("MASK")).toBe(FLOW_COLORS.amber);

  expect(resolvePortIcon("TEXT")).toBe(Type);
  expect(resolvePortIcon("PROMPT")).toBe(Type);
  expect(resolvePortColor("TEXT")).toBe(FLOW_COLORS.amber);
  expect(resolvePortIcon("AUDIO")).toBe(AudioLines);
  expect(resolvePortColor("AUDIO")).toBe(FLOW_COLORS.rose);
  expect(resolvePortColor("PATH")).toBe(FLOW_COLORS.teal);
  expect(resolveCategoryColor("Input")).toBe(FLOW_COLORS.teal);
  expect(resolvePortColor("MODEL")).toBe(FLOW_COLORS.slate);
});
