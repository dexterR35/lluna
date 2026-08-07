import { Button } from "./Button";

/** @typedef {Omit<import("react").ComponentProps<typeof Button>, "children"> & {label: string, icon?: import("react").ReactNode, shortcut?: string, active?: boolean, showLabel?: boolean}} ToolbarButtonProps */

/** @param {ToolbarButtonProps} props */
export function ToolbarButton({
  label,
  icon,
  shortcut,
  active = false,
  showLabel = false,
  ...props
}) {
  return (
    <Button
      variant="ghost"
      aria-pressed={active || undefined}
      title={shortcut ? `${label} (${shortcut})` : label}
      className={`min-w-8 rounded-mg px-2 ${active ? "border-mg-border bg-mg-elevated text-mg-primary" : ""}`}
      {...props}
    >
      {icon}
      {showLabel && <span>{label}</span>}
    </Button>
  );
}
