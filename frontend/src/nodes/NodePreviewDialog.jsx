import { Image as ImageIcon } from "lucide-react";
import { Dialog } from "../components";
import { ArtifactPreview } from "../preview/ArtifactPreview";
import { useEditorStore } from "../state/editorStore";
import { useRunStore } from "../state/runStore";

export function NodePreviewDialog({ nodeId, onClose }) {
  const node = useEditorStore(store => store.nodes.find(item => item.id === nodeId));
  const liveRun = useRunStore(store => nodeId ? store.nodeStates[nodeId] : null);
  if (!node) return null;

  const persistedResult = node.data.result;
  const artifactId = (liveRun?.artifactIds?.length ? liveRun.artifactIds : persistedResult?.artifactIds || []).at(-1);
  const label = node.data.label || node.data.definition?.name || "Node";

  return <Dialog open onClose={onClose} wide title={`${label} preview`} description="Latest locally stored image or video output." bodyClassName="!max-h-[78vh]">
    <div className="mb-2 flex items-center gap-2 text-[9px] text-mg-muted"><ImageIcon className="size-3.5" />Completed output</div>
    <ArtifactPreview artifactId={artifactId} effect={node.data.appearance?.imageEffect} />
  </Dialog>;
}
