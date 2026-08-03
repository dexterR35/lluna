import { useMemo, useState } from "react";
import { AlertTriangle, Blocks, ChevronDown, Image, PlaySquare, Save, Sparkles } from "lucide-react";
import { Badge, EmptyState, Panel, SearchInput } from "../components";
import { useEditorStore } from "../state/editorStore";
import { isVisibleCatalogNode } from "./catalogVisibility";

const CATEGORY_ICONS = {
  Input: Image,
  Image: Sparkles,
  Video: PlaySquare,
  Output: Save,
};

function LibraryNode({ node, onAdd }) {
  const Icon = CATEGORY_ICONS[node.category] || Blocks;
  return <button key={node.schemaId} type="button" draggable onDragStart={event => event.dataTransfer.setData("application/x-midgard-node", node.schemaId)} onClick={() => onAdd(node.schemaId)} className="group flex min-h-10 w-full items-center gap-2 rounded-lg border border-transparent px-2 text-left transition hover:border-mg-border hover:bg-mg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mg-focus/40">
    <span className="ui-icon-tile group-hover:border-mg-secondary/30 group-hover:text-mg-primary"><Icon className="size-3.5" /></span>
    <span className="min-w-0 flex-1">
      <span className="block truncate text-[11px] font-medium text-mg-primary">{node.name}</span>
      <span className="block truncate text-[9px] text-mg-muted">{node.description}</span>
    </span>
    {!node.available && <Badge tone="warning"><AlertTriangle className="size-2.5" /></Badge>}
  </button>;
}

function LibraryGroup({ category, nodes, closed, onToggle, onAdd }) {
  const Icon = CATEGORY_ICONS[category] || Blocks;
  return <section className="mb-1.5">
    <button type="button" aria-expanded={!closed} onClick={onToggle} className="flex h-7 w-full items-center gap-1.5 rounded-md px-2 text-left text-[9px] font-semibold uppercase tracking-[.11em] text-mg-muted transition hover:bg-mg-elevated hover:text-mg-secondary">
      <Icon className="size-3" /><span className="flex-1">{category}</span><span className="font-normal tabular-nums">{nodes.length}</span><ChevronDown className={`size-3 transition ${closed ? "-rotate-90" : ""}`} />
    </button>
    {!closed && <div className="grid gap-0.5 py-1">{nodes.map(node => <LibraryNode key={node.schemaId} node={node} onAdd={onAdd} />)}</div>}
  </section>;
}

export function NodeLibrary({ onAdd }) {
  const definitions = useEditorStore(store => store.definitions);
  const [query, setQuery] = useState("");
  const [closed, setClosed] = useState([]);
  const visibleDefinitions = useMemo(() => definitions.filter(isVisibleCatalogNode), [definitions]);
  const groups = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    const filtered = visibleDefinitions.filter(item => words.every(word => `${item.name} ${item.category} ${item.description}`.toLowerCase().includes(word)));
    return Object.entries(Object.groupBy(filtered, item => item.category)).sort(([a], [b]) => a.localeCompare(b));
  }, [visibleDefinitions, query]);

  return <Panel title="Library" subtitle={`${visibleDefinitions.length} available nodes`} icon={<Blocks className="size-3.5" />} className="h-full border-r" bodyClassName="flex flex-col">
    <div className="border-b border-mg-border p-2.5"><SearchInput value={query} onChange={setQuery} placeholder="Find a node" label="Search node library" /></div>
    <div className="min-h-0 flex-1 overflow-y-auto p-2">
      {!groups.length && <EmptyState icon={<Blocks className="size-4" />} title="No matching nodes" description="Try another operation or category." compact />}
      {groups.map(([category, nodes]) => <LibraryGroup key={category} category={category} nodes={nodes} closed={closed.includes(category)} onToggle={() => setClosed(value => value.includes(category) ? value.filter(item => item !== category) : [...value, category])} onAdd={onAdd} />)}
    </div>
    <div className="border-t border-mg-border px-3 py-2 text-[9px] text-mg-muted">Click to add · Drag to position</div>
  </Panel>;
}
