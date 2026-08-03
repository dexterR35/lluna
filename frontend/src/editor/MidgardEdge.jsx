import { BaseEdge, EdgeLabelRenderer, getBezierPath } from "@xyflow/react";
import { X } from "lucide-react";
import { useEditorStore } from "../state/editorStore";
export function MidgardEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, selected, markerEnd, style }) {
  const [path, x, y] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  const remove = useEditorStore(store => store.removeEdge);
  function unlink(event) {
    event.preventDefault();
    event.stopPropagation();
    remove(id);
  }
  return <>
    <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} interactionWidth={24} />
    <EdgeLabelRenderer>
      <button
        type="button"
        aria-label="Unlink connection"
        title="Unlink connection"
        onPointerDown={event => event.stopPropagation()}
        onClick={unlink}
        className={`midgard-edge-unlink nodrag nopan absolute grid size-5 place-items-center rounded-full border ${selected ? "is-selected" : ""}`}
        style={{ transform: `translate(-50%, -50%) translate(${x}px,${y}px)` }}
      >
        <X className="size-2.5" />
      </button>
    </EdgeLabelRenderer>
  </>;
}
