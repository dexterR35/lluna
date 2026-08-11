import { forwardRef } from "react";
import { cn } from "./utils";

/**
 * @typedef {import("react").InputHTMLAttributes<HTMLInputElement> & {
 *   label?: import("react").ReactNode,
 *   hint?: import("react").ReactNode,
 *   bare?: boolean,
 * }} TextFieldProps
 */

/** @param {TextFieldProps} props @param {import("react").ForwardedRef<HTMLInputElement>} ref */
function TextFieldComponent(
  { label, hint, bare = false, className = "", ...props },
  ref,
) {
  const id =
    props.id ||
    `field-${String(label || "input")
      .toLowerCase()
      .replaceAll(" ", "-")}`;
  const control = (
    <input
      ref={ref}
      id={id}
      className={cn("ui-input", bare && "is-bare", className)}
      {...props}
    />
  );
  if (bare && !label) return control;
  return (
    <label className="ui-field-label" htmlFor={id}>
      {label && <span>{label}</span>}
      {control}
      {hint && <span className="ui-help">{hint}</span>}
    </label>
  );
}

export const TextField = forwardRef(TextFieldComponent);
