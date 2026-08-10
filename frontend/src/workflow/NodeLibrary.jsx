import { useEffect, useMemo, useState } from "react";
import {
  Blocks,
  ChevronDown,
  Plus,
  PanelLeftClose,
  PanelLeftOpen,
  resolveCategoryColor,
  resolveCategoryIcon,
  resolveNodeIcon,
} from "../icons";
import {
  EmptyState,
  IconButton,
  IconTile,
  Panel,
  SearchInput,
} from "../components";
import { api } from "../api/client";
import { useDesktopStore } from "../state/desktopStore";
import { useEditorStore } from "../state/editorStore";
import { isVisibleCatalogNode } from "./catalogVisibility";

/** @typedef {{id: string, name: string, description: string, category: string, document: import("../types").WorkflowDocument}} TemplateSummary */

/** @param {{node: import("../types").NodeDefinition}} props */
function LibraryNode({ node }) {
  const Icon = resolveNodeIcon(node.icon);
  const color = resolveCategoryColor(node.category);
  return (
    <div
      draggable
      onDragStart={(event) =>
        event.dataTransfer.setData(
          "application/x-lluna-node",
          node.schemaId,
        )
      }
      title={`Drag ${node.name} onto the canvas${node.description ? ` — ${node.description}` : ""}`}
      className="ui-row group cursor-grab select-none active:cursor-grabbing"
    >
      <IconTile style={{ color }}>
        <Icon className="ui-icon" />
      </IconTile>
      <span className="ui-copy-title min-w-0 flex-1 truncate text-[12px]">
        {node.name}
      </span>
    </div>
  );
}

/** @param {{category: string, nodes: import("../types").NodeDefinition[], closed: boolean, onToggle: () => void}} props */
function LibraryGroup({ category, nodes, closed, onToggle }) {
  const CategoryIcon = resolveCategoryIcon(category);
  const color = resolveCategoryColor(category);
  return (
    <section className="mb-2">
      <button
        type="button"
        aria-expanded={!closed}
        onClick={onToggle}
        className="ui-nav-item"
      >
        <CategoryIcon className="ui-icon-sm shrink-0" style={{ color }} />
        <span className="flex-1 truncate">{category}</span>
        <span className="tabular-nums text-mg-muted">{nodes.length}</span>
        <ChevronDown
          className={`ui-icon text-mg-muted transition ${closed ? "-rotate-90" : ""}`}
        />
      </button>
      {!closed && (
        <div className="ui-stack-xs py-1">
          {nodes.map((node) => (
            <LibraryNode key={node.schemaId} node={node} />
          ))}
        </div>
      )}
    </section>
  );
}

/** @param {{query: string, onQuery: (value: string) => void, groups: [string, import("../types").NodeDefinition[]][], closed: string[], onToggleCategory: (category: string) => void, trailing?: import("react").ReactNode, templates?: TemplateSummary[], onInsertTemplate?: (template: TemplateSummary) => void}} props */
function LibraryBody({
  query,
  onQuery,
  groups,
  closed,
  onToggleCategory,
  trailing,
  templates = [],
  onInsertTemplate = () => {},
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
        <TemplateList templates={templates} onInsert={onInsertTemplate} />
        {!groups.length && !templates.length && (
          <EmptyState
            icon={<Blocks className="ui-icon-lg text-mg-primary" />}
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
          />
        ))}
      </div>

    </>
  );
}


/**
 * Ready-made workflows, offered above the node list.
 *
 * A template is a whole chain, not a single node, so it is inserted with a click
 * rather than dragged: there is no meaningful drop point for four connected
 * nodes. It lands below whatever is already on the canvas and arrives selected,
 * so the next drag moves it as one piece.
 *
 * @param {{templates: TemplateSummary[], onInsert: (template: TemplateSummary) => void}} props
 */
