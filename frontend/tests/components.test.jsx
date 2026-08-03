import { expect, test, vi } from "vitest";
import { fireEvent, render,screen,waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Dialog,Switch } from "../src/components";
import { NodeParameterField } from "../src/nodes/NodeParameterField";
test("switch is keyboard operable and reports state",async()=>{const user=userEvent.setup();let value=false;const {rerender}=render(<Switch label="Show previews" checked={value} onChange={next=>{value=next;}}/>);const control=screen.getByRole("switch",{name:"Show previews"});await user.click(control);expect(value).toBe(true);rerender(<Switch label="Show previews" checked={value}/>);expect(control).toHaveAttribute("aria-checked","true");});
test("dialog closes with escape",async()=>{const user=userEvent.setup();let closed=false;render(<Dialog open title="Settings" onClose={()=>{closed=true;}}><button>Focusable</button></Dialog>);await user.keyboard("{Escape}");expect(closed).toBe(true);});
test("image parameter accepts a dropped file and returns its preview artifact",async()=>{
  const registerDroppedFiles=vi.fn().mockResolvedValue([{grantId:"grant-1",artifactId:"artifact-1",name:"portrait.png",mediaType:"image/png"}]);
  const previousDesktop=window.midgardDesktop;
  window.midgardDesktop={registerDroppedFiles};
  const onChange=vi.fn();
  render(<NodeParameterField definition={{id:"pathGrantId",label:"Image file",type:"file"}} nodeDefinition={{schemaId:"midgard.input.image"}} onChange={onChange}/>);
  const file=new File(["image"],"portrait.png",{type:"image/png"});
  fireEvent.drop(screen.getByRole("button",{name:"Drop image file"}),{dataTransfer:{files:[file]}});
  await waitFor(()=>expect(onChange).toHaveBeenCalledWith("grant-1",expect.objectContaining({artifactId:"artifact-1",name:"portrait.png"})));
  expect(registerDroppedFiles).toHaveBeenCalledWith([file]);
  window.midgardDesktop=previousDesktop;
});
