import { useEffect, useState } from "react";
import { Download, Image as ImageIcon, MousePointer2 } from "../icons";
import { Badge, Button, Dialog, TextField } from "../components";
import { ArtifactPreview, ArtifactThumbnail } from "../preview/ArtifactPreview";
import { useArtifactSaver } from "../preview/useArtifactSaver";
import { downstreamNodeIds, useEditorStore } from "../state/editorStore";
import { useRunStore } from "../state/runStore";

/** @param {{nodeId: string | null, onClose: () => void}} props */
export function NodePreviewDialog({ nodeId, onClose }) {
  const node = useEditorStore((store) =>
    store.nodes.find((item) => item.id === nodeId),
  );
  const incomingImageEdge = useEditorStore((store) =>
    store.edges.find(
      (edge) => edge.target === nodeId && edge.targetHandle === "image",
    ),
  );
  const sourceNode = useEditorStore((store) =>
    store.nodes.find((item) => item.id === incomingImageEdge?.source),
  );
  const updateNode = useEditorStore((store) => store.updateNode);
  const liveRun = useRunStore((store) =>
    nodeId ? store.nodeStates[nodeId] : null,
  );
  const sourceLiveRun = useRunStore((store) =>
    incomingImageEdge?.source
      ? store.nodeStates[incomingImageEdge.source]
      : null,
  );
  const isSelectObject = node?.data.schemaId === "lluna.mask.select_object";
  const persistedResult = node?.data.result;
  const nodeArtifactIds = liveRun?.artifactIds?.length
    ? liveRun.artifactIds
    : persistedResult?.artifactIds || [];
  const sourceArtifactIds = sourceLiveRun?.artifactIds?.length
    ? sourceLiveRun.artifactIds
    : sourceNode?.data.result?.artifactIds || [];
  const artifactIds = isSelectObject ? sourceArtifactIds : nodeArtifactIds;
  const artifactId = artifactIds.at(-1);
  const schemaId = node?.data.schemaId || "";
  const label = node?.data.label || node?.data.definition?.name || "Node";
  const savedPoints = Array.isArray(node?.data.parameters?.points)
    ? node.data.parameters.points
    : [];
  const savedLabels = Array.isArray(node?.data.parameters?.labels)
    ? node.data.parameters.labels
    : [];
  const points = savedPoints.flatMap((point, index) =>
    Array.isArray(point) && point.length >= 2
      ? [
          {
            x: Number(point[0]),
            y: Number(point[1]),
            label: Number(savedLabels[index] ?? 1),
          },
        ]
      : [],
  );
  const [selectedArtifactId, setSelectedArtifactId] = useState(
    artifactId || "",
  );
  useEffect(() => {
    if (!artifactIds.includes(selectedArtifactId))
      setSelectedArtifactId(artifactId || "");
  }, [artifactId, artifactIds, selectedArtifactId]);
  const saveAll = useArtifactSaver(artifactIds, null, schemaId);

  if (!node || node.data.definition?.supportsPreview !== true) return null;
  const activeNode = node;

  /** @param {Record<string, unknown>} patch */
  function updateParameters(patch) {
    const current = useEditorStore
      .getState()
      .nodes.find((item) => item.id === activeNode.id);
    if (!current) return;
    updateNode(activeNode.id, {
      parameters: { ...current.data.parameters, ...patch },
    });
    useRunStore
      .getState()
      .clearNodeResults(
        downstreamNodeIds([activeNode.id], useEditorStore.getState().edges),
      );
  }

  return (
    <Dialog
      open
      onClose={onClose}
      wide
      title={isSelectObject ? "Select Object" : `${label} preview`}
      description={
        isSelectObject
          ? "Enter an object name or click the source image. Shift-click adds an exclusion point."
          : "Latest locally stored image or video output."
      }
      bodyClassName="!max-h-[78vh]"
    >
      <div className="ui-inline mb-2 text-[9px] text-mg-muted">
        <ImageIcon className="ui-icon" />
        {isSelectObject ? "Source image selection" : "Completed output"}
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
      {isSelectObject && (
        <div className="mb-3 grid grid-cols-[minmax(0,1fr)_auto] items-end gap-2">
          <TextField
            label="Object name"
            hint="Optional when at least one point is selected."
            value={String(node.data.parameters?.text || "")}
            onChange={(event) => updateParameters({ text: event.target.value })}
          />
          <Button
            variant="secondary"
            disabled={!points.length}
            onClick={() => updateParameters({ points: [], labels: [] })}
          >
            Clear {points.length ? `${points.length} point${points.length === 1 ? "" : "s"}` : "points"}
          </Button>
        </div>
      )}
      {artifactIds.length > 1 && (
        <div className="mb-2 flex gap-2 overflow-x-auto pb-1">
          {artifactIds.slice(0, 10).map((id, index) => (
            <button
              type="button"
              key={id}
              className={`w-24 shrink-0 overflow-hidden rounded-xl border ${selectedArtifactId === id ? "border-mg-accent" : "border-mg-border"}`}
              onClick={() => setSelectedArtifactId(id)}
            >
              <span className="ui-copy-muted block bg-mg-elevated px-2 py-1">
                Item {index + 1}
              </span>
              <ArtifactThumbnail
                artifactId={id}
                schemaId={schemaId}
                size="sm"
                label={`${label} item ${index + 1}`}
              />
            </button>
          ))}
        </div>
      )}
      {isSelectObject && !artifactId ? (
        <div className="ui-empty is-roomy rounded-xl border border-mg-border">
          <MousePointer2 className="ui-icon-lg text-mg-muted" />
          <p className="ui-copy-body">Connect and run an Image node first.</p>
        </div>
      ) : (
        <ArtifactPreview
          artifactId={selectedArtifactId || artifactId}
          schemaId={schemaId}
          effect={String(node.data.appearance?.imageEffect || "none")}
          points={isSelectObject ? points : []}
          onPointAdd={
            isSelectObject
              ? (point) =>
                  updateParameters({
                    points: [...savedPoints, [point.x, point.y]],
                    labels: [...savedLabels, point.label],
                  })
              : undefined
          }
        />
      )}
    </Dialog>
  );
}
