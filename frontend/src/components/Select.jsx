import { forwardRef } from "react";
import { cn } from "./utils";

/** @typedef {{value: string|number, label: string, disabled?: boolean}} SelectOption */
/**
 * @typedef {import("react").SelectHTMLAttributes<HTMLSelectElement> & {
 *   label?: import("react").ReactNode,
 *   options?: SelectOption[],
 *   hint?: import("react").ReactNode,
 *   bare?: boolean,
 * }} SelectProps
 */

/** @param {SelectProps} props @param {import("react").ForwardedRef<HTMLSelectElement>} ref */
function SelectComponent(
  { label, options = [], hint, bare = false, className = "", ...props },
  ref,
) {
  const id =
    props.id ||
    (label
      ? `select-${String(label)
          .toLowerCase()
          .replaceAll(" ", "-")}`
      : undefined);
  const control = (
    <select
      ref={ref}
      id={id}
      className={cn("ui-input", bare && "is-bare", className)}
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

export const Select = forwardRef(SelectComponent);
