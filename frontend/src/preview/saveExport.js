import { api, artifactObjectUrl, saveArtifact } from "../api/client";

/** @type {Record<string, string>} */
const SCHEMA_SUFFIXES = {
  "midgard.image.remove_text": "_nosub",
  "midgard.video.remove_text": "_nosub",
  "midgard.image.upscale": "_upscale",
  "midgard.image.low_light": "_lowlight",
};

/** @param {string | undefined} schemaId */
export function exportSuffixForSchema(schemaId) {
  return (schemaId && SCHEMA_SUFFIXES[schemaId]) || "";
}

/** @param {string[]} schemaIds */
export function exportSuffixForSchemas(schemaIds) {
  const seen = new Set();
  return schemaIds
    .map(exportSuffixForSchema)
    .filter((suffix) => suffix && !seen.has(suffix) && seen.add(suffix))
    .join("");
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
  // Windows filenames forbid ASCII control characters; the range is intentional.
  // eslint-disable-next-line no-control-regex
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
  return (await resolveLinkedExportInfo(metadata)).sourceName;
}

/**
 * Resolve the original input name and every known transformation in source order.
 * @param {Record<string, any> | null | undefined} metadata
 * @param {string | undefined} fallbackSchemaId
 */
export async function resolveLinkedExportInfo(
  metadata,
  fallbackSchemaId = undefined,
) {
  /** @type {string[]} */
  const reversedSchemas = [];
  const seenArtifacts = new Set();
  let sourceName = metadata?.originalSourcePath
    ? String(metadata.originalSourcePath).split(/[/\\]/).pop() || null
    : null;

  /** @param {Record<string, any> | null | undefined} record @param {boolean} root */
  async function walk(record, root = false) {
    const schemaId = record?.creatingSchemaId || (root ? fallbackSchemaId : "");
    if (schemaId) reversedSchemas.push(String(schemaId));
    if (record?.originalSourcePath) {
      sourceName =
        String(record.originalSourcePath).split(/[/\\]/).pop() || sourceName;
      return true;
    }
    for (const inputId of record?.inputArtifactIds || []) {
      if (typeof inputId !== "string" || seenArtifacts.has(inputId)) continue;
      seenArtifacts.add(inputId);
      try {
        const input = await api(`/api/artifacts/${inputId}/metadata`);
        if (await walk(input)) return true;
      } catch {
        // Try the next linked input when one artifact is unavailable.
      }
    }
    return false;
  }

  await walk(metadata, true);
  return {
    sourceName,
    suffix: exportSuffixForSchemas(reversedSchemas.reverse()),
  };
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

  const desktop = window.midgardDesktop;
  const usedNames = new Set();

  /** @type {{ artifactId: string, fileName: string, metadata: Record<string, any>, url?: string }[]} */
  const plans = [];
  for (const artifactId of ids) {
    const metadata = await api(`/api/artifacts/${artifactId}/metadata`);
    const linked = await resolveLinkedExportInfo(metadata, options.schemaId);
    const sourceName = linked.sourceName || "midgard-output";
    const fileName = buildExportFileName({
      sourceName,
      suffix: linked.suffix,
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

  const preparedGrants = await desktop.prepareDirectoryWrites(
    directory.grantId,
    plans.map((plan) => plan.fileName),
  );
  if (!preparedGrants) return null;

  /** @type {string[]} */
  const saved = [];
  for (const [index, plan] of plans.entries()) {
    const grant =
      preparedGrants?.[index] ||
      (await desktop.writeGrantInDirectory(directory.grantId, plan.fileName));
    const result = await saveArtifact(plan.artifactId, grant.grantId);
    saved.push(result.name || plan.fileName);
  }
  return saved;
}
