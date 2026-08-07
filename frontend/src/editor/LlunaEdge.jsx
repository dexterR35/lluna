import { BaseEdge, getBezierPath } from "@xyflow/react";
import { resolvePortColor } from "../icons";

/** @param {import("@xyflow/react").EdgeProps} props */
export function LlunaEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  selected,
  markerEnd,
  style,
  data,
}) {
  const [path] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });
  const portType = typeof data?.portType === "string" ? data.portType : "";
  const color = resolvePortColor(portType);
  return (
    <BaseEdge
      id={id}
      path={path}
      markerEnd={markerEnd}
      style={{
        ...style,
        stroke: selected ? "var(--mg-accent)" : color,
        strokeLinecap: "round",
        strokeWidth: selected ? 2.6 : 2,
      }}
      interactionWidth={24}
    />
  );
}
