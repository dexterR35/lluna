import {
  Box,
  Check,
  Cpu,
  Database,
  Image as ImageIcon,
  Play,
  Settings2,
  Sparkles,
} from "lucide-react";
import { ArtifactPreview } from "../preview/ArtifactPreview";
import {
  Badge,
  Button,
  Card,
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

/** @param {import("../types").ParameterOption | undefined} option @param {Record<string, any>[]} models */
/** @param {{option: import("../types").ParameterOption, selected: boolean, inventory?: Record<string, any>, onSelect: () => void}} props */
function ModelCard({ option, selected, inventory, onSelect }) {
  const installed = inventory?.installed;
  return (
    <Card
      as="button"
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      padded
      interactive
      selected={selected}
      className="w-full p-3 text-left"
    >
      <div className="flex items-start gap-2.5">
        <span
          className={`mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border ${selected ? "border-mg-accent bg-mg-accent text-white" : "border-mg-border text-transparent"}`}
        >
          <Check className="size-3" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <strong className="truncate text-[12px] font-semibold tracking-tight text-mg-primary">
              {option.label}
            </strong>
            {installed !== undefined && (
              <Badge size="xs" tone={installed ? "success" : "neutral"}>
                {installed ? "Installed" : "On demand"}
              </Badge>
            )}
          </span>
          {option.description && (
            <span className="mt-1 block text-[10px] leading-4 text-mg-secondary">
              {option.description}
            </span>
          )}
          {inventory && (
            <span className="mt-1.5 flex items-center gap-1 text-[10px] text-mg-muted">
              <Cpu className="size-2.5" />
              {inventory.framework || inventory.capability || "Local model"}
              {inventory.minimum_vram_mb
                ? ` · ${Math.round(inventory.minimum_vram_mb / 1024)} GB VRAM`
                : ""}
            </span>
          )}
        </span>
      </div>
    </Card>
  );
}

/** @param {{ids?: string[], models: Record<string, any>[]}} props */
function RequiredModels({ ids, models }) {
  if (!ids?.length) return null;
  return (
    <div className="grid gap-1.5">
      <span className="text-[11px] font-medium text-mg-secondary">
        Required runtime
      </span>
      {ids.map((id) => {
        const model = models.find((item) => item.id === id);
        return (
          <div
            key={id}
            className="flex items-center gap-2 rounded-xl border border-mg-border bg-mg-app/50 px-2.5 py-1.5"
          >
            <Database className="size-3 text-mg-muted" />
            <span className="min-w-0 flex-1 truncate text-[11px] text-mg-secondary">
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

/** @param {{nodeId: string | null, onClose: () => void, onRun: (id: string) => void, onManageModels: () => void}} props */
export function NodeEditorDialog({ nodeId, onClose, onRun, onManageModels }) {
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
  const artifactId = (
    liveRun?.artifactIds?.length
      ? liveRun.artifactIds
      : persistedResult?.artifactIds || []
  ).at(-1);
  const status = liveRun?.status || persistedResult?.status || "IDLE";
  const runLabel = definition?.kind === "input" ? "Run" : "Run from here";

  function setParameter(
    /** @type {import("../types").ParameterDefinition | undefined} */ parameter,
    /** @type {unknown} */ value,
    /** @type {import("../types").DesktopGrant | undefined} */ selection = undefined,
  ) {
    if (!parameter) return;
    /** @type {Partial<import("../types").WorkflowNodeData>} */
    const changes = {
      parameters: { ...activeNode.data.parameters, [parameter.id]: value },
    };
    if (selection?.artifactId) {
      useRunStore.getState().clearNodeResult(activeNode.id);
      changes.result = {
        status: "READY",
        artifactIds: [selection.artifactId],
        sourceName: selection.name,
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
      title={definition?.name || node.data.label}
      description="Node options · choose the model and settings used by this node."
      bodyClassName="!max-h-[72vh] !overflow-hidden !p-0"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Done
          </Button>
          <Button onClick={() => onRun(node.id)}>
            <Play className="size-3.5 fill-current" />
            {runLabel}
          </Button>
        </>
      }
    >
      <div className="grid h-[62vh] min-h-[30rem] grid-cols-[16rem_minmax(0,1fr)]">
        <aside className="min-h-0 overflow-y-auto border-r border-mg-border bg-mg-app/40 p-3.5">
          <div className="mb-3 flex items-center gap-2">
            <IconTile size="sm">
              <Sparkles className="size-3" />
            </IconTile>
            <div>
              <h3 className="text-[11px] font-semibold tracking-tight text-mg-primary">
                Model
              </h3>
              <p className="text-[10px] text-mg-muted">Stored with this node</p>
            </div>
          </div>
          {modelOptions.length ? (
            <div className="grid gap-1.5">
              {modelOptions.map((option) => (
                <ModelCard
                  key={option.value}
                  option={option}
                  selected={option.value === currentModel}
                  inventory={inventoryForOption(option, models)}
                  onSelect={() => setParameter(modelParameter, option.value)}
                />
              ))}
            </div>
          ) : (
            <div className="ui-section">
              <EmptyState
                icon={<Box className="size-4" />}
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
            </div>
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

        <main className="min-h-0 overflow-y-auto p-4">
          <div className="grid gap-4">
            <section className="grid gap-2.5">
              <div className="flex items-center gap-2">
                <Settings2 className="size-3.5 text-mg-muted" />
                <div className="min-w-0 flex-1">
                  <h3 className="text-[11px] font-semibold tracking-tight text-mg-secondary">
                    Node settings
                  </h3>
                  <p className="text-[9px] text-mg-muted">
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
              <div className="ui-section grid gap-3 p-3">
                <TextField
                  label="Node label"
                  value={node.data.label || ""}
                  onChange={(event) =>
                    update(node.id, { label: event.target.value })
                  }
                />
                {selectedOption && (
                  <div className="rounded-xl border border-mg-accent/25 bg-mg-accent/5 px-3 py-2">
                    <span className="text-[10px] text-mg-muted">
                      Selected model
                    </span>
                    <p className="mt-0.5 text-[10px] font-medium text-mg-primary">
                      {selectedOption.label}
                    </p>
                  </div>
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
                            parameter.type === "file"
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
                  <p className="text-[10px] text-mg-muted">
                    This node has no additional operation settings.
                  </p>
                )}
                <div className="border-t border-mg-border pt-2">
                  <Checkbox
                    label="Disable node"
                    checked={Boolean(node.data.disabled)}
                    onChange={(event) =>
                      update(node.id, { disabled: event.target.checked })
                    }
                  />
                </div>
              </div>
            </section>

            <section className="grid gap-2">
              <div className="flex items-center gap-2">
                <ImageIcon className="size-3.5 text-mg-muted" />
                <h3 className="text-[11px] font-semibold tracking-tight text-mg-secondary">
                  Latest result
                </h3>
              </div>
              <ArtifactPreview
                artifactId={artifactId}
                effect={String(node.data.appearance?.imageEffect || "none")}
              />
            </section>
          </div>
        </main>
      </div>
    </Dialog>
  );
}
