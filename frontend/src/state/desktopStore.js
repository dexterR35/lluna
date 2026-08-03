import { create } from "zustand";
const defaults={libraryVisible:true,inspectorVisible:true,drawerVisible:true,minimapVisible:true,settingsOpen:false,modelsOpen:false,drawerTab:"logs",libraryWidth:270,inspectorWidth:330,drawerHeight:220};
function load(){try{return{...defaults,...JSON.parse(localStorage.getItem("midgard-layout")||"{}")};}catch{return defaults;}}
export const useDesktopStore=create((set,get)=>({...load(),setValue:(key,value)=>{set({[key]:value});localStorage.setItem("midgard-layout",JSON.stringify({...get(),[key]:value,setValue:undefined,reset:undefined}));},toggle:key=>get().setValue(key,!get()[key]),reset:()=>{set(defaults);localStorage.removeItem("midgard-layout");}}));
