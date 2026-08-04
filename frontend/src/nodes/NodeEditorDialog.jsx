import {
  Box,
  Check,
  Cpu,
  Database,
  Image as ImageIcon,
  Settings2,
  Sparkles,
} from "lucide-react";
import { ArtifactPreview } from "../preview/ArtifactPreview";
import {
  Badge,
  Button,
  Checkbox,
  Dialog,
  EmptyState,
  IconTile,
  TextField,
} from "../components";
import { useEditorStore } from "../state/editorStore";
import { useRunStore } from "../state/runStore";
import { useServerStore } from "../state/serverStore";
import { NodeParameterField } from "./NodeParameterField";
import { enabledModelOptions, inventoryForOption } from "../models/modelAvailability";

/** @param {{option: import("../types").ParameterOption, selected: boolean, inventory?: Record<string, any>, onSelect: () => void}} props */
function ModelRow({ option, selected, inventory, onSelect }) {
  const installed = inventory?.installed;
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={`ui-nav-item h-auto items-start py-2 ${selected ? "is-active" : ""}`}
    >
      <span
        className={`mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border ${selected ? "border-mg-accent bg-mg-accent text-white" : "border-mg-border text-transparent"}`}
      >
        <Check className="ui-icon-xs" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="ui-actions">
          <strong className="ui-copy-title truncate text-[12px]">
            {option.label}
          </strong>
          {installed !== undefined && (
            <Badge size="xs" tone={installed ? "success" : "neutral"}>
              {installed ? "Installed" : "On demand"}
            </Badge>
          )}
        </span>
        {option.description && (
          <span className="ui-copy-muted mt-0.5 block leading-4">
            {option.description}
          </span>
        )}
        {inventory && (
          <span className="ui-copy-muted mt-1 ui-inline gap-1">
            <Cpu className="ui-icon-xs" />
            {inventory.framework || inventory.capability || "Local model"}
            {inventory.minimum_vram_mb
              ? ` · ${Math.round(inventory.minimum_vram_mb / 1024)} GB VRAM`
              : ""}
          </span>
        )}
      </span>
    </button>
  );
}

/** @param {{ids?: string[], models: Record<string, any>[]}} props */
function RequiredModels({ ids, models }) {
  if (!ids?.length) return null;
  return (
    <div className="ui-stack-xs">
      <span className="ui-field-label">Required runtime</span>
      {ids.map((id) => {
        const model = models.find((item) => item.id === id);
        return (
          <div key={id} className="ui-inline py-1">
            <Database className="ui-icon-sm text-mg-muted" />
            <span className="ui-copy-body min-w-0 flex-1 truncate">
              {model?.name || id}
            </span>
            <Badge tone={model?.installed ? "success" : "neutral"}>
              {model?.installed ? "Ready" : "On demand"}
            </Badge>
          </div>
        );
      })}
    </div>
  );
}

