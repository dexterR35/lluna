import {
  FolderOpen,
  Layers3,
  Logs,
  Pause,
  Play,
  Redo2,
  Save,
  Settings,
  Square,
  Undo2,
  Workflow,
} from "../icons";
import { Button, TextField, ToolbarButton } from "../components";
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
  const setProjectName = useEditorStore((store) => store.setProjectName);
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
      <div className="mr-1 flex min-w-0 items-center gap-1.5 px-1">
        <TextField
          bare
          id="workflow-name"
          aria-label="Workflow name"
          value={name}
          onChange={(event) => setProjectName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.currentTarget.blur();
              void actions.saveWorkflow();
            }
          }}
          title="Edit workflow name"
        />
        {dirty && (
          <span
            className="size-1.5 shrink-0 rounded-full bg-mg-warning"
            title="Unsaved changes"
          />
        )}
      </div>
      <ToolbarButton
        label="Save"
        shortcut="Ctrl+S"
        icon={<Save className="ui-icon" />}
        onClick={actions.saveWorkflow}
      />
      <span className="ui-divider" />
      <ToolbarButton
        label="New"
        shortcut="Ctrl+N"
        icon={<Workflow className="ui-icon" />}
        onClick={actions.newWorkflow}
      />
      <ToolbarButton
        label="Open"
        shortcut="Ctrl+O"
        icon={<FolderOpen className="ui-icon" />}
        onClick={actions.openWorkflow}
      />
      <span className="ui-divider" />
      <ToolbarButton
        label="Undo"
        shortcut="Ctrl+Z"
        icon={<Undo2 className="ui-icon" />}
        disabled={!past}
        onClick={undo}
      />
      <ToolbarButton
        label="Redo"
        shortcut="Ctrl+Shift+Z"
        icon={<Redo2 className="ui-icon" />}
        disabled={!future}
        onClick={redo}
      />
      <span className="ui-divider" />
      <ToolbarButton
        label="Flow box"
        icon={<Layers3 className="ui-icon" />}
        disabled={!selected}
        onClick={actions.createFlow}
      />
      <span className="flex-1" />
      {!active ? (
        <Button
          onClick={actions.run}
          className="min-w-20"
          title="Run workflow (Ctrl+Enter). Use Ctrl+Shift+Enter to queue next."
        >
          <Play className="ui-icon fill-current" />
          Run
        </Button>
      ) : (
        <>
          <Button
            variant="secondary"
            onClick={run?.status === "PAUSED" ? resume : pause}
          >
            <Pause className="ui-icon" />
            {run?.status === "PAUSED" ? "Resume" : "Pause"}
          </Button>
          <ToolbarButton
            label="Stop"
            icon={<Square className="ui-icon" />}
            onClick={() => void cancel()}
          />
        </>
      )}
      <span className="ui-divider" />
      <ToolbarButton
        label="Activity"
        active={desktop.drawerVisible}
        icon={<Logs className="ui-icon" />}
        onClick={() => desktop.toggle("drawerVisible")}
      />
      <ToolbarButton
        label="Settings"
        icon={<Settings className="ui-icon" />}
        onClick={() => desktop.setValue("settingsOpen", true)}
      />
    </header>
  );
}
