import { memo, useState } from "react";
import * as XYFlow from "@xyflow/react";
import {
  AlertTriangle,
  Ban,
  Box,
  Check,
  Clock3,
  Eye,
  FileImage,
  Film,
  Hash,
  Image as ImageIcon,
  Images,
  Layers3,
  LoaderCircle,
  Pause,
  Play,
  Settings2,
  Sparkles,
  Type,
  X,
  ZoomIn,
} from "lucide-react";
import { ProgressBar, Badge, IconTile, Select } from "../components";
import { ArtifactThumbGrid, ArtifactThumbnail } from "../preview/ArtifactPreview";
import { useRunStore } from "../state/runStore";
import { PORT_COLORS } from "./portTypes";
import { enabledModelOptions } from "../models/modelAvailability";

/** @typedef {import("react").ComponentType<{className?: string, "aria-hidden"?: boolean, style?: import("react").CSSProperties}>} NodeIcon */
/** @type {Record<string, NodeIcon>} */
const STATUS_ICON = {
  RUNNING: LoaderCircle,
  SUCCEEDED: Check,
  FAILED: X,
  CACHED: Sparkles,
  PAUSED: Pause,
  PAUSE_REQUESTED: Clock3,
  DISABLED: Ban,
  INVALID: AlertTriangle,
};

/** @type {Record<string, "neutral"|"success"|"warning"|"error"|"running"|"cached"|"accent">} */
const STATUS_TONE = {
  RUNNING: "running",
  QUEUED: "running",
  SUCCEEDED: "success",
  FAILED: "error",
  INVALID: "error",
  CACHED: "cached",
  PAUSED: "warning",
  PAUSE_REQUESTED: "warning",
  DISABLED: "neutral",
};

/** @type {Record<string, NodeIcon>} */
const PORT_ICONS = {
  IMAGE: ImageIcon,
  MASK: ImageIcon,
  ALPHA: ImageIcon,
  VIDEO: Film,
  PROMPT: Type,
  TEXT: Type,
  STRING: Type,
  NUMBER: Hash,
  INTEGER: Hash,
  FILE: FileImage,
  DIRECTORY: FileImage,
  MODEL: Box,
};

/** @type {Record<string, NodeIcon>} */
const NODE_ICONS = {
  image: ImageIcon,
  images: Images,
  layers: Layers3,
  film: Film,
  sparkles: Sparkles,
  "zoom-in": ZoomIn,
  eye: ImageIcon,
  play: Play,
};

/** @param {string | undefined} type */
function portIcon(type) {
  return PORT_ICONS[type || ""] || Box;
}

/** @param {import("../types").NodeDefinition} definition */
function nodeIcon(definition) {
  return NODE_ICONS[definition.icon || ""] || Box;
}

/**
 * Outside connection circle for linking ports.
 * @param {{port: import("../types").PortDefinition, side: "input"|"output", top: string, active: boolean}} props
 */
function PortCircle({ port, side, top, active }) {
  const output = side === "output";
  const Icon = portIcon(port.type);
  const color = PORT_COLORS[port.type] || "#9298a7";
  return (
    <XYFlow.Handle
      id={port.id}
      type={output ? "source" : "target"}
      position={output ? XYFlow.Position.Right : XYFlow.Position.Left}
      className={`midgard-port-handle ${active ? "is-active" : ""} ${output ? "is-output" : "is-input"}`}
      style={/** @type {import("react").CSSProperties} */ ({ top, "--port-color": color })}
      aria-label={`${port.label}, ${port.type}${port.multiple ? ", queue" : ""}`}
      title={`${port.label} · ${port.type}${port.multiple ? " queue" : ""}`}
    >
      <Icon aria-hidden className="midgard-port-glyph" style={{ color }} />
    </XYFlow.Handle>
  );
}

