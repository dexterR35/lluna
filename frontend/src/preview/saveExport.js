import { api, artifactObjectUrl, saveArtifact } from "../api/client";

/** @type {Record<string, string>} */
const SCHEMA_SUFFIXES = {
  "midgard.image.remove_background": "_no_bg",
  "midgard.image.remove_text": "_no_sub",
  "midgard.video.remove_text": "_no_sub",
};

/** @param {string | undefined} schemaId */
export function exportSuffixForSchema(schemaId) {
  return (schemaId && SCHEMA_SUFFIXES[schemaId]) || "";
}

/** @param {string | undefined} mediaType @param {string | undefined} sourceName */
export function extensionForExport(mediaType, sourceName) {
  const fromSource = sourceName?.match(/(\.[a-z0-9]+)$/i)?.[1]?.toLowerCase();
  if (mediaType?.startsWith("video/")) {
    if (mediaType.includes("webm")) return ".webm";
    if (mediaType.includes("quicktime") || mediaType.includes("mov")) return ".mov";
    return fromSource && [".mp4", ".mov", ".mkv", ".webm"].includes(fromSource)
      ? fromSource
      : ".mp4";
  }
  if (mediaType === "image/jpeg") return ".jpg";
  if (mediaType === "image/webp") return ".webp";
  if (mediaType === "image/bmp") return ".bmp";
  if (mediaType === "image/tiff") return ".tiff";
  if (mediaType?.startsWith("image/")) return ".png";
  return fromSource || ".bin";
}

/** @param {string | undefined} value */
export function fileStem(value) {
  const base = String(value || "")
    .trim()
    .split(/[/\\]/)
    .pop();
  if (!base) return "midgard-output";
  const stem = base.replace(/\.[^.]+$/, "");
  const cleaned = stem.replace(/[<>:"|?*\u0000-\u001f]/g, "_").trim();
  return cleaned || "midgard-output";
}

/**
 * @param {{
 *   sourceName?: string | null,
 *   suffix?: string,
 *   mediaType?: string,
 *   usedNames?: Set<string>,
 * }} options
 */
export function buildExportFileName({
  sourceName,
  suffix = "",
  mediaType,
  usedNames,
}) {
  const stem = fileStem(sourceName || undefined);
  const ext = extensionForExport(mediaType, sourceName || undefined);
  const tag = suffix || "";
  let candidate = `${stem}${tag}${ext}`;
  if (!usedNames?.has(candidate.toLowerCase())) {
    usedNames?.add(candidate.toLowerCase());
    return candidate;
  }
  for (let number = 1; number < 10_000; number += 1) {
    candidate = `${stem}${tag}-${number}${ext}`;
    if (!usedNames.has(candidate.toLowerCase())) {
      usedNames.add(candidate.toLowerCase());
      return candidate;
    }
  }
  throw new Error("No available export file name");
}

/** @param {Record<string, any> | null | undefined} metadata */
export async function resolveLinkedSourceName(metadata) {
  /** @type {string[]} */
  const queue = Array.isArray(metadata?.inputArtifactIds)
    ? [...metadata.inputArtifactIds]
    : [];
  const seen = new Set(queue);
  while (queue.length) {
    const inputId = queue.shift();
    if (!inputId) continue;
    try {
      const input = await api(`/api/artifacts/${inputId}/metadata`);
      if (input?.originalSourcePath) {
        return String(input.originalSourcePath).split(/[/\\]/).pop() || null;
      }
      for (const nestedId of input?.inputArtifactIds || []) {
        if (typeof nestedId === "string" && !seen.has(nestedId)) {
          seen.add(nestedId);
          queue.push(nestedId);
        }
      }
    } catch {
      // Keep walking linked inputs when one metadata lookup fails.
    }
  }
  return null;
}

/**
 * Save one or more artifacts into a chosen folder using input-linked names.
 * Desktop: pick folder once, write every file automatically (no rename dialog).
 * Browser: trigger downloads with the same auto names.
 *
 * @param {string[]} artifactIds
 * @param {{ schemaId?: string }} [options]
 * @returns {Promise<string[] | null>} saved file names, or null if cancelled
 */
export async function saveArtifactsExport(artifactIds, options = {}) {
  const ids = [...new Set(artifactIds.filter(Boolean))];
  if (!ids.length) return [];

  const suffix = exportSuffixForSchema(options.schemaId);
  const desktop = window.midgardDesktop;
  const usedNames = new Set();

  /** @type {{ artifactId: string, fileName: string, metadata: Record<string, any>, url?: string }[]} */
  const plans = [];
  for (const artifactId of ids) {
    const metadata = await api(`/api/artifacts/${artifactId}/metadata`);
    const sourceName =
      (await resolveLinkedSourceName(metadata)) || "midgard-output";
    const fileName = buildExportFileName({
      sourceName,
      suffix,
      mediaType: metadata?.mediaType,
      usedNames,
    });
    plans.push({ artifactId, fileName, metadata });
  }

  if (!desktop?.selectDirectory || !desktop.writeGrantInDirectory) {
    for (const plan of plans) {
      const url = await artifactObjectUrl(plan.artifactId);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = plan.fileName;
      anchor.click();
      URL.revokeObjectURL(url);
    }
    return plans.map((plan) => plan.fileName);
  }

  const directory = await desktop.selectDirectory();
  if (!directory) return null;

  /** @type {string[]} */
  const saved = [];
  for (const plan of plans) {
    const grant = await desktop.writeGrantInDirectory(
      directory.grantId,
      plan.fileName,
    );
    const result = await saveArtifact(plan.artifactId, grant.grantId);
    saved.push(result.name || plan.fileName);
  }
  return saved;
}
