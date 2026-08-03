import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Blocks,
  ChevronDown,
  Image,
  PlaySquare,
  Save,
  Sparkles,
} from "lucide-react";
import { Badge, EmptyState, IconTile, Panel, SearchInput } from "../components";
import { useEditorStore } from "../state/editorStore";
import { isVisibleCatalogNode } from "./catalogVisibility";

/** @type {Record<string, import("react").ComponentType<{className?: string}>>} */
const CATEGORY_ICONS = {
  Input: Image,
  Image: Sparkles,
  Video: PlaySquare,
  Output: Save,
};

/** @param {{node: import("../types").NodeDefinition, onAdd: (schemaId: string) => void}} props */
function LibraryNode({ node, onAdd }) {
  const Icon = CATEGORY_ICONS[node.category || ""] || Blocks;
  return (
    <button
      key={node.schemaId}
      type="button"
      draggable
      onDragStart={(event) =>
        event.dataTransfer.setData(
          "application/x-midgard-node",
          node.schemaId,
        )
      }
      onClick={() => onAdd(node.schemaId)}
      className="ui-row group"
    >
      <IconTile className="group-hover:border-mg-secondary/30 group-hover:text-mg-primary">
        <Icon className="size-3.5" />
      </IconTile>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12px] font-medium tracking-tight text-mg-primary">
          {node.name}
        </span>
        <span className="block truncate text-[10px] text-mg-muted">
          {node.description}
        </span>
      </span>
      {!node.available && (
        <Badge tone="warning" size="xs">
          <AlertTriangle className="size-2.5" />
        </Badge>
      )}
    </button>
  );
}

/** @param {{category: string, nodes: import("../types").NodeDefinition[], closed: boolean, onToggle: () => void, onAdd: (schemaId: string) => void}} props */
function LibraryGroup({ category, nodes, closed, onToggle, onAdd }) {
  const Icon = CATEGORY_ICONS[category] || Blocks;
  return (
    <section className="mb-2">
      <button
        type="button"
        aria-expanded={!closed}
        onClick={onToggle}
        className="flex h-8 w-full items-center gap-2 rounded-xl px-2.5 text-left text-[11px] font-medium text-mg-secondary transition hover:bg-mg-elevated hover:text-mg-primary"
      >
        <Icon className="size-3.5" />
        <span className="flex-1 truncate">{category}</span>
        <span className="tabular-nums text-mg-muted">{nodes.length}</span>
        <ChevronDown
          className={`size-3.5 text-mg-muted transition ${closed ? "-rotate-90" : ""}`}
        />
      </button>
      {!closed && (
        <div className="grid gap-0.5 py-1">
          {nodes.map((node) => (
            <LibraryNode key={node.schemaId} node={node} onAdd={onAdd} />
          ))}
        </div>
      )}
    </section>
  );
}

/** @param {{onAdd: (schemaId: string) => void}} props */
export function NodeLibrary({ onAdd }) {
  const definitions = useEditorStore((store) => store.definitions);
  const [query, setQuery] = useState("");
  const [closed, setClosed] = useState(/** @type {string[]} */ ([]));
  const visibleDefinitions = useMemo(
    () => definitions.filter(isVisibleCatalogNode),
    [definitions],
  );
  const groups = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    const filtered = visibleDefinitions.filter((item) =>
      words.every((word) =>
        `${item.name} ${item.category || ""} ${item.description || ""}`
          .toLowerCase()
          .includes(word),
      ),
    );
    /** @type {Record<string, import("../types").NodeDefinition[]>} */
    const grouped = {};
    for (const item of filtered)
      (grouped[item.category || "Other"] ||= []).push(item);
    return Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b, "en-US"));
  }, [visibleDefinitions, query]);

  return (
    <Panel
      title="Library"
      subtitle={`${visibleDefinitions.length} nodes`}
      icon={<Blocks className="size-3.5" />}
      className="h-full border-r border-mg-border"
      bodyClassName="flex flex-col"
    >
      <div className="border-b border-mg-border p-3">
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder="Find a node"
          label="Search node library"
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2.5">
        {!groups.length && (
          <EmptyState
            icon={<Blocks className="size-4" />}
            title="No matching nodes"
            description="Try another operation or category."
            compact
          />
        )}
        {groups.map(([category, nodes]) => (
          <LibraryGroup
            key={category}
            category={category}
            nodes={nodes}
            closed={closed.includes(category)}
            onToggle={() =>
              setClosed((value) =>
                value.includes(category)
                  ? value.filter((item) => item !== category)
                  : [...value, category],
              )
            }
            onAdd={onAdd}
          />
        ))}
      </div>
      <div className="border-t border-mg-border px-3.5 py-2.5 text-[10px] text-mg-muted">
        Click to add · Drag to position
      </div>
    </Panel>
  );
}
