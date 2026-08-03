import { AlertTriangle, CheckCircle2, Download, ScrollText } from "lucide-react";
import { EmptyState, Panel, ProgressBar, Tabs } from "../components";
import { useDesktopStore } from "../state/desktopStore";
import { useRunStore } from "../state/runStore";
import { useServerStore } from "../state/serverStore";
const tabs=[{id:"logs",label:"Run log"},{id:"downloads",label:"Downloads"},{id:"problems",label:"Problems"},{id:"diagnostics",label:"Diagnostics"}];
export function BottomDrawer({ issues }) { const tab=useDesktopStore(store=>store.drawerTab); const set=useDesktopStore(store=>store.setValue); const logs=useRunStore(store=>store.logs); const run=useRunStore(store=>store.run); const downloads=useServerStore(store=>store.downloads); const diagnostics=useServerStore(store=>store.diagnostics);
  return <Panel className="h-full border-t" bodyClassName="flex min-h-0 flex-col"><Tabs tabs={tabs} value={tab} onChange={value=>set("drawerTab",value)} /><div className="min-h-0 flex-1 overflow-auto p-3 text-sm">
    {tab==="logs" && (logs.length ? <div role="log" className="grid gap-1 font-mono text-xs">{logs.map(line=><div key={line.id} className="grid grid-cols-[7rem_1fr] gap-3"><span className="text-mg-secondary">{new Date(line.timestamp).toLocaleTimeString()}</span><span>{line.message}</span></div>)}</div> : <EmptyState icon={<ScrollText className="size-5"/>} title="No run log" description="Execution messages appear here." />)}
    {tab==="downloads" && <div className="grid gap-3">{[...(downloads?.active||[]),...(downloads?.pending||[])].map(item=><div key={`${item.kind}-${item.key}`} className="rounded-lg border border-mg-border p-3"><div className="flex justify-between"><span>{item.key}</span><span className="text-mg-secondary">{item.kind}</span></div><ProgressBar value={item.progress||0}/></div>)}{!(downloads?.active?.length||downloads?.pending?.length)&&<EmptyState icon={<Download className="size-5"/>} title="Download queue is empty" />}</div>}
    {tab==="problems" && (issues.length ? <div className="grid gap-2">{issues.map((issue,index)=><div key={`${issue.code}-${index}`} className={`flex gap-2 rounded-lg border p-3 ${issue.severity==="error"?"border-mg-error text-mg-error":"border-mg-warning text-mg-warning"}`}><AlertTriangle className="size-4 shrink-0"/><div><strong>{issue.code}</strong><p>{issue.message}</p></div></div>)}</div>:<EmptyState icon={<CheckCircle2 className="size-5"/>} title="No workflow problems" />)}
    {tab==="diagnostics" && <pre className="whitespace-pre-wrap text-xs text-mg-secondary">{JSON.stringify(diagnostics,null,2)}</pre>}
  </div>{run&&<div className="border-t border-mg-border p-2"><ProgressBar value={run.progress||0} label={`Run ${run.status}`} showLabel/></div>}</Panel>;
}
