import {
  Box,
  Database,
  Settings2,
  resolveCategoryColor,
  resolveNodeIcon,
  resolveSectionIcon,
} from "../icons";
import { ArtifactPreview } from "../preview/ArtifactPreview";
import {
  Badge,
  Button,
  Checkbox,
  Dialog,
  EmptyState,
  IconTile,
  Select,
  TextField,
} from "../components";
import { useEditorStore } from "../state/editorStore";
import { useRunStore } from "../state/runStore";
import { useServerStore } from "../state/serverStore";
import { NodeParameterField } from "./NodeParameterField";
import { enabledModelOptions } from "../models/modelAvailability";
import {
  applyCapabilityDefaults,
  capabilityContract,
  parametersForCapabilities,
} from "../models/modelCapabilities";

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
  const selectedCapabilities = capabilityContract(selectedOption);
  const effectiveRequiredModels = selectedOption?.modelId
    ? [selectedOption.modelId]
    : definition?.requiredModels || [];
  const operationParameters = parametersForCapabilities(
    parameters.filter(
      (parameter) =>
        parameter.id !== "model" &&
        !(
          definition?.schemaId === "midgard.mask.select_object" &&
          ["points", "labels"].includes(parameter.id)
        ),
    ),
    selectedCapabilities,
    String(currentModel),
  );
  const persistedResult = node.data.result;
  const artifactIds = liveRun?.artifactIds?.length
    ? liveRun.artifactIds
    : persistedResult?.artifactIds || [];
  const artifactId = artifactIds.at(-1);
  const status = liveRun?.status || persistedResult?.status || "IDLE";
  const supportsPreview = definition?.supportsPreview === true;
  const NodeIcon = resolveNodeIcon(definition?.icon);
  const accent = resolveCategoryColor(definition?.category);
  const ModelsIcon = resolveSectionIcon("models");

  function setParameter(
    /** @type {import("../types").ParameterDefinition | undefined} */ parameter,
    /** @type {unknown} */ value,
    /** @type {import("../types").DesktopGrant | import("../types").DesktopGrant[] | undefined} */ selection = undefined,
  ) {
    if (!parameter) return;
    const nextParameters = {
      ...activeNode.data.parameters,
      [parameter.id]: value,
    };
    /** @type {Partial<import("../types").WorkflowNodeData>} */
    const changes = {
      parameters: nextParameters,
    };
    const selections = Array.isArray(selection)
      ? selection
      : selection
        ? [selection]
        : [];
    const artifactIds = selections.flatMap((item) =>
      item.artifactId ? [item.artifactId] : [],
    );
    if (selections.length && !artifactIds.length) {
      nextParameters[`${parameter.id}Name`] =
        selections.length === 1
          ? selections[0].name
          : `${selections.length} selections`;
    }
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

  function selectModel(/** @type {import("../types").ParameterOption} */ option) {
    const capabilities = capabilityContract(option);
    update(activeNode.id, {
      parameters: capabilities?.complete
        ? applyCapabilityDefaults(activeNode.data.parameters || {}, capabilities, option.value)
        : { ...activeNode.data.parameters, model: option.value },
    });
  }

  return (
    <Dialog
      open
      onClose={onClose}
      wide
      className="!max-w-6xl"
      title={definition?.name || node.data.label}
      description={definition?.description}
      bodyClassName="!max-h-[72vh] !overflow-hidden !p-0"
      footer={
        <Button variant="secondary" onClick={onClose}>
          Done
        </Button>
      }
    >
      <div
        className={
          supportsPreview
            ? "grid h-[62vh] min-h-[30rem] grid-cols-[15rem_minmax(15rem,0.85fr)_minmax(0,1.15fr)]"
            : "grid h-[62vh] min-h-[30rem] grid-cols-[15rem_minmax(15rem,1fr)]"
        }
      >
        <aside className="ui-settings-nav border-r p-3.5">
          <div className="ui-inline mb-2.5">
            <IconTile size="sm" style={{ color: accent }}>
              <ModelsIcon className="ui-icon-sm" style={{ color: accent }} />
            </IconTile>
            <div>
              <h3 className="ui-copy-title text-[11px]">Model</h3>
              <p className="ui-copy-muted">Stored with this node</p>
            </div>
          </div>
          {modelParameter ? (
            modelOptions.length ? (
              <Select
                label="Model"
                value={String(currentModel ?? "")}
                options={modelOptions.map((option) => ({
                  value: String(option.value),
                  label: option.label,
                  disabled: option.disabled,
                }))}
                hint={selectedOption?.description}
                onChange={(event) => {
                  const option = modelOptions.find(
                    (candidate) =>
                      String(candidate.value) === event.target.value,
                  );
                  if (option) selectModel(option);
                }}
              />
            ) : (
              <EmptyState
                icon={<Box className="ui-icon-lg" />}
                title="No enabled model"
                description="Install and enable a compatible model in Model settings."
                compact
              />
            )
          ) : (
            <EmptyState
              icon={<Box className="ui-icon-lg" />}
              title="No model choice"
              description={
                definition?.requiredModels?.length
                  ? "This operation uses its required bundled model."
                  : "This node does not run an AI model."
              }
              compact
            />
          )}
          <div className="mt-3">
            {selectedOption?.variant && (
              <div className="ui-actions mb-2 justify-start">
                <Badge tone="accent">{selectedOption.variant.kind}</Badge>
                {selectedOption.variant.quantization && (
                  <Badge tone="neutral">{selectedOption.variant.quantization}</Badge>
                )}
                <Badge tone={selectedCapabilities?.complete ? "success" : "warning"}>
                  {selectedCapabilities?.complete ? "Reviewed settings" : "Needs configuration"}
                </Badge>
              </div>
            )}
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
                      parameter.type === "directory" ||
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
                          : String(
                              node.data.parameters?.[`${parameter.id}Name`] ||
                                "",
                            ) || undefined
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

        {supportsPreview && (
          <aside className="flex min-h-0 flex-col overflow-hidden p-4">
            <div className="ui-inline mb-2.5">
              <IconTile size="sm" style={{ color: accent }}>
                <NodeIcon className="ui-icon-sm" style={{ color: accent }} />
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
        )}
      </div>
    </Dialog>
  );
}
