import { cn, focusRing } from "./utils";

/** @param {{label: import("react").ReactNode, checked: boolean, onChange?: (checked: boolean) => void, disabled?: boolean}} props */
export function Switch({ label, checked, onChange, disabled = false }) {
  return (
    <label className="ui-switch">
      <span>{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange?.(!checked)}
        className={cn(
          "ui-switch-track",
          checked ? "is-on" : "is-off",
          focusRing,
        )}
      >
        <span
          className={cn("ui-switch-thumb", checked ? "is-on" : "is-off")}
        />
      </button>
    </label>
  );
}
