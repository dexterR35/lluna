import { BaseEdge, EdgeLabelRenderer, getBezierPath } from "@xyflow/react";
import { X } from "lucide-react";
import { useEditorStore } from "../state/editorStore";
export function MidgardEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, selected, markerEnd, style }) {
  const [path, x, y] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  const remove = useEditorStore(store => store.removeEdge);
  return <><BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} /><EdgeLabelRenderer>{selected && <button type="button" aria-label="Delete connection" onClick={() => remove(id)} className="nodrag nopan absolute grid size-6 place-items-center rounded-full border border-mg-border bg-mg-panel text-mg-secondary hover:text-mg-error" style={{ transform: `translate(-50%, -50%) translate(${x}px,${y}px)` }}><X className="size-3" /></button>}</EdgeLabelRenderer></>;
}
