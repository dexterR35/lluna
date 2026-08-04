import { expect, test } from "vitest";
import {
  buildExportFileName,
  exportSuffixForSchema,
  extensionForExport,
  fileStem,
} from "../src/preview/saveExport";

test("export suffixes follow remove-background and remove-text schemas", () => {
  expect(exportSuffixForSchema("midgard.image.remove_background")).toBe(
    "_no_bg",
  );
  expect(exportSuffixForSchema("midgard.image.remove_text")).toBe("_no_sub");
  expect(exportSuffixForSchema("midgard.video.remove_text")).toBe("_no_sub");
  expect(exportSuffixForSchema("midgard.generate.image")).toBe("");
});

test("export file names reuse the linked input stem with effect tags", () => {
  expect(
    buildExportFileName({
      sourceName: "/photos/clip.mp4",
      suffix: "_no_sub",
      mediaType: "video/mp4",
    }),
  ).toBe("clip_no_sub.mp4");
  expect(
    buildExportFileName({
      sourceName: "portrait.JPG",
      suffix: "_no_bg",
      mediaType: "image/png",
    }),
  ).toBe("portrait_no_bg.png");
});

test("export file names avoid collisions inside one batch", () => {
  const usedNames = new Set();
  expect(
    buildExportFileName({
      sourceName: "shot.png",
      suffix: "_no_bg",
      mediaType: "image/png",
      usedNames,
    }),
  ).toBe("shot_no_bg.png");
  expect(
    buildExportFileName({
      sourceName: "shot.png",
      suffix: "_no_bg",
      mediaType: "image/png",
      usedNames,
    }),
  ).toBe("shot_no_bg-1.png");
});

test("file stem and extension helpers stay conservative", () => {
  expect(fileStem("C:\\\\inbox\\\\holiday.mov")).toBe("holiday");
  expect(extensionForExport("image/jpeg", "x.png")).toBe(".jpg");
  expect(extensionForExport("video/mp4", "x.mkv")).toBe(".mkv");
});
