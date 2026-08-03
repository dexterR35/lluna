import { forwardRef } from "react"; import { cn } from "./utils";
/** @typedef {import("react").TextareaHTMLAttributes<HTMLTextAreaElement> & {label?: import("react").ReactNode, error?: import("react").ReactNode, hint?: import("react").ReactNode}} TextAreaProps */
/** @param {TextAreaProps} props @param {import("react").ForwardedRef<HTMLTextAreaElement>} ref */
function TextAreaComponent({label,error,hint,className="",...props},ref){return <label className="ui-field-label">{label&&<span>{label}</span>}<textarea ref={ref} aria-invalid={Boolean(error)} className={cn("ui-control min-h-20 resize-y py-2",Boolean(error)&&"border-mg-error",className)} {...props}/>{error&&<span role="alert" className="ui-help text-mg-error">{error}</span>}{!error&&hint&&<span className="ui-help">{hint}</span>}</label>}
export const TextArea=forwardRef(TextAreaComponent);