/** @param {import("@xyflow/react").NodeProps<import("../types").EditorNode>} props */
function MidgardNodeComponent({ id, data, selected }) {
  const state = useRunStore((store) => store.nodeStates[id]);
  const [hovered, setHovered] = useState(false);
  /** @type {import("../types").NodeDefinition} */
  const definition = data.definition || {
    schemaId: data.schemaId,
    schemaVersion: data.schemaVersion,
    inputs: [],
    outputs: [],
    parameters: [],
    name: data.schemaId,
    description: "Unknown node",
  };
  const appearance = data.appearance || {};
  const persistedResult = data.result;
  const status = data.disabled
    ? "DISABLED"
    : state?.status && state.status !== "IDLE"
      ? state.status
      : persistedResult?.status || "IDLE";
  const artifactIds = state?.artifactIds?.length
    ? state.artifactIds
    : persistedResult?.artifactIds || [];
  const artifactId = artifactIds.at(-1);
  const StatusIcon = STATUS_ICON[status] || Box;
  const HeaderIcon = nodeIcon(definition);
  const busy = status === "RUNNING" || status === "QUEUED";
  const showPorts = selected || hovered || busy;
  const nodeLabel = data.label || definition.name;
  const runLabel = definition.kind === "input" ? "Run" : "Run from here";
  const actions = data.nodeActions || {};
  const parameters = definition.parameters || [];
  const modelParameter = parameters.find(
    (parameter) => parameter.id === "model" || parameter.type === "model",
  );
  const modelValue = data.parameters?.model || modelParameter?.default;
  const modelOptions = enabledModelOptions(
    modelParameter?.options || [],
    data.modelInventory || [],
  );
  const modelLabel = String(
    modelParameter?.options?.find((option) => option.value === modelValue)
      ?.label ||
      modelValue ||
      "",
  );
  const modelAvailable = modelOptions.some(
    (option) => String(option.value) === String(modelValue),
  );
  const footerParams = parameters.filter((parameter) => {
    if (parameter.id === "model" || parameter.type === "model") return true;
    if (parameter.type === "select" || parameter.type === "enum") return true;
    return Boolean(parameter.options?.length);
  });
  const promptParam = parameters.find(
    (parameter) =>
      parameter.type === "textarea" ||
      parameter.id === "value" ||
      parameter.id === "prompt" ||
      parameter.id === "text",
  );
  const showPromptField =
    Boolean(promptParam) &&
    (definition.kind === "input" ||
      definition.schemaId?.includes("prompt") ||
      definition.schemaId?.includes("generate"));
  const inputs = definition.inputs || [];
  const outputs = definition.outputs || [];
  /** @param {import("react").SyntheticEvent} event */
  const stopPointer = (event) => event.stopPropagation();

  /** @param {number} index @param {number} total */
  const portTop = (index, total) =>
    total <= 1 ? "50%" : `${((index + 1) / (total + 1)) * 100}%`;

  return (
    <article
      aria-label={`${nodeLabel} node`}
      title="Use the settings button to edit this node"
      className={`midgard-node ${selected ? "is-selected" : ""} ${data.disabled ? "is-disabled" : ""} ${showPorts ? "is-ports-open" : ""}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {inputs.map((port, index) => (
        <PortCircle
          key={`in-${port.id}`}
          port={port}
          side="input"
          top={portTop(index, inputs.length)}
          active={showPorts}
        />
      ))}
      {outputs.map((port, index) => (
        <PortCircle
          key={`out-${port.id}`}
          port={port}
          side="output"
          top={portTop(index, outputs.length)}
          active={showPorts}
        />
      ))}

      <header className="midgard-node-header">
        <IconTile
          size="sm"
          active={selected}
          className="border-transparent bg-transparent"
          aria-hidden
        >
          {status !== "IDLE" && status !== "SUCCEEDED" ? (
            <StatusIcon
              className={`size-3.5 ${status === "RUNNING" ? "animate-spin" : ""}`}
            />
          ) : (
            <HeaderIcon className="size-3.5" />
          )}
        </IconTile>
        <strong className="midgard-node-title">{nodeLabel}</strong>
        {status !== "IDLE" && (
          <Badge size="xs" tone={STATUS_TONE[status] || "neutral"}>
            {status.replaceAll("_", " ")}
          </Badge>
        )}
        {artifactIds.length > 1 && (
          <Badge size="xs" tone="accent">
            {artifactIds.length} items
          </Badge>
        )}
      </header>

      <div className="midgard-node-body">
        {appearance.showPreview !== false && artifactIds.length > 1 ? (
          <ArtifactThumbGrid
            artifactIds={artifactIds}
            schemaId={data.schemaId}
            effect={String(appearance.imageEffect || "none")}
            fit={String(appearance.imageFit || "cover")}
            label={`${nodeLabel} output`}
          />
        ) : appearance.showPreview !== false && artifactId ? (
          <ArtifactThumbnail
            artifactId={artifactId}
            schemaId={data.schemaId}
            effect={String(appearance.imageEffect || "none")}
            fit={String(appearance.imageFit || "cover")}
            ratio="square"
            label={`${nodeLabel} output`}
          />
        ) : (
          <div className="midgard-node-stage" aria-hidden>
            {!showPromptField && (
              <ImageIcon className="midgard-node-stage-glyph" />
            )}
          </div>
        )}

        {showPromptField && promptParam && (
          <div className="midgard-node-prompt">
            <Type aria-hidden className="size-3.5 shrink-0 text-mg-muted" />
            <textarea
              className="nodrag nowheel"
              rows={2}
              placeholder={
                promptParam.description ||
                `Describe the ${definition.category?.split("/")[0]?.toLowerCase() || "result"} you want…`
              }
              aria-label={promptParam.label || "Prompt"}
              disabled={data.disabled || busy}
              value={String(data.parameters?.[promptParam.id] ?? "")}
              onPointerDown={stopPointer}
              onClick={stopPointer}
              onKeyDown={stopPointer}
              onChange={(event) => {
                event.stopPropagation();
                actions.onParameterChange?.(id, promptParam.id, event.target.value);
              }}
            />
          </div>
        )}
      </div>

      {(status === "RUNNING" || status === "PAUSE_REQUESTED") && (
        <div className="midgard-node-progress">
          <ProgressBar
            value={state?.progress || 0}
            label={state?.message || `${nodeLabel} progress`}
            showLabel
          />
        </div>
      )}

      <footer className="midgard-node-footer">
        <div className="midgard-node-footer-options">
          {footerParams.map((parameter) => {
            const isModel =
              parameter.id === "model" || parameter.type === "model";
            if (isModel) {
              const options = [
                ...(!modelAvailable && modelValue
                  ? [
                      {
                        value: String(modelValue),
                        label: `${modelLabel} (disabled)`,
                        disabled: true,
                      },
                    ]
                  : []),
                ...(!modelOptions.length && !modelValue
                  ? [
                      {
                        value: "",
                        label: "No enabled model",
                        disabled: true,
                      },
                    ]
                  : []),
                ...modelOptions.map((option) => ({
                  value: String(option.value),
                  label: option.label,
                  disabled: option.disabled,
                })),
              ];
              return (
                <Select
                  key={parameter.id}
                  bare
                  controlSize="sm"
                  aria-label={`Model for ${nodeLabel}`}
                  title={`Model for ${nodeLabel}`}
                  value={String(modelValue ?? "")}
                  options={options}
                  disabled={data.disabled || busy || !modelOptions.length}
                  className="nodrag nowheel"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={(event) => event.stopPropagation()}
                  onKeyDown={(event) => event.stopPropagation()}
                  onChange={(event) => {
                    event.stopPropagation();
                    const option = modelOptions.find(
                      (candidate) =>
                        String(candidate.value) === event.target.value,
                    );
                    if (option) actions.onModelChange?.(id, option.value);
                  }}
                />
              );
            }
            const raw = data.parameters?.[parameter.id] ?? parameter.default;
            const options = (parameter.options || []).map((option) => ({
              value: String(option.value),
              label: option.label,
              disabled: option.disabled,
            }));
            if (!options.length) return null;
            return (
              <Select
                key={parameter.id}
                bare
                controlSize="sm"
                aria-label={parameter.label}
                title={parameter.label}
                value={String(raw ?? "")}
                options={options}
                disabled={data.disabled || busy}
                className="nodrag nowheel"
                onPointerDown={(event) => event.stopPropagation()}
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
                onChange={(event) => {
                  event.stopPropagation();
                  const option = parameter.options?.find(
                    (candidate) =>
                      String(candidate.value) === event.target.value,
                  );
                  actions.onParameterChange?.(
                    id,
                    parameter.id,
                    option ? option.value : event.target.value,
                  );
                }}
              />
            );
          })}
          <button
            type="button"
            className="nodrag nowheel midgard-node-gear"
            aria-label={`Open ${nodeLabel} options`}
            title="Node options"
            onPointerDown={stopPointer}
            onClick={(event) => {
              event.stopPropagation();
              actions.onOpen?.(id);
            }}
          >
            <Settings2 className="size-4.5" />
          </button>
        </div>

        <div className="midgard-node-footer-actions">
          {artifactId && (
            <button
              type="button"
              className="nodrag nowheel midgard-node-gear"
              aria-label={`Preview ${nodeLabel} image`}
              title="Preview image"
              onPointerDown={stopPointer}
              onClick={(event) => {
                event.stopPropagation();
                actions.onPreview?.(id);
              }}
            >
              <Eye className="size-4.5" />
            </button>
          )}
          <button
            type="button"
            className="nodrag nowheel midgard-node-run"
            aria-label={`${runLabel} ${nodeLabel}`}
            title={runLabel}
            disabled={data.disabled || busy}
            onPointerDown={stopPointer}
            onClick={(event) => {
              event.stopPropagation();
              actions.onRun?.(id);
            }}
          >
            <Play className="size-4 fill-current" />
          </button>
        </div>
      </footer>
    </article>
  );
}

export const MidgardNode = memo(MidgardNodeComponent);
