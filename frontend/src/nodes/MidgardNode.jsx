import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { AlertTriangle, Ban, Box, Check, Clock3, Eye, LoaderCircle, Pause, Play, Settings2, Sparkles, X } from "lucide-react";
import { Badge, ProgressBar } from "../components";
import { ArtifactThumbnail } from "../preview/ArtifactPreview";
import { useRunStore } from "../state/runStore";
import { PORT_COLORS } from "./portTypes";

const STATUS_ICON = { RUNNING: LoaderCircle, SUCCEEDED: Check, FAILED: X, CACHED: Sparkles, PAUSED: Pause, PAUSE_REQUESTED: Clock3, DISABLED: Ban, INVALID: AlertTriangle };
const ACCENTS = { teal: "#63cbb6", blue: "#70b7f8", violet: "#a393fa", amber: "#e8b768", rose: "#ef7182", slate: "#9298a7" };

function Port({ port, side }) {
  const output = side === "output";
  return <div className={`relative flex min-h-5 items-center gap-1.5 px-2.5 text-[9px] text-mg-secondary ${output ? "justify-end" : "justify-start"}`}>
    <Handle id={port.id} type={output ? "source" : "target"} position={output ? Position.Right : Position.Left} className="midgard-port-handle" style={{ backgroundColor: PORT_COLORS[port.type] || "#9298a7" }} aria-label={`${port.label}, ${port.type}`} />
    <span className="truncate">{port.label}</span><span className="text-[7px] uppercase tracking-wide text-mg-muted">{port.type}</span>
  </div>;
}

function PortList({ definition, side, compact = false }) {
  if (compact) return <div className="grid grid-cols-2 border-t border-mg-border py-0.5">{definition.inputs?.map(port => <Port key={`in-${port.id}`} port={port} side="input" />)}{definition.outputs?.map(port => <Port key={`out-${port.id}`} port={port} side="output" />)}</div>;
  const ports = side === "input" ? definition.inputs : definition.outputs;
  return <div className="grid gap-px py-1">{ports?.map(port => <Port key={port.id} port={port} side={side} />)}{!ports?.length && (side === "input" ? <p className="line-clamp-2 px-2.5 py-1 text-[9px] leading-4 text-mg-muted">{definition.description}</p> : <span className="px-2.5 py-1 text-[8px] text-mg-muted">No output</span>)}</div>;
}

