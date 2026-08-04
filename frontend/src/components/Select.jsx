import { forwardRef } from "react";
import { cn } from "./utils";

/** @typedef {{value: string|number, label: string, disabled?: boolean}} SelectOption */
/** @typedef {import("react").SelectHTMLAttributes<HTMLSelectElement> & {label?: import("react").ReactNode, options?: SelectOption[], error?: import("react").ReactNode, hint?: import("react").ReactNode}} SelectProps */

/** @param {SelectProps} props @param {import("react").ForwardedRef<HTMLSelectElement>} ref */
function SelectComponent(
  { label, options = [], error, hint, className = "", ...props },
  ref,
) {
  return (
    <label className="ui-field-label">
      {label && <span>{label}</span>}
      <select
        ref={ref}
        aria-invalid={Boolean(error)}
        className={cn(
          "ui-control",
          Boolean(error) && "border-mg-error",
          className,
        )}
        {...props}
      >
        {options.map((option) => (
          <option
            key={String(option.value)}
            value={option.value}
            disabled={option.disabled}
          >
            {option.label}
          </option>
        ))}
      </select>
      {error && (
        <span role="alert" className="ui-help text-mg-error">
          {error}
        </span>
      )}
      {!error && hint && <span className="ui-help">{hint}</span>}
    </label>
  );
}

export const Select = forwardRef(SelectComponent);
