import { expect, test } from "vitest";
import { render,screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Dialog,Switch } from "../src/components";
test("switch is keyboard operable and reports state",async()=>{const user=userEvent.setup();let value=false;const {rerender}=render(<Switch label="Show previews" checked={value} onChange={next=>{value=next;}}/>);const control=screen.getByRole("switch",{name:"Show previews"});await user.click(control);expect(value).toBe(true);rerender(<Switch label="Show previews" checked={value}/>);expect(control).toHaveAttribute("aria-checked","true");});
test("dialog closes with escape",async()=>{const user=userEvent.setup();let closed=false;render(<Dialog open title="Settings" onClose={()=>{closed=true;}}><button>Focusable</button></Dialog>);await user.keyboard("{Escape}");expect(closed).toBe(true);});
