import { cn,focusRing } from "./utils";
/** @param {import("react").InputHTMLAttributes<HTMLInputElement> & {label: import("react").ReactNode}} props */
export function Checkbox({label,className="",...props}){return <label className={cn("flex min-h-8 items-center gap-2 text-xs text-mg-primary",className)}><input type="checkbox" className={cn("size-3.5 rounded accent-mg-accent",focusRing)} {...props}/><span>{label}</span></label>}
