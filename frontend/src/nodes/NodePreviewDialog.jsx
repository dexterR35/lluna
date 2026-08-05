import { Download, Image as ImageIcon } from "../icons";
import { Badge, Button, Dialog } from "../components";
import { useToast } from "../components/ToastContext";
import { ArtifactPreview, ArtifactThumbnail } from "../preview/ArtifactPreview";
import { saveArtifactsExport } from "../preview/saveExport";
import { useEditorStore } from "../state/editorStore";
import { useRunStore } from "../state/runStore";

/** @param {{nodeId: string | null, onClose: () => void}} props */
export function NodePreviewDialog({ nodeId, onClose }) {
  const toast = useToast();
  const node = useEditorStore((store) =>
    store.nodes.find((item) => item.id === nodeId),
  );
  const liveRun = useRunStore((store) =>
    nodeId ? store.nodeStates[nodeId] : null,
  );
  if (!node || node.data.definition?.supportsPreview !== true) return null;

  const persistedResult = node.data.result;
  const artifactIds = liveRun?.artifactIds?.length
    ? liveRun.artifactIds
    : persistedResult?.artifactIds || [];
  const artifactId = artifactIds.at(-1);
  const schemaId = node.data.schemaId;
  const label = node.data.label || node.data.definition?.name || "Node";

  async function saveAll() {
    if (!artifactIds.length) return;
    try {
      const saved = await saveArtifactsExport(artifactIds, { schemaId });
      if (!saved) return;
      toast.push(
        saved.length === 1
          ? `Saved ${saved[0]}`
          : `Saved ${saved.length} files`,
      );
    } catch (error) {
      toast.push(
        error instanceof Error ? error.message : String(error),
        "error",
      );
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      wide
      title={`${label} preview`}
      description="Latest locally stored image or video output."
      bodyClassName="!max-h-[78vh]"
    >
      <div className="ui-inline mb-2 text-[9px] text-mg-muted">
        <ImageIcon className="ui-icon" />
        Completed output
        {artifactIds.length > 1 && (
          <Badge tone="accent">{artifactIds.length} ordered items</Badge>
        )}
        {artifactIds.length > 1 && (
          <Button
            variant="secondary"
            onClick={() => void saveAll()}
            className="ml-auto min-h-6 px-2 text-[9px]"
          >
            <Download className="ui-icon-sm" />
            Save {artifactIds.length}
          </Button>
        )}
      </div>
      {artifactIds.length > 1 ? (
        <div className="ui-preview grid grid-cols-2 gap-2 p-2 sm:grid-cols-3">
          {artifactIds.slice(0, 10).map((id, index) => (
            <div key={id} className="ui-stage overflow-hidden rounded-xl">
              <div className="ui-copy-muted bg-mg-elevated px-2 py-1">
                Item {index + 1}
              </div>
              <ArtifactThumbnail
                artifactId={id}
                schemaId={schemaId}
                ratio="square"
                label={`${label} item ${index + 1}`}
              />
            </div>
          ))}
        </div>
      ) : (
        <ArtifactPreview
          artifactId={artifactId}
          schemaId={schemaId}
          effect={String(node.data.appearance?.imageEffect || "none")}
        />
      )}
    </Dialog>
  );
}
