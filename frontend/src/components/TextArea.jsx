import { forwardRef } from "react";
import { cn } from "./utils";

/** @typedef {import("react").TextareaHTMLAttributes<HTMLTextAreaElement> & {label?: import("react").ReactNode, hint?: import("react").ReactNode}} TextAreaProps */

/** @param {TextAreaProps} props @param {import("react").ForwardedRef<HTMLTextAreaElement>} ref */
function TextAreaComponent({ label, hint, className = "", ...props }, ref) {
  return (
    <label className="ui-field-label">
      {label && <span>{label}</span>}
      <textarea ref={ref} className={cn("ui-input is-area", className)} {...props} />
      {hint && <span className="ui-help">{hint}</span>}
    </label>
  );
}

export const TextArea = forwardRef(TextAreaComponent);
