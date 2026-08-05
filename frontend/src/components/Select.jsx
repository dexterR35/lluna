import { forwardRef } from "react";
import { cn } from "./utils";

/** @typedef {{value: string|number, label: string, disabled?: boolean}} SelectOption */
/**
 * @typedef {import("react").SelectHTMLAttributes<HTMLSelectElement> & {
 *   label?: import("react").ReactNode,
 *   options?: SelectOption[],
 *   error?: import("react").ReactNode,
 *   hint?: import("react").ReactNode,
 *   bare?: boolean,
 * }} SelectProps
 */

/** @param {SelectProps} props @param {import("react").ForwardedRef<HTMLSelectElement>} ref */
function SelectComponent(
  {
    label,
    options = [],
    error,
    hint,
    bare = false,
    className = "",
    ...props
  },
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
      aria-invalid={Boolean(error)}
      className={cn(
        "ui-input",
        bare && "is-bare",
        Boolean(error) && "is-error",
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
  );
  if (bare && !label) return control;
  return (
    <label className="ui-field-label" htmlFor={id}>
      {label && <span>{label}</span>}
      {control}
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
