import { memo, useState } from "react";
import * as XYFlow from "@xyflow/react";
import { ProgressBar, Badge, Switch } from "../components";
import {
  ChevronDown,
  Eye,
  Minus,
  Play,
  Plus,
  Settings2,
  resolveCategoryColor,
  resolveNodeIcon,
  resolvePortColor,
  resolvePortIcon,
  resolveStatusIcon,
} from "../icons";
import { ArtifactThumbGrid, ArtifactThumbnail } from "../preview/ArtifactPreview";
import { useRunStore } from "../state/runStore";
import { useNodeActionsContext } from "./NodeActionsContext";
import {
  enabledModelOptions,
  selectedModelOption as resolveSelectedModelOption,
} from "../models/modelAvailability";
import {
  capabilityContract,
  parametersForCapabilities,
} from "../models/modelCapabilities";

const SETTINGS_CARD_SCHEMAS = new Set(["lluna.input.llava"]);

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
  STALE: "warning",
};

/**
 * Outside connection circle for linking ports.
 * @param {{port: import("../types").PortDefinition, side: "input"|"output", top: string, active: boolean}} props
 */
function PortCircle({ port, side, top, active }) {
  const output = side === "output";
  const Icon = resolvePortIcon(port.type);
  const color = resolvePortColor(port.type);
  return (
    <XYFlow.Handle
      id={port.id}
      type={output ? "source" : "target"}
      position={output ? XYFlow.Position.Right : XYFlow.Position.Left}
      className={`lluna-port-handle ${active ? "is-active" : ""} ${port.multiple ? "is-multiple" : ""} ${output ? "is-output" : "is-input"}`}
      data-port-type={port.type}
      data-multiple={port.multiple ? "true" : "false"}
      style={/** @type {import("react").CSSProperties} */ ({ top, "--port-color": color })}
      aria-label={`${port.label}, ${port.type}${port.multiple ? ", queue" : ""}`}
      title={`${port.label} · ${port.type}${port.multiple ? " queue" : ""}`}
    >
      <Icon aria-hidden className="lluna-port-glyph" style={{ color }} />
    </XYFlow.Handle>
  );
}

/**
 * Compact pill select for the node toolbar.
 * @param {{
 *   label: string,
 *   value: string,
 *   disabled?: boolean,
 *   options: {value: string, label: string, disabled?: boolean}[],
 *   onChange: (value: string) => void,
 *   stopPointer: (event: import("react").SyntheticEvent) => void,
 * }} props
 */