/** @param {{nodeId: string | null, onClose: () => void, onManageModels: () => void}} props */
export function NodeEditorDialog({ nodeId, onClose, onManageModels }) {
  const node = useEditorStore((store) =>
    store.nodes.find((item) => item.id === nodeId),
  );
  const update = useEditorStore((store) => store.updateNode);
  const models = useServerStore((store) => store.models);
  const liveRun = useRunStore((store) =>
    nodeId ? store.nodeStates[nodeId] : null,
  );
  if (!node) return null;
  const activeNode = node;

  const definition = node.data.definition;
  const parameters = definition?.parameters || [];
  const modelParameter = parameters.find(
    (parameter) => parameter.type === "model" || parameter.id === "model",
  );
  const allModelOptions = modelParameter?.options || [];
  const modelOptions = enabledModelOptions(allModelOptions, models);
  const currentModel =
    node.data.parameters?.model ||
    modelParameter?.default ||
    modelOptions[0]?.value ||
    "";
  const selectedOption = modelOptions.find(
    (option) => option.value === currentModel,
  );
  const effectiveRequiredModels = selectedOption?.modelId
    ? [selectedOption.modelId]
    : definition?.requiredModels || [];
  const operationParameters = parameters.filter(
    (parameter) => parameter.id !== "model",
  );
  const persistedResult = node.data.result;
  const artifactIds = liveRun?.artifactIds?.length
    ? liveRun.artifactIds
    : persistedResult?.artifactIds || [];
  const artifactId = artifactIds.at(-1);
  const status = liveRun?.status || persistedResult?.status || "IDLE";

  function setParameter(
    /** @type {import("../types").ParameterDefinition | undefined} */ parameter,
    /** @type {unknown} */ value,
    /** @type {import("../types").DesktopGrant | import("../types").DesktopGrant[] | undefined} */ selection = undefined,
  ) {
    if (!parameter) return;
    /** @type {Partial<import("../types").WorkflowNodeData>} */
    const changes = {
      parameters: { ...activeNode.data.parameters, [parameter.id]: value },
    };
    const selections = Array.isArray(selection)
      ? selection
      : selection
        ? [selection]
        : [];
    const artifactIds = selections.flatMap((item) =>
      item.artifactId ? [item.artifactId] : [],
    );
    if (artifactIds.length) {
      useRunStore.getState().clearNodeResult(activeNode.id);
      changes.result = {
        status: "READY",
        artifactIds,
        sourceName:
          selections.length === 1
            ? selections[0].name
            : `${selections.length} images`,
        completedAt: new Date().toISOString(),
      };
    }
    update(activeNode.id, changes);
  }

  return (
    <Dialog
      open
      onClose={onClose}
      wide
      className="!max-w-6xl"
      title={definition?.name || node.data.label}
      bodyClassName="!max-h-[72vh] !overflow-hidden !p-0"
      footer={
        <Button variant="secondary" onClick={onClose}>
          Done
        </Button>
      }
    >
      <div className="grid h-[62vh] min-h-[30rem] grid-cols-[15rem_minmax(15rem,0.85fr)_minmax(0,1.15fr)]">
        <aside className="ui-settings-nav border-r p-3.5">
          <div className="ui-inline mb-2.5">
            <IconTile size="sm">
              <Sparkles className="ui-icon-sm" />
            </IconTile>
            <div>
              <h3 className="ui-copy-title text-[11px]">Model</h3>
              <p className="ui-copy-muted">Stored with this node</p>
            </div>
          </div>
          {modelOptions.length ? (
            <div className="ui-stack-xs">
              {modelOptions.map((option) => (
                <ModelRow
                  key={option.value}
                  option={option}
                  selected={option.value === currentModel}
                  inventory={inventoryForOption(option, models)}
                  onSelect={() => setParameter(modelParameter, option.value)}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<Box className="ui-icon-lg" />}
              title={modelParameter ? "No enabled model" : "No model choice"}
              description={
                modelParameter
                  ? "Install and enable a compatible model in Model settings."
                  : definition?.requiredModels?.length
                    ? "This operation uses its required bundled model."
                    : "This node does not run an AI model."
              }
              compact
            />
          )}
          <div className="mt-3">
            <RequiredModels ids={effectiveRequiredModels} models={models} />
          </div>
          {effectiveRequiredModels?.length > 0 && (
            <Button
              variant="secondary"
              className="mt-2 w-full"
              onClick={onManageModels}
            >
              Manage local models
            </Button>
          )}
        </aside>

        <section className="ui-settings-main border-r p-4">
          <div className="ui-inline mb-3">
            <IconTile size="sm">
              <Settings2 className="ui-icon-sm" />
            </IconTile>
            <div className="min-w-0 flex-1">
              <h3 className="ui-copy-title text-[11px] text-mg-secondary">
                Node settings
              </h3>
              <p className="ui-copy-muted text-[9px]">
                These values belong only to this node instance.
              </p>
            </div>
            <Badge
              tone={
                status === "FAILED"
                  ? "error"
                  : status === "RUNNING"
                    ? "running"
                    : ["SUCCEEDED", "CACHED"].includes(status)
                      ? "success"
                      : "neutral"
              }
            >
              {status}
            </Badge>
          </div>
          <div className="ui-stack">
            <TextField
              label="Node label"
              value={node.data.label || ""}
              onChange={(event) =>
                update(node.id, { label: event.target.value })
              }
            />
            {selectedOption && (
              <p className="ui-copy-muted">
                Selected model{" "}
                <span className="font-medium text-mg-primary">
                  {selectedOption.label}
                </span>
              </p>
            )}
            {operationParameters.length ? (
              <div className="grid grid-cols-2 gap-3">
                {operationParameters.map((parameter) => (
                  <div
                    key={parameter.id}
                    className={
                      parameter.type === "textarea" ||
                      parameter.type === "json" ||
                      parameter.type === "file" ||
                      parameter.type === "files" ||
                      parameter.type === "saveFile"
                        ? "col-span-2"
                        : ""
                    }
                  >
                    <NodeParameterField
                      definition={parameter}
                      nodeDefinition={definition}
                      value={node.data.parameters?.[parameter.id]}
                      selectedName={
                        ["file", "files"].includes(parameter.type)
                          ? node.data.result?.sourceName
                          : undefined
                      }
                      onChange={(value, selection) =>
                        setParameter(parameter, value, selection)
                      }
                    />
                  </div>
                ))}
              </div>
            ) : (
              <p className="ui-copy-muted">
                This node has no additional operation settings.
              </p>
            )}
            <Checkbox
              label="Disable node"
              checked={Boolean(node.data.disabled)}
              onChange={(event) =>
                update(node.id, { disabled: event.target.checked })
              }
            />
          </div>
        </section>

        <aside className="flex min-h-0 flex-col overflow-hidden p-4">
          <div className="ui-inline mb-2.5">
            <IconTile size="sm">
              <ImageIcon className="ui-icon-sm" />
            </IconTile>
            <h3 className="ui-copy-title text-[11px] text-mg-secondary">
              Preview
            </h3>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <ArtifactPreview
              artifactId={artifactId}
              artifactIds={artifactIds}
              schemaId={node.data.schemaId}
              effect={String(node.data.appearance?.imageEffect || "none")}
            />
          </div>
        </aside>
      </div>
    </Dialog>
  );
}
