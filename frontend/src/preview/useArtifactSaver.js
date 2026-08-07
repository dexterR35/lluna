import { useToast } from "../components/ToastContext";
import { saveArtifactsExport } from "./saveExport";

/**
 * Save one or more artifacts to disk with a consistent success/error toast.
 * Shared by ArtifactPreview's own save button and NodePreviewDialog's
 * "save all" action so both surfaces behave identically.
 * @param {string | string[] | undefined} artifactIds
 * @param {import("../types").ArtifactPreviewState | null | undefined} state
 * @param {string | undefined} schemaId
 */
export function useArtifactSaver(artifactIds, state, schemaId) {
  const toast = useToast();
  return async function save() {
    const ids = /** @type {string[]} */ (
      (Array.isArray(artifactIds) ? artifactIds : [artifactIds]).filter(
        (id) => typeof id === "string" && id.length > 0,
      )
    );
    if (!ids.length) return;
    if (state && !state.url && ids.length === 1) return;
    try {
      const saved = await saveArtifactsExport(ids, { schemaId });
      if (!saved) return;
      if (saved.length === 1) toast.push(`Saved ${saved[0]}`);
      else toast.push(`Saved ${saved.length} files`);
    } catch (error) {
      toast.push(
        error instanceof Error ? error.message : String(error),
        "error",
      );
    }
  };
}
