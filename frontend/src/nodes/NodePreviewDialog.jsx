import { Image as ImageIcon } from "lucide-react";
import { Badge, Dialog } from "../components";
import { ArtifactPreview, ArtifactThumbnail } from "../preview/ArtifactPreview";
import { useEditorStore } from "../state/editorStore";
import { useRunStore } from "../state/runStore";

/** @param {{nodeId: string | null, onClose: () => void}} props */
export function NodePreviewDialog({ nodeId, onClose }) {
  const node = useEditorStore(store => store.nodes.find(item => item.id === nodeId));
  const liveRun = useRunStore(store => nodeId ? store.nodeStates[nodeId] : null);
  if (!node) return null;

  const persistedResult = node.data.result;
  const artifactIds = liveRun?.artifactIds?.length
    ? liveRun.artifactIds
    : persistedResult?.artifactIds || [];
  const artifactId = artifactIds.at(-1);
  const label = node.data.label || node.data.definition?.name || "Node";

  return <Dialog open onClose={onClose} wide title={`${label} preview`} description="Latest locally stored image or video output." bodyClassName="!max-h-[78vh]">
    <div className="mb-2 flex items-center gap-2 text-[9px] text-mg-muted"><ImageIcon className="size-3.5" />Completed output{artifactIds.length > 1 && <Badge tone="accent">{artifactIds.length} ordered items</Badge>}</div>
    {artifactIds.length > 1 ? (
      <div className="grid grid-cols-2 gap-2 overflow-hidden rounded-2xl border border-mg-border bg-mg-app p-2 sm:grid-cols-3">
        {artifactIds.map((id, index) => (
          <div key={id} className="overflow-hidden rounded-xl border border-mg-border">
            <div className="bg-mg-elevated px-2 py-1 text-[9px] text-mg-muted">Item {index + 1}</div>
            <ArtifactThumbnail artifactId={id} ratio="square" label={`${label} item ${index + 1}`} />
          </div>
        ))}
      </div>
    ) : (
      <ArtifactPreview artifactId={artifactId} effect={String(node.data.appearance?.imageEffect || "none")} />
    )}
  </Dialog>;
}
