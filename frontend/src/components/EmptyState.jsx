import { IconTile } from "./IconTile";
import { cn } from "./utils";

/** @param {{icon?: import("react").ReactNode, title: import("react").ReactNode, description?: import("react").ReactNode, action?: import("react").ReactNode, compact?: boolean}} props */
export function EmptyState({
  icon,
  title,
  description,
  action,
  compact = false,
}) {
  return (
    <div className={cn("ui-empty", compact ? "is-compact" : "is-roomy")}>
      <div className="max-w-xs">
        {icon && (
          <IconTile size="lg" className="mx-auto mb-3 bg-mg-elevated">
            {icon}
          </IconTile>
        )}
        <h3 className="ui-copy-title text-[12px]">{title}</h3>
        {description && (
          <p className="ui-copy-body mt-1.5 leading-5">{description}</p>
        )}
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  );
}
