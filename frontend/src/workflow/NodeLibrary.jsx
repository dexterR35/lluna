import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Blocks,
  ChevronDown,
  Image,
  PanelLeftClose,
  PanelLeftOpen,
  PlaySquare,
  Save,
  Sparkles,
} from "lucide-react";
import {
  Badge,
  EmptyState,
  IconButton,
  IconTile,
  Panel,
  SearchInput,
} from "../components";
import { useDesktopStore } from "../state/desktopStore";
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
        <Icon className="ui-icon" />
      </IconTile>
      <span className="ui-copy-title min-w-0 flex-1 truncate text-[12px]">
        {node.name}
      </span>
      {!node.available && (
        <Badge tone="warning" size="xs">
          <AlertTriangle className="ui-icon-xs" />
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
        className="ui-nav-item"
      >
        <Icon className="ui-icon" />
        <span className="flex-1 truncate">{category}</span>
        <span className="tabular-nums text-mg-muted">{nodes.length}</span>
        <ChevronDown
          className={`ui-icon text-mg-muted transition ${closed ? "-rotate-90" : ""}`}
        />
      </button>
      {!closed && (
        <div className="ui-stack-xs py-1">
          {nodes.map((node) => (
            <LibraryNode key={node.schemaId} node={node} onAdd={onAdd} />
          ))}
        </div>
      )}
    </section>
  );
}

/** @param {{onAdd: (schemaId: string) => void, query: string, onQuery: (value: string) => void, groups: [string, import("../types").NodeDefinition[]][], closed: string[], onToggleCategory: (category: string) => void, trailing?: import("react").ReactNode}} props */
function LibraryBody({
  onAdd,
  query,
  onQuery,
  groups,
  closed,
  onToggleCategory,
  trailing,
}) {
  return (
    <>
      <div className="flex items-center gap-1.5 border-b border-mg-border p-3">
        <div className="min-w-0 flex-1">
          <SearchInput
            value={query}
            onChange={onQuery}
            placeholder="Find a node"
            label="Search node library"
          />
        </div>
        {trailing}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2.5">
        {!groups.length && (
          <EmptyState
            icon={<Blocks className="ui-icon-lg" />}
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
            onToggle={() => onToggleCategory(category)}
            onAdd={onAdd}
          />
        ))}
      </div>

    </>
  );
}

/** @param {{onAdd: (schemaId: string) => void}} props */
export function NodeLibrary({ onAdd }) {
  const definitions = useEditorStore((store) => store.definitions);
  const collapsed = useDesktopStore((store) => store.libraryCollapsed);
  const setValue = useDesktopStore((store) => store.setValue);
  const [query, setQuery] = useState("");
  const [closed, setClosed] = useState(/** @type {string[]} */ ([]));
  const [preview, setPreview] = useState(false);
  const [activeCategory, setActiveCategory] = useState(
    /** @type {string | null} */ (null),
  );
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

  const categoryIcons = useMemo(() => {
    /** @type {Record<string, import("../types").NodeDefinition[]>} */
    const grouped = {};
    for (const item of visibleDefinitions)
      (grouped[item.category || "Other"] ||= []).push(item);
    return Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b, "en-US"));
  }, [visibleDefinitions]);

  const previewGroups = useMemo(() => {
    if (!activeCategory) return groups;
    return groups.filter(([category]) => category === activeCategory);
  }, [groups, activeCategory]);

  function toggleCategory(/** @type {string} */ category) {
    setClosed((value) =>
      value.includes(category)
        ? value.filter((item) => item !== category)
        : [...value, category],
    );
  }

  function expand() {
    setValue("libraryCollapsed", false);
    setPreview(false);
    setActiveCategory(null);
  }

  function collapse() {
    setValue("libraryCollapsed", true);
    setPreview(false);
    setActiveCategory(null);
  }

  if (collapsed) {
    return (
      <div
        className="relative h-full"
        onMouseLeave={() => {
          setPreview(false);
          setActiveCategory(null);
        }}
      >
        <Panel className="h-full border-r border-mg-border" bodyClassName="flex flex-col">
          <div className="flex flex-col items-center gap-1 border-b border-mg-border py-2">
            <IconButton
              label="Expand library"
              onClick={expand}
              onMouseEnter={() => {
                setPreview(true);
                setActiveCategory(null);
              }}
            >
              <PanelLeftOpen className="ui-icon" />
            </IconButton>
          </div>
          <div className="ui-stack-xs flex min-h-0 flex-1 flex-col items-center overflow-y-auto py-2">
            {categoryIcons.map(([category]) => {
              const Icon = CATEGORY_ICONS[category] || Blocks;
              const active = preview && activeCategory === category;
              return (
                <IconButton
                  key={category}
                  label={`${category} nodes`}
                  onMouseEnter={() => {
                    setPreview(true);
                    setActiveCategory(category);
                  }}
                  onClick={() => {
                    setPreview(true);
                    setActiveCategory(category);
                  }}
                  className={
                    active
                      ? "border-mg-accent/40 bg-mg-accent/10 text-mg-accent"
                      : ""
                  }
                >
                  <Icon className="ui-icon" />
                </IconButton>
              );
            })}
          </div>
        </Panel>
        {preview && (
          <div
            className="absolute left-full top-0 z-30 flex h-full w-62 flex-col border-r border-mg-border bg-mg-panel shadow-[8px_0_24px_rgba(0,0,0,0.18)]"
            onMouseEnter={() => setPreview(true)}
          >
            <LibraryBody
              onAdd={onAdd}
              query={query}
              onQuery={setQuery}
              groups={previewGroups}
              closed={closed}
              onToggleCategory={toggleCategory}
            />
          </div>
        )}
      </div>
    );
  }

  return (
    <Panel className="h-full border-r border-mg-border" bodyClassName="flex flex-col">
      <LibraryBody
        onAdd={onAdd}
        query={query}
        onQuery={setQuery}
        groups={groups}
        closed={closed}
        onToggleCategory={toggleCategory}
        trailing={
          <IconButton label="Collapse library" onClick={collapse}>
            <PanelLeftClose className="ui-icon" />
          </IconButton>
        }
      />
    </Panel>
  );
}
