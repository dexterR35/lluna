import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { AlertTriangle, Ban, Box, Check, Clock3, LoaderCircle, Pause, Sparkles, X } from "lucide-react";
import { Badge, ProgressBar } from "../components";
import { useRunStore } from "../state/runStore";
import { PORT_COLORS } from "./portTypes";

const STATUS_ICON = { RUNNING: LoaderCircle, SUCCEEDED: Check, FAILED: X, CACHED: Sparkles, PAUSED: Pause, PAUSE_REQUESTED: Clock3, DISABLED: Ban, INVALID: AlertTriangle };
function Port({ port, side }) {
  const output = side === "output";
  return <div className={`relative flex min-h-6 items-center gap-2 px-3 text-[11px] text-mg-secondary ${output ? "justify-end" : "justify-start"}`}>
    <Handle id={port.id} type={output ? "source" : "target"} position={output ? Position.Right : Position.Left} style={{ backgroundColor: PORT_COLORS[port.type] || "#91a0b2" }} aria-label={`${port.label}, ${port.type}`} />
    <span>{port.label}</span><span className="opacity-50">{port.type.toLowerCase()}</span>
  </div>;
}
function MidgardNodeComponent({ id, data, selected }) {
  const state = useRunStore(store => store.nodeStates[id]);
  const definition = data.definition || { inputs: [], outputs: [], name: data.schemaId, description: "Unknown node" };
  const status = data.disabled ? "DISABLED" : (state?.status || "IDLE");
  const StatusIcon = STATUS_ICON[status] || Box;
  const tone = status === "FAILED" || status === "INVALID" ? "error" : status === "RUNNING" ? "running" : status === "CACHED" ? "cached" : status === "SUCCEEDED" ? "success" : "neutral";
  return <article aria-label={`${data.label || definition.name} node`} className={`w-64 overflow-hidden rounded-xl border bg-mg-node shadow-lg transition ${selected ? "border-mg-focus ring-2 ring-mg-focus/30" : "border-mg-border"} ${data.disabled ? "opacity-55" : ""}`}>
    <header className="flex min-h-11 items-center gap-2 border-b border-mg-border px-3">
      <StatusIcon aria-hidden className={`size-4 shrink-0 ${status === "RUNNING" ? "animate-spin text-mg-running" : "text-mg-secondary"}`} />
      <strong className="min-w-0 flex-1 truncate text-sm">{data.label || definition.name}</strong>
      {status !== "IDLE" && <Badge tone={tone}>{status.replaceAll("_", " ")}</Badge>}
    </header>
    {!data.collapsed && <><div className="grid gap-0.5 py-2">{definition.inputs?.map(port => <Port key={port.id} port={port} side="input" />)}{!definition.inputs?.length && <p className="px-3 text-[11px] text-mg-secondary">{definition.description}</p>}</div>
      {definition.parameters?.length > 0 && <div className="border-t border-mg-border px-3 py-2 text-[11px] text-mg-secondary">{definition.parameters.slice(0, 2).map(item => <div key={item.id} className="flex justify-between gap-3"><span>{item.label}</span><span className="max-w-28 truncate text-mg-primary">{String(data.parameters?.[item.id] ?? "")}</span></div>)}</div>}
      <div className="grid gap-0.5 border-t border-mg-border py-2">{definition.outputs?.map(port => <Port key={port.id} port={port} side="output" />)}{!definition.outputs?.length && <span className="px-3 text-[11px] text-mg-secondary">No output</span>}</div></>}
    {(status === "RUNNING" || status === "PAUSE_REQUESTED") && <ProgressBar value={state?.progress || 0} label={`${data.label} progress`} />}
  </article>;
}
export const MidgardNode = memo(MidgardNodeComponent);
