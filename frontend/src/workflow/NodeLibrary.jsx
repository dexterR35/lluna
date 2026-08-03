import { useMemo, useState } from "react";
import { AlertTriangle, Box, ChevronDown, Star } from "lucide-react";
import { Badge, EmptyState, Panel, SearchInput } from "../components";
import { useEditorStore } from "../state/editorStore";
export function NodeLibrary({ onAdd }) {
  const definitions = useEditorStore(store => store.definitions);
  const [query, setQuery] = useState("");
  const [closed, setClosed] = useState([]);
  const groups = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    const filtered = definitions.filter(item => words.every(word => `${item.name} ${item.category} ${item.description}`.toLowerCase().includes(word)));
    return Object.entries(Object.groupBy(filtered, item => item.category)).sort(([a], [b]) => a.localeCompare(b));
  }, [definitions, query]);
  return <Panel title="Node library" className="h-full border-r" bodyClassName="flex flex-col"><div className="border-b border-mg-border p-3"><SearchInput value={query} onChange={setQuery} placeholder="Search nodes…" label="Search node library" /></div><div className="min-h-0 flex-1 overflow-y-auto p-2">
    {!groups.length && <EmptyState icon={<Box className="size-5" />} title="No matching nodes" description="Try a capability, category, or operation name." />}
    {groups.map(([category, nodes]) => <section key={category} className="mb-2"><button type="button" aria-expanded={!closed.includes(category)} onClick={() => setClosed(value => value.includes(category) ? value.filter(item => item !== category) : [...value, category])} className="flex min-h-8 w-full items-center gap-2 rounded px-2 text-left text-xs font-semibold uppercase tracking-wide text-mg-secondary hover:bg-mg-selected"><ChevronDown className={`size-3.5 transition ${closed.includes(category) ? "-rotate-90" : ""}`} />{category}<span className="ml-auto">{nodes.length}</span></button>
      {!closed.includes(category) && <div className="grid gap-1 py-1">{nodes.map(node => <button key={node.schemaId} type="button" draggable onDragStart={event => event.dataTransfer.setData("application/x-midgard-node", node.schemaId)} onClick={() => onAdd(node.schemaId)} className="group flex min-h-11 items-center gap-2 rounded-md border border-transparent px-2 text-left hover:border-mg-border hover:bg-mg-selected focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mg-focus"><Star className="size-3.5 text-mg-secondary opacity-0 group-hover:opacity-100" /><span className="min-w-0 flex-1"><span className="block truncate text-sm text-mg-primary">{node.name}</span><span className="block truncate text-[11px] text-mg-secondary">{node.description}</span></span>{!node.available && <Badge tone="warning"><AlertTriangle className="size-3" /></Badge>}</button>)}</div>}
    </section>)}
  </div></Panel>;
}
