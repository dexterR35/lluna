import { cn } from "./utils";

/** @typedef {"neutral"|"success"|"warning"|"error"|"running"|"cached"|"accent"} BadgeTone */
/** @typedef {"xs"|"sm"|"md"} BadgeSize */

const TONES = {
  neutral: "border-mg-border bg-mg-elevated text-mg-secondary",
  success: "border-mg-success/30 bg-mg-success/10 text-mg-success",
  warning: "border-mg-warning/30 bg-mg-warning/10 text-mg-warning",
  error: "border-mg-error/30 bg-mg-error/10 text-mg-error",
  running: "border-mg-running/30 bg-mg-running/10 text-mg-running",
  cached: "border-mg-cached/30 bg-mg-cached/10 text-mg-cached",
  accent: "border-mg-accent/30 bg-mg-accent/10 text-mg-accent",
};

const SIZES = {
  xs: "min-h-4 gap-0.5 px-1.5 py-px text-[8px] font-semibold tracking-wide",
  sm: "min-h-5 gap-1 px-2 py-0.5 text-[9px] font-semibold tracking-wide",
  md: "min-h-7 gap-1 px-2.5 text-[10px] font-medium",
};

/**
 * Modern pill badge — one component for status, meta, chips, and node pills.
 * @param {{
 *   children?: import("react").ReactNode,
 *   tone?: BadgeTone,
 *   size?: BadgeSize,
 *   className?: string,
 *   as?: "span"|"div"|"button"|"label",
 *   title?: string,
 * } & import("react").HTMLAttributes<HTMLElement>} props
 */
export function Badge({
  children,
  tone = "neutral",
  size = "sm",
  className = "",
  as: Tag = "span",
  ...props
}) {
  return (
    <Tag
      className={cn(
        "inline-flex max-w-full items-center rounded-full border transition",
        TONES[tone] || TONES.neutral,
        SIZES[size] || SIZES.sm,
        className,
      )}
      {...props}
    >
      {children}
    </Tag>
  );
}
