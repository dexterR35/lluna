import { beforeEach,expect,test } from "vitest";
import { useEditorStore } from "../src/state/editorStore";
const definition={schemaId:"test.number",schemaVersion:1,name:"Number",parameters:[{id:"value",default:1}],inputs:[],outputs:[{id:"value",type:"INTEGER"}]};
beforeEach(()=>useEditorStore.setState({nodes:[],edges:[],groups:[],past:[],future:[],definitions:[definition],dirty:false}));
test("graph edits are undoable",()=>{useEditorStore.getState().addNode("test.number",{x:1,y:2});expect(useEditorStore.getState().nodes).toHaveLength(1);useEditorStore.getState().undo();expect(useEditorStore.getState().nodes).toHaveLength(0);useEditorStore.getState().redo();expect(useEditorStore.getState().nodes).toHaveLength(1);});
test("serialization never copies backend definitions",()=>{useEditorStore.getState().addNode("test.number");const document=useEditorStore.getState().serialize();expect(document.nodes[0].schemaId).toBe("test.number");expect(document.nodes[0]).not.toHaveProperty("definition");});
