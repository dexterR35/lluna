import { AlertTriangle, CheckCircle2, Download, ScrollText, Stethoscope } from "lucide-react";
import { EmptyState, Panel, ProgressBar, Tabs } from "../components";
import { useDesktopStore } from "../state/desktopStore";
import { useEditorStore } from "../state/editorStore";
import { useRunStore } from "../state/runStore";
import { useServerStore } from "../state/serverStore";

function ProblemRow({ issue, label, onFocus }) {
  const clickable = Boolean(issue.nodeId);
  const tone = issue.severity === "error"
    ? "border-mg-error text-mg-error"
    : "border-mg-warning text-mg-warning";
  const className = `flex w-full gap-2 rounded-lg border bg-mg-app/30 p-2 text-left text-[10px] ${tone}${clickable ? " hover:bg-mg-selected/40" : ""}`;
  const body = (
    <>
      <AlertTriangle className="size-3.5 shrink-0" />
      <div>
        <strong>{issue.code}</strong>
        {label ? <p className="text-[9px] opacity-70">{label}</p> : null}
        <p>{issue.message}</p>
        {issue.action ? <p className="mt-1 text-[9px] opacity-70">{issue.action}</p> : null}
      </div>
    </>
  );
  if (clickable) {
    return (
      <button type="button" onClick={() => onFocus(issue.nodeId)} className={className}>
        {body}
      </button>
    );
  }
  return <div className={className}>{body}</div>;
}

export function BottomDrawer({ issues }) {
  const tab = useDesktopStore((store) => store.drawerTab);
  const set = useDesktopStore((store) => store.setValue);
  const logs = useRunStore((store) => store.logs);
  const run = useRunStore((store) => store.run);
  const downloads = useServerStore((store) => store.downloads);
  const diagnostics = useServerStore((store) => store.diagnostics);
  const nodes = useEditorStore((store) => store.nodes);
  const focusNode = useEditorStore((store) => store.focusNode);
  const labels = Object.fromEntries(
    nodes.map((node) => [node.id, node.data.label || node.data.definition?.name || node.data.schemaId]),
  );
  const downloadCount = (downloads?.active?.length || 0) + (downloads?.pending?.length || 0);
  const tabs = [
    { id: "logs", label: "Run log", icon: <ScrollText className="size-3" />, count: logs.length || undefined },
    { id: "downloads", label: "Downloads", icon: <Download className="size-3" />, count: downloadCount || undefined },
    { id: "problems", label: "Problems", icon: <AlertTriangle className="size-3" />, count: issues.length || undefined },
    { id: "diagnostics", label: "Diagnostics", icon: <Stethoscope className="size-3" /> },
  ];

  return (
    <Panel className="h-full border-t" bodyClassName="flex min-h-0 flex-col">
      <Tabs tabs={tabs} value={tab} onChange={(value) => set("drawerTab", value)} />
      <div className="min-h-0 flex-1 overflow-auto p-2.5 text-[11px]">
        {tab === "logs" && (logs.length ? (
          <div role="log" className="grid gap-0.5 font-mono text-[10px]">
            {logs.map((line) => (
              <div key={line.id} className="grid grid-cols-[5.5rem_1fr] gap-2 rounded px-1.5 py-1 odd:bg-mg-elevated/35">
                <span className="text-mg-secondary">{new Date(line.timestamp).toLocaleTimeString()}</span>
                <span>{line.message}</span>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={<ScrollText className="size-5" />} title="No run log" description="Execution messages appear here." />
        ))}
        {tab === "downloads" && (
          <div className="grid gap-3">
            {[...(downloads?.active || []), ...(downloads?.pending || [])].map((item) => (
              <div key={`${item.kind}-${item.key}`} className="ui-card p-2">
                <div className="flex justify-between">
                  <span>{item.key}</span>
                  <span className="text-mg-secondary">{item.kind}</span>
                </div>
                <ProgressBar value={item.progress || 0} />
              </div>
            ))}
            {!(downloads?.active?.length || downloads?.pending?.length) && (
              <EmptyState icon={<Download className="size-5" />} title="Download queue is empty" />
            )}
          </div>
        )}
        {tab === "problems" && (issues.length ? (
          <div className="grid gap-2">
            {issues.map((issue, index) => (
              <ProblemRow
                key={`${issue.code}-${index}`}
                issue={issue}
                label={issue.nodeId ? labels[issue.nodeId] : null}
                onFocus={focusNode}
              />
            ))}
          </div>
        ) : (
          <EmptyState icon={<CheckCircle2 className="size-5" />} title="No workflow problems" />
        ))}
        {tab === "diagnostics" && (
          <pre className="whitespace-pre-wrap font-mono text-[9px] leading-4 text-mg-secondary">{JSON.stringify(diagnostics, null, 2)}</pre>
        )}
      </div>
      {run && (
        <div className="border-t border-mg-border bg-mg-app/25 p-2">
          <ProgressBar value={run.progress || 0} label={`Run ${run.status}`} showLabel />
        </div>
      )}
    </Panel>
  );
}
