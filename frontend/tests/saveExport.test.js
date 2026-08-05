import { expect, test } from "vitest";
import {
  buildExportFileName,
  exportSuffixForSchema,
  exportSuffixForSchemas,
  extensionForExport,
  fileStem,
} from "../src/preview/saveExport";

test("export suffixes follow processing schemas", () => {
  expect(exportSuffixForSchema("lluna.image.remove_text")).toBe("_nosub");
  expect(exportSuffixForSchema("lluna.video.remove_text")).toBe("_nosub");
  expect(exportSuffixForSchema("lluna.image.upscale")).toBe("_upscale");
  expect(
    exportSuffixForSchemas([
      "lluna.image.low_light",
      "lluna.image.upscale",
    ]),
  ).toBe("_lowlight_upscale");
  expect(exportSuffixForSchema("lluna.generate.image")).toBe("");
});

test("export file names reuse the linked input stem with effect tags", () => {
  expect(
    buildExportFileName({
      sourceName: "/photos/clip.mp4",
      suffix: "_nosub",
      mediaType: "video/mp4",
    }),
  ).toBe("clip_nosub.mp4");
  expect(
    buildExportFileName({
      sourceName: "portrait.JPG",
      suffix: "_nobg",
      mediaType: "image/png",
    }),
  ).toBe("portrait_nobg.png");
});

test("export file names avoid collisions inside one batch", () => {
  const usedNames = new Set();
  expect(
    buildExportFileName({
      sourceName: "shot.png",
      suffix: "_nobg",
      mediaType: "image/png",
      usedNames,
    }),
  ).toBe("shot_nobg.png");
  expect(
    buildExportFileName({
      sourceName: "shot.png",
      suffix: "_nobg",
      mediaType: "image/png",
      usedNames,
    }),
  ).toBe("shot_nobg-1.png");
});

test("file stem and extension helpers stay conservative", () => {
  expect(fileStem("C:\\\\inbox\\\\holiday.mov")).toBe("holiday");
  expect(extensionForExport("image/jpeg", "x.png")).toBe(".jpg");
  expect(extensionForExport("video/mp4", "x.mkv")).toBe(".mkv");
});