function PillSelect({ label, value, disabled, options, onChange, stopPointer }) {
  const selected = options.find((option) => option.value === value);
  return (
    <label className="lluna-node-pill nodrag nowheel" title={label}>
      <span className="lluna-node-pill-label">{selected?.label || label}</span>
      <ChevronDown aria-hidden className="lluna-node-pill-chevron" />
      <select
        aria-label={label}
        disabled={disabled}
        value={value}
        onPointerDown={stopPointer}
        onClick={stopPointer}
        onKeyDown={stopPointer}
        onChange={(event) => {
          event.stopPropagation();
          onChange(event.target.value);
        }}
      >
        {options.map((option) => (
          <option
            key={option.value}
            value={option.value}
            disabled={option.disabled}
          >
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * Compact − xN + stepper for small integer ranges.
 * @param {{
 *   label: string,
 *   value: number,
 *   min?: number,
 *   max?: number,
 *   step?: number,
 *   disabled?: boolean,
 *   onChange: (value: number) => void,
 *   stopPointer: (event: import("react").SyntheticEvent) => void,
 * }} props
 */
function QuantityStepper({
  label,
  value,
  min = 1,
  max = 8,
  step = 1,
  disabled,
  onChange,
  stopPointer,
}) {
  const clamp = (/** @type {number} */ next) =>
    Math.min(max, Math.max(min, next));
  return (
    <div
      className="lluna-node-stepper nodrag nowheel"
      title={label}
      onPointerDown={stopPointer}
    >
      <button
        type="button"
        aria-label={`Decrease ${label}`}
        disabled={disabled || value <= min}
        onClick={(event) => {
          event.stopPropagation();
          onChange(clamp(value - step));
        }}
      >
        <Minus aria-hidden />
      </button>
      <span aria-label={label}>x{value}</span>
      <button
        type="button"
        aria-label={`Increase ${label}`}
        disabled={disabled || value >= max}
        onClick={(event) => {
          event.stopPropagation();
          onChange(clamp(value + step));
        }}
      >
        <Plus aria-hidden />
      </button>
    </div>
  );
}

/** @param {import("../types").ParameterDefinition} parameter */
function isQuantityParam(parameter) {
  if (parameter.type !== "integer" && parameter.type !== "number") return false;
  const id = parameter.id.toLowerCase();
  if (/(count|batch|quantity|numimages|num_images|samples)/.test(id)) {
    return true;
  }
  const max = parameter.maximum;
  const min = parameter.minimum ?? 0;
  return typeof max === "number" && max - min <= 16 && max <= 32;
}

/**
 * Expand a bounded integer parameter into toolbar choices. Generation steps
 * are commonly expressed as a range in model manifests rather than as a
 * fixed option list, but still need to be selectable without opening the
 * full node dialog.
 * @param {import("../types").ParameterDefinition | undefined} parameter
 */
function integerParameterOptions(parameter) {
  if (!parameter) return [];
  if (parameter.options?.length) return parameter.options;
  const minimum = Number(parameter.minimum);
  const maximum = Number(parameter.maximum);
  const step = Number(parameter.step ?? 1);
  if (
    parameter.type !== "integer" ||
    !Number.isFinite(minimum) ||
    !Number.isFinite(maximum) ||
    !Number.isFinite(step) ||
    step <= 0 ||
    maximum < minimum ||
    Math.floor((maximum - minimum) / step) + 1 > 100
  )
    return [];
  return Array.from(
    { length: Math.floor((maximum - minimum) / step) + 1 },
    (_, index) => {
      const value = minimum + index * step;
      return { value, label: String(value) };
    },
  );
}

/** @param {{items: import("../types").SaveProgressItem[]}} props */
function SaveProgressList({ items }) {
  return (
    <div className="lluna-save-progress-list">
      {items.map((item, index) => {
        const finished = item.status === "FINISHED";
        const failed = item.status === "FAILED";
        const label = item.name || `Image ${index + 1}`;
        const statusLabel = finished
          ? "Finished"
          : failed
            ? "Failed"
            : item.status === "PENDING"
              ? "Waiting"
              : "Saving";
        return (
          <div
            key={`${item.index}-${label}`}
            className={`lluna-save-progress-item ${finished ? "is-finished" : ""} ${failed ? "is-failed" : ""}`}
          >
            <div className="lluna-save-progress-heading">
              <span title={label}>{label}</span>
              <strong>
                {statusLabel}
                <span className="lluna-save-progress-pct">
                  {Math.round(item.progress)}%
                </span>
              </strong>
            </div>
            <ProgressBar
              value={item.progress}
              label={`${label} save progress`}
            />
          </div>
        );
      })}
    </div>
  );
}

/** @param {import("@xyflow/react").NodeProps<import("../types").EditorNode>} props */
function LlunaNodeComponent({ id, data, selected }) {
  const state = useRunStore((store) => store.nodeStates[id]);
  const { actions, modelInventory } = useNodeActionsContext();
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
  const StatusIcon = resolveStatusIcon(status);
  const HeaderIcon = resolveNodeIcon(definition.icon);
  const accent = resolveCategoryColor(definition.category);
  const busy = status === "RUNNING" || status === "QUEUED";
  const previewImage = state?.previewImage;
  const showPorts = selected || hovered || busy;
  const nodeLabel = data.label || definition.name;
  const runLabel = definition.kind === "input" ? "Run" : "Run from here";
  const parameters = definition.parameters || [];
  const modelParameter = parameters.find(
    (parameter) => parameter.id === "model" || parameter.type === "model",
  );
  const modelValue = data.parameters?.model || modelParameter?.default;
  const modelOptions = enabledModelOptions(
    modelParameter?.options || [],
    modelInventory || [],
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
  const selectedOption = resolveSelectedModelOption(
    modelParameter?.options || [],
    modelOptions,
    modelValue,
  );
  const selectedCapabilities = capabilityContract(selectedOption);
  const visibleParameters = parametersForCapabilities(
    parameters,
    selectedCapabilities,
    String(modelValue || ""),
  );
  const llavaToggle = visibleParameters.find(
    (parameter) => parameter.id === "useLlava",
  );
  const showLlavaToggle = modelValue === "SUPIR" && Boolean(llavaToggle);
  const isSettingsCard = SETTINGS_CARD_SCHEMAS.has(definition.schemaId);
  const isSelectObject = definition.schemaId === "lluna.mask.select_object";
  const quantityParam = visibleParameters.find(isQuantityParam);
  const stepsParam = visibleParameters.find(
    (parameter) => parameter.id === "steps",
  );
  const footerParams = visibleParameters.filter((parameter) => {
    if (isSettingsCard) return false;
    if (quantityParam && parameter.id === quantityParam.id) return false;
    if (stepsParam && parameter.id === stepsParam.id) return false;
    if (parameter.id === "model" || parameter.type === "model") return true;
    if (parameter.type === "select" || parameter.type === "enum") return true;
    return Boolean(parameter.options?.length);
  });
  const promptParam = visibleParameters.find((parameter) => {
    const id = parameter.id.toLowerCase();
    if (id.includes("negative")) return false;
    return (
      id === "value" ||
      id === "prompt" ||
      id === "text" ||
      id === "question" ||
      (parameter.type === "textarea" &&
        (id.includes("prompt") || id.includes("instruction") || id.includes("caption")))
    );
  });
  const showPromptField =
    Boolean(promptParam) &&
    (isSettingsCard ||
      definition.kind === "input" ||
      definition.schemaId?.includes("prompt") ||
      definition.schemaId?.includes("llava") ||
      isSelectObject);
  const bodySettings = isSettingsCard
    ? visibleParameters.filter(
        (parameter) =>
          parameter.id !== promptParam?.id &&
          (["number", "integer", "boolean", "select", "enum"].includes(
            parameter.type,
          ) ||
            Boolean(parameter.options?.length)),
      )
    : [];
  const supportsPreview = definition.supportsPreview === true;
  const isPreviewOutput = definition.schemaId.startsWith(
    "lluna.output.preview_",
  );
  const isSaveImage = definition.schemaId === "lluna.output.save_image";
  const reportedSaveItems = state
    ? state.saveItems || []
    : persistedResult?.saveItems || [];
  const saveItems = reportedSaveItems.length
    ? reportedSaveItems
    : isSaveImage &&
        artifactIds.length &&
        ["SUCCEEDED", "CACHED"].includes(status)
      ? artifactIds.map((_, index) => ({
          index,
          name: artifactIds.length === 1 ? "Saved image" : `Image ${index + 1}`,
          progress: 100,
          status: "FINISHED",
          detail: "Saved successfully",
        }))
      : [];
  const showPreview =
    !isSettingsCard &&
    supportsPreview &&
    appearance.showPreview !== false &&
    (Boolean(artifactId) || artifactIds.length > 1 || !showPromptField);
  const showNodeBody =
    isSettingsCard || showPreview || showPromptField || saveItems.length > 0;
  const promptFirst = showPromptField && !isSettingsCard;
  const inputs = definition.inputs || [];
  const outputs = definition.outputs || [];
  /** @param {import("react").SyntheticEvent} event */
  const stopPointer = (event) => event.stopPropagation();
  /** @param {string} parameterId @param {unknown} value */
  const setParameter = (parameterId, value) => {
    actions.onParameterChange?.(id, parameterId, value);
  };

  /** @param {number} index @param {number} total */
  const portTop = (index, total) =>
    total <= 1 ? "50%" : `${((index + 1) / (total + 1)) * 100}%`;

  const quantityValue = Number(
    data.parameters?.[quantityParam?.id || ""] ??
      quantityParam?.default ??
      1,
  );
  const stepsValue = Number(
    data.parameters?.[stepsParam?.id || ""] ?? stepsParam?.default,
  );
  const supportedStepOptions = integerParameterOptions(stepsParam);
  const stepOptions = [
    ...(!supportedStepOptions.some(
      (option) => Number(option.value) === stepsValue,
    ) && Number.isFinite(stepsValue)
      ? [
          {
            value: String(stepsValue),
            label: `${stepsValue} steps (unsupported)`,
            disabled: true,
          },
        ]
      : []),
    ...supportedStepOptions.map((option) => ({
      value: String(option.value),
      label: `${option.label || option.value} steps`,
      disabled: "disabled" in option ? option.disabled : false,
    })),
  ];

  return (
    <article
      aria-label={`${nodeLabel} node`}
      title={
        isPreviewOutput
          ? "Open the media preview or connect another step"
          : "Use the settings button to edit this node"
      }
      className={`lluna-node ${selected ? "is-selected" : ""} ${data.disabled ? "is-disabled" : ""} ${showPorts ? "is-ports-open" : ""} ${promptFirst ? "is-prompt" : ""} ${isSettingsCard ? "is-settings-card" : ""}`}
      style={/** @type {import("react").CSSProperties} */ ({ "--node-accent": accent })}
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

      <div className="lluna-node-chrome">
        <button
          type="button"
          className="nodrag nowheel lluna-node-chip"
          aria-label={
            status !== "IDLE" && status !== "SUCCEEDED"
              ? `${nodeLabel} status ${status.replaceAll("_", " ")}`
              : isPreviewOutput
                ? `Open ${nodeLabel} preview`
                : `Open ${nodeLabel} options`
          }
          title={nodeLabel}
          onPointerDown={stopPointer}
          onClick={(event) => {
            event.stopPropagation();
            if (isPreviewOutput) actions.onPreview?.(id);
            else actions.onOpen?.(id);
          }}
        >
          {status !== "IDLE" && status !== "SUCCEEDED" ? (
            <StatusIcon
              className={status === "RUNNING" ? "animate-spin" : undefined}
            />
          ) : isPreviewOutput ? (
            <Eye aria-hidden />
          ) : (
            <Settings2 aria-hidden />
          )}
        </button>
        <strong className="lluna-node-title">{nodeLabel}</strong>
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
      </div>

      {showNodeBody && (
        <div
          className={`lluna-node-body ${isSettingsCard ? "is-settings" : ""} ${isSaveImage ? "is-save" : ""} ${promptFirst && !showPreview ? "is-prompt" : ""}`}
          onClick={
            supportsPreview
              ? (event) => {
                  event.stopPropagation();
                  actions.onPreview?.(id);
                }
              : undefined
          }
        >
          {isSaveImage ? (
            <SaveProgressList items={saveItems} />
          ) : isSettingsCard ? (
          <div className="lluna-node-settings">
            {showPromptField && promptParam && (
              <label className="lluna-node-settings-field">
                <span>{promptParam.label || "Instruction"}</span>
                <textarea
                  className="ui-input is-area nodrag nowheel"
                  rows={4}
                  placeholder={
                    promptParam.description ||
                    "Describe what LLaVA should caption…"
                  }
                  aria-label={promptParam.label || "Instruction"}
                  disabled={data.disabled || busy}
                  value={String(
                    data.parameters?.[promptParam.id] ??
                      promptParam.default ??
                      "",
                  )}
                  onPointerDown={stopPointer}
                  onClick={stopPointer}
                  onKeyDown={stopPointer}
                  onChange={(event) => {
                    event.stopPropagation();
                    setParameter(promptParam.id, event.target.value);
                  }}
                />
              </label>
            )}
            {bodySettings.map((parameter) => {
              const raw =
                data.parameters?.[parameter.id] ?? parameter.default;
              if (parameter.type === "boolean") {
                return (
                  <div
                    key={parameter.id}
                    className="lluna-node-settings-field is-switch"
                    onPointerDown={stopPointer}
                  >
                    <Switch
                      label={parameter.label}
                      checked={Boolean(raw)}
                      disabled={data.disabled || busy}
                      onChange={(checked) =>
                        setParameter(parameter.id, checked)
                      }
                    />
                  </div>
                );
              }
              if (
                parameter.type === "select" ||
                parameter.type === "enum" ||
                parameter.options?.length
              ) {
                const options = parameter.options || [];
                if (!options.length) return null;
                return (
                  <label
                    key={parameter.id}
                    className="lluna-node-settings-field is-inline"
                  >
                    <span>{parameter.label}</span>
                    <select
                      className="ui-input nodrag nowheel"
                      aria-label={parameter.label}
                      disabled={data.disabled || busy}
                      value={String(raw ?? "")}
                      onPointerDown={stopPointer}
                      onClick={stopPointer}
                      onKeyDown={stopPointer}
                      onChange={(event) => {
                        event.stopPropagation();
                        const option = options.find(
                          (candidate) =>
                            String(candidate.value) === event.target.value,
                        );
                        setParameter(
                          parameter.id,
                          option ? option.value : event.target.value,
                        );
                      }}
                    >
                      {options.map((option) => (
                        <option
                          key={String(option.value)}
                          value={String(option.value)}
                          disabled={option.disabled}
                        >
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                );
              }
              return (
                <label
                  key={parameter.id}
                  className="lluna-node-settings-field is-inline"
                >
                  <span>{parameter.label}</span>
                  <input
                    type="number"
                    className="ui-input nodrag nowheel"
                    min={parameter.minimum}
                    max={parameter.maximum}
                    step={
                      parameter.step ||
                      (parameter.type === "integer" ? 1 : "any")
                    }
                    aria-label={parameter.label}
                    disabled={data.disabled || busy}
                    value={raw == null ? "" : String(raw)}
                    onPointerDown={stopPointer}
                    onClick={stopPointer}
                    onKeyDown={stopPointer}
                    onChange={(event) => {
                      event.stopPropagation();
                      const next =
                        parameter.type === "integer"
                          ? Number.parseInt(event.target.value || "0", 10)
                          : Number(event.target.value);
                      setParameter(
                        parameter.id,
                        Number.isFinite(next) ? next : parameter.default,
                      );
                    }}
                  />
                </label>
              );
            })}
          </div>
        ) : (
          <>
            {showPreview && busy && previewImage ? (
              // Live mid-generation frame takes priority over any stale
              // completed-result thumbnail from a previous run of this node.
              <img
                src={previewImage}
                alt={`${nodeLabel} generating…`}
                className={`min-h-[196px] flex-1 ${String(appearance.imageFit || "cover") === "contain" ? "object-contain" : "object-cover"}`}
              />
            ) : showPreview && artifactIds.length > 1 ? (
              <ArtifactThumbGrid
                artifactIds={artifactIds}
                schemaId={data.schemaId}
                effect={String(appearance.imageEffect || "none")}
                fit={String(appearance.imageFit || "cover")}
                label={`${nodeLabel} output`}
              />
            ) : showPreview && artifactId ? (
              <ArtifactThumbnail
                artifactId={artifactId}
                schemaId={data.schemaId}
                effect={String(appearance.imageEffect || "none")}
                fit={String(appearance.imageFit || "cover")}
                ratio="square"
                label={`${nodeLabel} output`}
              />
            ) : showPreview ? (
              <div className="lluna-node-stage" aria-hidden>
                <HeaderIcon
                  className="lluna-node-stage-glyph"
                  style={{ color: accent }}
                />
              </div>
            ) : null}

            {showPromptField && promptParam && (
              <div className="lluna-node-prompt">
                <textarea
                  className="nodrag nowheel"
                  rows={promptFirst && !showPreview ? 4 : 2}
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
                    setParameter(promptParam.id, event.target.value);
                  }}
                />
              </div>
            )}
          </>
          )}
        </div>
      )}

      {!isSaveImage &&
        (status === "RUNNING" || status === "PAUSE_REQUESTED") && (
        <div className="lluna-node-progress">
          <ProgressBar
            value={state?.progress || 0}
            label={state?.message || `${nodeLabel} progress`}
            showLabel
          />
        </div>
        )}

      <footer className="lluna-node-footer">
        <div className="lluna-node-toolbar">
          {quantityParam && Number.isFinite(quantityValue) && (
            <QuantityStepper
              label={quantityParam.label}
              value={Math.round(quantityValue)}
              min={quantityParam.minimum ?? 1}
              max={quantityParam.maximum ?? 8}
              step={
                typeof quantityParam.step === "number"
                  ? quantityParam.step
                  : 1
              }
              disabled={data.disabled || busy}
              onChange={(value) => setParameter(quantityParam.id, value)}
              stopPointer={stopPointer}
            />
          )}

          {stepsParam && stepOptions.length > 0 && (
            <PillSelect
              label={stepsParam.label || "Steps"}
              value={String(stepsValue)}
              disabled={data.disabled || busy}
              options={stepOptions}
              stopPointer={stopPointer}
              onChange={(next) => setParameter(stepsParam.id, Number(next))}
            />
          )}

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
                <PillSelect
                  key={parameter.id}
                  label={`Model for ${nodeLabel}`}
                  value={String(modelValue ?? "")}
                  disabled={data.disabled || busy || !modelOptions.length}
                  options={options}
                  stopPointer={stopPointer}
                  onChange={(next) => {
                    const option = modelOptions.find(
                      (candidate) => String(candidate.value) === next,
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
              <PillSelect
                key={parameter.id}
                label={parameter.label}
                value={String(raw ?? "")}
                disabled={data.disabled || busy}
                options={options}
                stopPointer={stopPointer}
                onChange={(next) => {
                  const option = parameter.options?.find(
                    (candidate) => String(candidate.value) === next,
                  );
                  actions.onParameterChange?.(
                    id,
                    parameter.id,
                    option ? option.value : next,
                  );
                }}
              />
            );
          })}

          {showLlavaToggle && llavaToggle && (
            <div
              className="nodrag nowheel lluna-node-llava-toggle"
              title={llavaToggle.description}
              onPointerDown={stopPointer}
              onClick={stopPointer}
              onKeyDown={stopPointer}
            >
              <Switch
                label="LLaVA"
                checked={Boolean(
                  data.parameters?.[llavaToggle.id] ?? llavaToggle.default,
                )}
                disabled={data.disabled || busy}
                onChange={(checked) =>
                  setParameter(llavaToggle.id, checked)
                }
              />
            </div>
          )}
        </div>

        <div className="lluna-node-footer-actions">
          {supportsPreview && (
            <button
              type="button"
              className="nodrag nowheel lluna-node-icon-btn"
              aria-label={`Preview ${nodeLabel} image`}
              title="Preview image"
              onPointerDown={stopPointer}
              onClick={(event) => {
                event.stopPropagation();
                actions.onPreview?.(id);
              }}
            >
              <Eye />
            </button>
          )}
          {!isPreviewOutput && (
            <button
              type="button"
              className="nodrag nowheel lluna-node-icon-btn"
              aria-label={`Open ${nodeLabel} options`}
              title="Node options"
              onPointerDown={stopPointer}
              onClick={(event) => {
                event.stopPropagation();
                actions.onOpen?.(id);
              }}
            >
              <Settings2 />
            </button>
          )}
          <button
            type="button"
            className="nodrag nowheel lluna-node-run"
            aria-label={`${runLabel} ${nodeLabel}`}
            title={runLabel}
            disabled={data.disabled || busy}
            onPointerDown={stopPointer}
            onClick={(event) => {
              event.stopPropagation();
              actions.onRun?.(id);
            }}
          >
            <Play className="fill-current" />
          </button>
        </div>
      </footer>
    </article>
  );
}

export const LlunaNode = memo(LlunaNodeComponent);
