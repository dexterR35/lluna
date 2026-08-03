import { useEffect, useMemo, useState } from "react";
import { Monitor, RotateCcw, Settings2 } from "lucide-react";
import { Button, Card, Dialog, NumberField, Switch, TextField } from "../components";
import { useDesktopStore } from "../state/desktopStore";
import { useServerStore } from "../state/serverStore";

/** @param {string} value */
function title(value) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

/** @param {{section: string, values: Record<string, any>}} props */
function SettingsSection({ section, values }) {
  const update = useServerStore((store) => store.updateSettings);
  const reset = useServerStore((store) => store.resetSettings);
  const [draft, setDraft] = useState(values);
  useEffect(() => setDraft(values), [values]);

  async function commit(/** @type {string} */ key, /** @type {unknown} */ value) {
    setDraft((current) => ({ ...current, [key]: value }));
    await update({ [section]: { ...draft, [key]: value } });
  }

  return (
    <div className="grid gap-2.5">
      {Object.entries(draft).map(([key, value]) =>
        typeof value === "boolean" ? (
          <Card key={key} className="bg-mg-app/45 px-3 py-1" padded={false}>
            <Switch label={title(key)} checked={value} onChange={(next) => void commit(key, next)} />
          </Card>
        ) : typeof value === "number" ? (
          <NumberField
            key={key}
            label={title(key)}
            value={value}
            onChange={(event) => setDraft((current) => ({ ...current, [key]: Number(event.target.value) }))}
            onBlur={(event) => void commit(key, Number(event.target.value))}
          />
        ) : (
          <TextField
            key={key}
            label={title(key)}
            value={String(value)}
            onChange={(event) => setDraft((current) => ({ ...current, [key]: event.target.value }))}
            onBlur={(event) => void commit(key, event.target.value)}
          />
        ),
      )}
      <div className="mt-1 flex justify-end border-t border-mg-border pt-2.5">
        <Button variant="ghost" className="min-h-7 px-2 text-[10px]" onClick={() => void reset(section)}>
          <RotateCcw className="size-3" /> Reset section
        </Button>
      </div>
    </div>
  );
}

/** @param {{onReset: () => void}} props */
function EditorSettings({ onReset }) {
  const minimapVisible = useDesktopStore((store) => store.minimapVisible);
  const set = useDesktopStore((store) => store.setValue);
  return (
    <div className="grid gap-2.5">
      <Card className="bg-mg-app/45 px-3 py-1" padded={false}>
        <Switch label="Show minimap" checked={minimapVisible} onChange={(value) => set("minimapVisible", value)} />
      </Card>
      <Card className="flex items-center justify-between gap-3 bg-mg-app/45">
        <div>
          <p className="text-[11px] font-medium text-mg-primary">Reset workspace layout</p>
          <p className="mt-0.5 text-[10px] text-mg-muted">Restore panel sizes and visibility.</p>
        </div>
        <Button variant="secondary" className="min-h-7 shrink-0 px-2.5 text-[10px]" onClick={onReset}>
          Reset
        </Button>
      </Card>
    </div>
  );
}

export function SettingsDialog() {
  const open = useDesktopStore((store) => store.settingsOpen);
  const set = useDesktopStore((store) => store.setValue);
  const settings = useServerStore((store) => store.settings);
  const sections = useMemo(
    () =>
      Object.entries(settings || {})
        .filter(([key, value]) => key !== "schema_version" && value !== null && typeof value === "object")
        .map(([id, values]) => ({ id, label: title(id), values: /** @type {Record<string, any>} */ (values) })),
    [settings],
  );
  const [activeId, setActiveId] = useState("editor");
  useEffect(() => {
    if (activeId !== "editor" && !sections.some((section) => section.id === activeId)) setActiveId("editor");
  }, [activeId, sections]);
  const active = sections.find((section) => section.id === activeId);

  return (
    <Dialog
      open={open}
      onClose={() => set("settingsOpen", false)}
      title="Settings"
      description="Application and local processing preferences"
      className="max-w-xl"
      bodyClassName="!max-h-none !p-0"
    >
      <div className="grid h-[28rem] grid-cols-[9.5rem_minmax(0,1fr)]">
        <nav aria-label="Settings sections" className="min-h-0 overflow-y-auto border-r border-mg-border bg-mg-app/40 p-2.5">
          <button
            type="button"
            onClick={() => setActiveId("editor")}
            className={`flex min-h-8 w-full items-center gap-2 rounded-xl px-2.5 text-left text-[11px] transition ${activeId === "editor" ? "bg-mg-accent/15 font-medium text-mg-accent" : "text-mg-secondary hover:bg-mg-elevated hover:text-mg-primary"}`}
          >
            <Monitor className="size-3.5" /> Editor
          </button>
          <div className="my-2 border-t border-mg-border" />
          {sections.map((section) => (
            <button
              key={section.id}
              type="button"
              onClick={() => setActiveId(section.id)}
              className={`flex min-h-8 w-full items-center gap-2 rounded-xl px-2.5 text-left text-[11px] transition ${activeId === section.id ? "bg-mg-accent/15 font-medium text-mg-accent" : "text-mg-secondary hover:bg-mg-elevated hover:text-mg-primary"}`}
            >
              <Settings2 className="size-3.5" />
              <span className="truncate">{section.label}</span>
            </button>
          ))}
        </nav>
        <section className="min-h-0 overflow-y-auto p-4">
          <header className="mb-3 border-b border-mg-border pb-3">
            <h3 className="text-[12px] font-semibold tracking-tight text-mg-primary">{active?.label || "Editor"}</h3>
            <p className="mt-1 text-[10px] text-mg-muted">
              {active ? "Changes are saved automatically." : "Canvas appearance and workspace behavior."}
            </p>
          </header>
          {active ? (
            <SettingsSection key={active.id} section={active.id} values={active.values} />
          ) : (
            <EditorSettings onReset={() => useDesktopStore.getState().reset()} />
          )}
        </section>
      </div>
    </Dialog>
  );
}
