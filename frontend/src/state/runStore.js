import { create } from "zustand";
import { api } from "../api/client";
const terminal=new Set(["COMPLETED","FAILED","CANCELLED"]);
const nodeStatus={started:"RUNNING",progress:"RUNNING",completed:"SUCCEEDED",cached:"CACHED",failed:"FAILED",cancelled:"CANCELLED",queued:"QUEUED",paused:"PAUSED"};
export const useRunStore=create((set,get)=>({
  run:null,nodeStates:{},logs:[],connection:"connecting",setConnection:connection=>set({connection}),
  async start(workflow,mode="all",selectedNodeIds=[]){const run=await api("/api/runs",{method:"POST",body:JSON.stringify({workflow,mode,selectedNodeIds})});set({run,nodeStates:run.nodes||{},logs:[]});return run;},
  async pause(){const run=get().run;if(run)set({run:await api(`/api/runs/${run.runId}/pause`,{method:"POST"})});},
  async resume(){const run=get().run;if(run)set({run:await api(`/api/runs/${run.runId}/resume`,{method:"POST"})});},
  async cancel(){const run=get().run;if(run)set({run:await api(`/api/runs/${run.runId}/cancel`,{method:"POST"})});},
  async clearCache(){const run=get().run;if(run)await api(`/api/runs/${run.runId}/clear-cache`,{method:"POST"});},
  handleEvent(event){const current=get().run;if(event.runId&&current&&event.runId!==current.runId)return;
    if(event.type==="node.log")set(state=>({logs:[...state.logs.slice(-999),{id:event.eventId,nodeId:event.nodeId,message:event.payload.message,timestamp:event.timestamp}]}));
    if(event.nodeId&&event.type.startsWith("node.")){const key=event.type.split(".")[1];const status=nodeStatus[key]||key.toUpperCase();set(state=>{const previous=state.nodeStates[event.nodeId]||{};const progress=event.payload.progress??(["SUCCEEDED","CACHED"].includes(status)?100:previous.progress||0);const nodeStates={...state.nodeStates,[event.nodeId]:{...previous,status,progress,artifactIds:event.payload.artifactIds||previous.artifactIds||[]}};const values=Object.values(nodeStates);const overall=values.length?Math.round(values.reduce((sum,item)=>sum+(item.progress||0),0)/values.length):0;window.midgardDesktop?.setRunProgress(overall/100);return{nodeStates,run:state.run?{...state.run,progress:overall}:state.run};});}
    if(event.type.startsWith("run.")){const key=event.type.split(".")[1];const status={started:"RUNNING",pause_requested:"PAUSE_REQUESTED",resumed:"RUNNING"}[key]||key.toUpperCase();set(state=>({run:state.run?{...state.run,status,progress:status==="COMPLETED"?100:state.run.progress,artifactIds:event.payload.artifactIds||state.run.artifactIds,error:status==="FAILED"?event.payload:state.run.error}:state.run}));if(terminal.has(status))window.midgardDesktop?.setRunProgress(-1);}
  },
}));