function TemplateList({ templates, onInsert }) {
  const [open, setOpen] = useState(true);
  if (!templates.length) return null;
  return (
    <section className="mb-2 border-b border-mg-border pb-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="ui-nav-item"
      >
        <Blocks className="ui-icon-sm shrink-0 text-mg-primary" />
        <span className="min-w-0 flex-1 truncate text-left">Start from a template</span>
        <ChevronDown
          className={`ui-icon-sm shrink-0 transition ${open ? "" : "-rotate-90"}`}
        />
      </button>
      {open && (
        <div className="ui-stack-xs mt-1">
          {templates.map((template) => (
            <button
              key={template.id}
              type="button"
              title={template.description}
              onClick={() => onInsert(template)}
              className="ui-row group w-full cursor-pointer select-none text-left"
            >
              <IconTile style={{ color: resolveCategoryColor(template.category) }}>
                <Plus className="ui-icon" />
              </IconTile>
              <span className="min-w-0 flex-1">
                <span className="ui-copy-title block truncate text-[12px]">
                  {template.name}
                </span>
                <span className="ui-copy-muted block truncate text-[10px]">
                  {template.description}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

export function NodeLibrary() {
  const definitions = useEditorStore((store) => store.definitions);
  const insertTemplate = useEditorStore((store) => store.insertTemplate);
  const collapsed = useDesktopStore((store) => store.libraryCollapsed);
  const [templates, setTemplates] = useState(
    /** @type {TemplateSummary[]} */ ([]),
  );
  const setValue = useDesktopStore((store) => store.setValue);
  const [query, setQuery] = useState("");
  const [closed, setClosed] = useState(/** @type {string[]} */ ([]));
  const [preview, setPreview] = useState(false);
  const [activeCategory, setActiveCategory] = useState(
    /** @type {string | null} */ (null),
  );
  useEffect(() => {
    let cancelled = false;
    // Templates are static for a session; a failure here must never block the
    // node library, so the section simply stays empty.
    api("/api/workflows/templates")
      .then((payload) => {
        if (!cancelled) setTemplates(payload?.templates || []);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  const visibleDefinitions = useMemo(
    () => definitions.filter(isVisibleCatalogNode),
    [definitions],
  );
  const matchingTemplates = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return templates.filter((template) =>
      words.every((word) =>
        `${template.name} ${template.category} ${template.description}`
          .toLowerCase()
          .includes(word),
      ),
    );
  }, [templates, query]);
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
              <PanelLeftOpen className="ui-icon text-mg-primary" />
            </IconButton>
          </div>
          <div className="ui-stack-xs flex min-h-0 flex-1 flex-col items-center overflow-y-auto py-2">
            {categoryIcons.map(([category]) => {
              const Icon = resolveCategoryIcon(category);
              const color = resolveCategoryColor(category);
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
                      ? "border-mg-accent/40 bg-mg-accent/10"
                      : ""
                  }
                  style={active ? { color, borderColor: `${color}66` } : { color }}
                >
                  <Icon className="ui-icon" />
                </IconButton>
              );
            })}
          </div>
        </Panel>
        {preview && (
          <div
            className="absolute left-full top-0 z-30 flex h-full w-62 flex-col border-r border-mg-border bg-mg-panel"
            onMouseEnter={() => setPreview(true)}
          >
            <LibraryBody
              query={query}
              onQuery={setQuery}
              groups={previewGroups}
              closed={closed}
              onToggleCategory={toggleCategory}
              templates={matchingTemplates}
              onInsertTemplate={(/** @type {TemplateSummary} */ template) =>
                insertTemplate(template.document)
              }
            />
          </div>
        )}
      </div>
    );
  }

  return (
    <Panel className="h-full border-r border-mg-border" bodyClassName="flex flex-col">
      <LibraryBody
        query={query}
        onQuery={setQuery}
        groups={groups}
        closed={closed}
        onToggleCategory={toggleCategory}
        templates={matchingTemplates}
        onInsertTemplate={(/** @type {TemplateSummary} */ template) =>
                insertTemplate(template.document)
              }
        trailing={
          <IconButton label="Collapse library" onClick={collapse}>
            <PanelLeftClose className="ui-icon text-mg-primary" />
          </IconButton>
        }
      />
    </Panel>
  );
}
