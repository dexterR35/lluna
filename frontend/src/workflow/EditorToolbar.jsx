import {
  FolderOpen,
  Layers3,
  Logs,
  PanelLeft,
  Pause,
  Play,
  Redo2,
  Save,
  Settings,
  Square,
  Undo2,
  Workflow,
} from "lucide-react";
import midgardIconUrl from "../../assets/app-icon/midgard.svg";
import { Button, ToolbarButton } from "../components";
import { useDesktopStore } from "../state/desktopStore";
import { useEditorStore } from "../state/editorStore";
import { useRunStore } from "../state/runStore";

/** @param {{actions: Record<string, (...args: any[]) => any>}} props */
export function EditorToolbar({ actions }) {
  const past = useEditorStore((store) => store.past.length);
  const future = useEditorStore((store) => store.future.length);
  const selected = useEditorStore((store) =>
    store.nodes.some((node) => node.selected),
  );
  const name = useEditorStore((store) => store.project.name);
  const dirty = useEditorStore((store) => store.dirty);
  const undo = useEditorStore((store) => store.undo);
  const redo = useEditorStore((store) => store.redo);
  const run = useRunStore((store) => store.run);
  const pause = useRunStore((store) => store.pause);
  const resume = useRunStore((store) => store.resume);
  const cancel = useRunStore((store) => store.cancel);
  const desktop = useDesktopStore();
  const active = ["RUNNING", "PAUSE_REQUESTED", "PAUSED"].includes(
    run?.status || "",
  );

  return (
    <header className="flex h-full items-center gap-1 border-b border-mg-border bg-mg-panel px-2.5">
      <div className="mr-1 flex min-w-0 items-center gap-2.5 px-1">
        <img
          className="size-7 shrink-0 rounded-xl"
          src={midgardIconUrl}
          alt="Midgard"
        />
        <div className="hidden min-w-0 xl:block">
          <div className="flex items-center gap-1.5">
            <strong className="max-w-44 truncate text-[12px] font-semibold tracking-tight">
              {name}
            </strong>
            {dirty && (
              <span
                className="size-1.5 rounded-full bg-mg-warning"
                title="Unsaved changes"
              />
            )}
          </div>
          <span className="block text-[10px] text-mg-muted">Workflow</span>
        </div>
      </div>
      <span className="ui-divider" />
      <ToolbarButton
        label="New"
        shortcut="Ctrl+N"
        icon={<Workflow className="size-3.5" />}
        onClick={actions.newWorkflow}
      />
      <ToolbarButton
        label="Open"
        shortcut="Ctrl+O"
        icon={<FolderOpen className="size-3.5" />}
        onClick={actions.openWorkflow}
      />
      <ToolbarButton
        label="Save"
        shortcut="Ctrl+S"
        icon={<Save className="size-3.5" />}
        onClick={actions.saveWorkflow}
      />
      <span className="ui-divider" />
      <ToolbarButton
        label="Undo"
        shortcut="Ctrl+Z"
        icon={<Undo2 className="size-3.5" />}
        disabled={!past}
        onClick={undo}
      />
      <ToolbarButton
        label="Redo"
        shortcut="Ctrl+Shift+Z"
        icon={<Redo2 className="size-3.5" />}
        disabled={!future}
        onClick={redo}
      />
      <span className="ui-divider" />
      <ToolbarButton
        label="Flow box"
        icon={<Layers3 className="size-3.5" />}
        disabled={!selected}
        onClick={actions.createFlow}
      />
      <span className="flex-1" />
      {!active ? (
        <Button onClick={actions.run} className="min-w-20">
          <Play className="size-3.5 fill-current" />
          Run
        </Button>
      ) : (
        <>
          <Button
            variant="secondary"
            onClick={run?.status === "PAUSED" ? resume : pause}
          >
            <Pause className="size-3.5" />
            {run?.status === "PAUSED" ? "Resume" : "Pause"}
          </Button>
          <ToolbarButton
            label="Stop"
            icon={<Square className="size-3.5" />}
            onClick={cancel}
          />
        </>
      )}
      <span className="ui-divider" />
      <ToolbarButton
        label="Library"
        active={desktop.libraryVisible}
        icon={<PanelLeft className="size-3.5" />}
        onClick={() => desktop.toggle("libraryVisible")}
      />
      <ToolbarButton
        label="Activity"
        active={desktop.drawerVisible}
        icon={<Logs className="size-3.5" />}
        onClick={() => desktop.toggle("drawerVisible")}
      />
      <ToolbarButton
        label="Settings"
        icon={<Settings className="size-3.5" />}
        onClick={() => desktop.setValue("settingsOpen", true)}
      />
    </header>
  );
}
