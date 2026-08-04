import { Image as ImageIcon } from "lucide-react";
import { Badge, Dialog } from "../components";
import { ArtifactPreview, ArtifactThumbnail } from "../preview/ArtifactPreview";
import { useEditorStore } from "../state/editorStore";
import { useRunStore } from "../state/runStore";

/** @param {{nodeId: string | null, onClose: () => void}} props */
export function NodePreviewDialog({ nodeId, onClose }) {
  const node = useEditorStore((store) =>
    store.nodes.find((item) => item.id === nodeId),
  );
  const liveRun = useRunStore((store) =>
    nodeId ? store.nodeStates[nodeId] : null,
  );
  if (!node) return null;

  const persistedResult = node.data.result;
  const artifactIds = liveRun?.artifactIds?.length
    ? liveRun.artifactIds
    : persistedResult?.artifactIds || [];
  const artifactId = artifactIds.at(-1);
  const label = node.data.label || node.data.definition?.name || "Node";

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
                ratio="square"
                label={`${label} item ${index + 1}`}
              />
            </div>
          ))}
        </div>
      ) : (
        <ArtifactPreview
          artifactId={artifactId}
          effect={String(node.data.appearance?.imageEffect || "none")}
        />
      )}
    </Dialog>
  );
}
