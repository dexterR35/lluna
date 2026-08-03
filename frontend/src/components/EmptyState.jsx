import { IconTile } from "./IconTile";

/** @param {{icon?: import("react").ReactNode, title: import("react").ReactNode, description?: import("react").ReactNode, action?: import("react").ReactNode, compact?: boolean}} props */
export function EmptyState({
  icon,
  title,
  description,
  action,
  compact = false,
}) {
  return (
    <div
      className={`grid h-full place-items-center text-center ${compact ? "min-h-28 p-4" : "min-h-36 p-5"}`}
    >
      <div className="max-w-xs">
        {icon && (
          <IconTile size="lg" className="mx-auto mb-3 bg-mg-elevated">
            {icon}
          </IconTile>
        )}
        <h3 className="text-[12px] font-semibold tracking-tight text-mg-primary">
          {title}
        </h3>
        {description && (
          <p className="mt-1.5 text-[11px] leading-5 text-mg-secondary">
            {description}
          </p>
        )}
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  );
}
