import { Copy, Play, Trash2 } from "lucide-react";
import { Accordion, Badge, Button, Checkbox, EmptyState, NumberField, Panel, Select, Switch, TextArea, TextField } from "../components";
import { useEditorStore } from "../state/editorStore";
import { useRunStore } from "../state/runStore";
import { ArtifactPreview } from "../preview/ArtifactPreview";
function Parameter({ definition, value, onChange }) {
  const common = { label: definition.label, value: value ?? "", onChange: event => onChange(event.target.value) };
  if (definition.type === "boolean") return <Switch label={definition.label} checked={Boolean(value)} onChange={onChange} />;
  if (["number", "integer"].includes(definition.type)) return <NumberField {...common} min={definition.minimum} max={definition.maximum} step={definition.step || (definition.type === "integer" ? 1 : "any")} onChange={event => onChange(definition.type === "integer" ? Number.parseInt(event.target.value || "0", 10) : Number(event.target.value))} />;
  if (definition.type === "textarea" || definition.type === "json") return <TextArea {...common} onChange={event => onChange(definition.type === "json" ? event.target.value : event.target.value)} />;
  if (definition.options?.length) return <Select {...common} options={definition.options} />;
  if (definition.type === "file" || definition.type === "saveFile") return <DesktopFileField definition={definition} value={value} onChange={onChange} />;
  return <TextField {...common} />;
}
function DesktopFileField({ definition, value, onChange }) {
  async function choose() { const desktop = window.midgardDesktop; if (!desktop) return; let grant; if (definition.type === "saveFile") grant = await desktop.selectSaveFile("image"); else grant = (await desktop.selectImageFiles()).at(0); if (grant) onChange(grant.grantId); }
  return <div className="grid gap-1.5"><span className="text-sm text-mg-secondary">{definition.label}</span><Button variant="secondary" onClick={choose}>{value ? "Change selected file" : "Choose local file…"}</Button>{value && <span className="truncate text-xs text-mg-secondary">Grant: {value}</span>}</div>;
}
export function Inspector({ issues, onRunNode }) {
  const nodes = useEditorStore(store => store.nodes); const update = useEditorStore(store => store.updateNode); const duplicate = useEditorStore(store => store.duplicateSelected); const remove = useEditorStore(store => store.deleteSelected); const name = useEditorStore(store => store.project.name); const setName = useEditorStore(store => store.setProjectName);
  const selected = nodes.find(node => node.selected); const nodeRun = useRunStore(store => selected ? store.nodeStates[selected.id] : null);
  if (!selected) return <Panel title="Workflow inspector" className="h-full border-l" bodyClassName="overflow-y-auto p-4"><div className="grid gap-4"><TextField label="Workflow name" value={name} onChange={event => setName(event.target.value)} /><EmptyState title="Nothing selected" description="Select a node to edit its parameters and inspect output artifacts." /></div></Panel>;
  const definition = selected.data.definition; const nodeIssues = issues.filter(issue => issue.nodeId === selected.id); const artifactId = nodeRun?.artifactIds?.at(-1);
  return <Panel title="Node inspector" className="h-full border-l" bodyClassName="overflow-y-auto"><div className="grid gap-4 p-4"><div><div className="flex items-center gap-2"><h2 className="font-semibold">{definition?.name || selected.data.schemaId}</h2>{nodeRun?.status && <Badge tone={nodeRun.status === "FAILED" ? "error" : nodeRun.status === "RUNNING" ? "running" : "neutral"}>{nodeRun.status}</Badge>}</div><p className="mt-1 text-sm leading-5 text-mg-secondary">{definition?.description}</p></div><TextField label="Node label" value={selected.data.label || ""} onChange={event => update(selected.id, { label: event.target.value })} />
    {nodeIssues.length > 0 && <div className="rounded-lg border border-mg-warning p-3 text-xs text-mg-warning">{nodeIssues.map(issue => <p key={`${issue.code}-${issue.message}`}>{issue.message}</p>)}</div>}
    <Accordion openIds={["parameters", "preview", "status"]} onToggle={() => {}} items={[
      { id: "parameters", label: "Parameters", content: <div className="grid gap-3">{definition?.parameters?.length ? definition.parameters.map(parameter => <Parameter key={parameter.id} definition={parameter} value={selected.data.parameters?.[parameter.id]} onChange={value => update(selected.id, { parameters: { ...selected.data.parameters, [parameter.id]: value } })} />) : <p className="text-sm text-mg-secondary">This node has no parameters.</p>}<Checkbox label="Disable node" checked={Boolean(selected.data.disabled)} onChange={event => update(selected.id, { disabled: event.target.checked })} /><Checkbox label="Bypass when possible" checked={Boolean(selected.data.bypass)} onChange={event => update(selected.id, { bypass: event.target.checked })} /></div> },
      { id: "preview", label: "Preview", content: <ArtifactPreview artifactId={artifactId} /> },
      { id: "status", label: "Execution", content: <div className="grid gap-2 text-xs text-mg-secondary"><span>Status: {nodeRun?.status || "IDLE"}</span><span>Progress: {nodeRun?.progress || 0}%</span><span>Cache: content-addressed</span></div> },
    ]} />
    <div className="grid grid-cols-3 gap-2"><Button onClick={() => onRunNode(selected.id)}><Play className="size-4" />Run</Button><Button variant="secondary" onClick={duplicate}><Copy className="size-4" />Copy</Button><Button variant="danger" onClick={remove}><Trash2 className="size-4" />Delete</Button></div></div></Panel>;
}
