import { cn } from "./utils";
import { Button } from "./Button";

/**
 * Label + optional description with a trailing control/button.
 * @param {{
 *   title: import("react").ReactNode,
 *   description?: import("react").ReactNode,
 *   action?: import("react").ReactNode,
 *   className?: string,
 * }} props
 */
export function ActionRow({ title, description, action, className = "" }) {
  return (
    <div className={cn("ui-action-row ui-rule pt-3", className)}>
      <div className="min-w-0">
        <p className="text-[11px] font-medium text-mg-primary">{title}</p>
        {description && <p className="ui-copy-muted mt-0.5">{description}</p>}
      </div>
      {action}
    </div>
  );
}

/**
 * Compact ghost/secondary action used in settings footers.
 * @param {{
 *   children: import("react").ReactNode,
 *   onClick?: () => void,
 *   variant?: import("react").ComponentProps<typeof Button>["variant"],
 * }} props
 */
export function CompactButton({ children, onClick, variant = "ghost" }) {
  return (
    <Button
      variant={variant}
      className="min-h-7 shrink-0 px-2.5 text-[10px]"
      onClick={onClick}
    >
      {children}
    </Button>
  );
}
