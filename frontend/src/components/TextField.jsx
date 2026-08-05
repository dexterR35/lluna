import { forwardRef } from "react";
import { cn } from "./utils";

/**
 * @typedef {import("react").InputHTMLAttributes<HTMLInputElement> & {
 *   label?: import("react").ReactNode,
 *   error?: import("react").ReactNode,
 *   hint?: import("react").ReactNode,
 *   bare?: boolean,
 * }} TextFieldProps
 */

/** @param {TextFieldProps} props @param {import("react").ForwardedRef<HTMLInputElement>} ref */
function TextFieldComponent(
  { label, error, hint, bare = false, className = "", ...props },
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
      aria-invalid={Boolean(error)}
      aria-describedby={error ? `${id}-error` : undefined}
      className={cn(
        "ui-input",
        bare && "is-bare",
        Boolean(error) && "is-error",
        className,
      )}
      {...props}
    />
  );
  if (bare && !label) return control;
  return (
    <label className="ui-field-label" htmlFor={id}>
      {label && <span>{label}</span>}
      {control}
      {error && (
        <span id={`${id}-error`} role="alert" className="ui-help text-mg-error">
          {error}
        </span>
      )}
      {!error && hint && <span className="ui-help">{hint}</span>}
    </label>
  );
}

export const TextField = forwardRef(TextFieldComponent);