function MidgardNodeComponent({ id, data, selected }) {
  const state = useRunStore(store => store.nodeStates[id]);
  const definition = data.definition || { inputs: [], outputs: [], name: data.schemaId, description: "Unknown node" };
  const appearance = data.appearance || {};
  const cardStyle = appearance.cardStyle || "visual";
  const persistedResult = data.result;
  const status = data.disabled ? "DISABLED" : (state?.status && state.status !== "IDLE" ? state.status : persistedResult?.status || "IDLE");
  const artifactIds = state?.artifactIds?.length ? state.artifactIds : persistedResult?.artifactIds || [];
  const artifactId = artifactIds.at(-1);
  const StatusIcon = STATUS_ICON[status] || Box;
  const tone = status === "FAILED" || status === "INVALID" ? "error" : status === "RUNNING" ? "running" : status === "CACHED" ? "cached" : status === "SUCCEEDED" ? "success" : "neutral";
  const accent = ACCENTS[appearance.accent] || ACCENTS.teal;
  const width = cardStyle === "compact" ? "w-48" : cardStyle === "visual" ? "w-64" : "w-56";
  const modelParameter = definition.parameters?.find(parameter => parameter.id === "model");
  const modelValue = data.parameters?.model || modelParameter?.default;
  const modelLabel = modelParameter?.options?.find(option => option.value === modelValue)?.label || modelValue;
  const nodeLabel = data.label || definition.name;
  const runLabel = definition.kind === "input" ? "Run" : "Run from here";
  const actions = data.nodeActions || {};
  const stopPointer = event => event.stopPropagation();

  return <article aria-label={`${nodeLabel} node`} title="Use the settings button to edit this node" className={`${width} relative overflow-hidden rounded-xl border bg-mg-node transition-[border-color,opacity] ${selected ? "border-mg-focus outline outline-1 outline-offset-1 outline-mg-focus/40" : "border-mg-border hover:border-mg-secondary/40"} ${data.disabled ? "opacity-50" : ""}`} style={{ "--node-accent": accent }}>
    <div className="absolute inset-y-0 left-0 w-0.5" style={{ background: "var(--node-accent)" }} />
    <header className="flex min-h-10 items-center gap-2 border-b border-mg-border px-2.5">
      <span className="grid size-6 shrink-0 place-items-center rounded-lg border" style={{ color: "var(--node-accent)", borderColor: "color-mix(in srgb, var(--node-accent) 22%, transparent)", background: "color-mix(in srgb, var(--node-accent) 9%, transparent)" }}><StatusIcon aria-hidden className={`size-3 ${status === "RUNNING" ? "animate-spin" : ""}`} /></span>
      <span className="min-w-0 flex-1"><strong className="block truncate text-[10px] font-semibold leading-4">{nodeLabel}</strong><span className="block truncate text-[8px] text-mg-muted">{modelLabel || definition.category || data.schemaId}</span></span>
      {status !== "IDLE" && <Badge tone={tone}>{status.replaceAll("_", " ")}</Badge>}
      <button type="button" className="nodrag nowheel grid size-7 shrink-0 place-items-center rounded-lg border border-mg-border text-mg-muted transition hover:border-mg-secondary/40 hover:bg-mg-elevated hover:text-mg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mg-focus/40" aria-label={`Open ${nodeLabel} options`} title="Node options" onPointerDown={stopPointer} onClick={event => { event.stopPropagation(); actions.onOpen?.(id); }}><Settings2 className="size-3.5" /></button>
    </header>
    {appearance.showPreview !== false && cardStyle === "visual" && artifactId && <ArtifactThumbnail artifactId={artifactId} effect={appearance.imageEffect} fit={appearance.imageFit} ratio={appearance.imageRatio} label={`${data.label || definition.name} output`} />}
    {!data.collapsed && cardStyle !== "compact" && <>
      <div><div className="px-2.5 pt-1.5 text-[7px] font-semibold uppercase tracking-[.12em] text-mg-muted">Inputs</div><PortList definition={definition} side="input" /></div>
      {definition.parameters?.length > 0 && <div className="grid gap-1 border-t border-mg-border bg-mg-app/20 px-2.5 py-1.5 text-[8px] text-mg-muted">{definition.parameters.slice(0, 2).map(item => { const rawValue = data.parameters?.[item.id]; const displayValue = item.type === "file" ? (data.result?.sourceName || (rawValue ? "Selected" : "Not selected")) : String(rawValue ?? ""); return <div key={item.id} className="flex justify-between gap-2"><span className="truncate">{item.label}</span><span className="max-w-24 truncate font-medium text-mg-secondary">{displayValue}</span></div>; })}</div>}
      <div className="border-t border-mg-border"><div className="px-2.5 pt-1.5 text-[7px] font-semibold uppercase tracking-[.12em] text-mg-muted">Outputs</div><PortList definition={definition} side="output" /></div>
    </>}
    {cardStyle === "compact" && !data.collapsed && <PortList definition={definition} compact />}
    {(status === "RUNNING" || status === "PAUSE_REQUESTED") && <div className="px-2.5 py-1.5"><ProgressBar value={state?.progress || 0} label={`${data.label} progress`} /></div>}
    <footer className="flex min-h-9 items-center justify-end gap-1.5 border-t border-mg-border bg-mg-app/20 px-2 py-1.5">
      {artifactId && <button type="button" className="nodrag nowheel inline-flex min-h-6 items-center gap-1 rounded-lg px-2 text-[8px] font-medium text-mg-secondary transition hover:bg-mg-elevated hover:text-mg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mg-focus/40" aria-label={`Open ${nodeLabel} preview`} onPointerDown={stopPointer} onClick={event => { event.stopPropagation(); actions.onPreview?.(id); }}><Eye className="size-3" />Preview</button>}
      <button type="button" className="nodrag nowheel grid size-7 shrink-0 place-items-center rounded-full bg-mg-accent text-white transition hover:scale-105 hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mg-focus/50 disabled:cursor-not-allowed disabled:opacity-50" aria-label={`${runLabel} ${nodeLabel}`} title={runLabel} disabled={data.disabled || status === "RUNNING" || status === "QUEUED"} onPointerDown={stopPointer} onClick={event => { event.stopPropagation(); actions.onRun?.(id); }}><Play className="size-3 fill-current" /></button>
    </footer>
  </article>;
}

export const MidgardNode = memo(MidgardNodeComponent);
