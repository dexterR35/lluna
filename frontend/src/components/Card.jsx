import { cn } from "./utils";

/**
 * Reusable surface card — panels, drawers, and previews share this.
 * @param {{
 *   children?: import("react").ReactNode,
 *   className?: string,
 *   as?: "article"|"div"|"section"|"li"|"button",
 *   type?: "button"|"submit"|"reset",
 *   padded?: boolean,
 *   interactive?: boolean,
 *   selected?: boolean,
 * } & import("react").HTMLAttributes<HTMLElement>} props
 */
export function Card({
  children,
  className = "",
  as: Tag = "div",
  padded = true,
  interactive = false,
  selected = false,
  ...props
}) {
  return (
    <Tag
      className={cn(
        "ui-card",
        selected && "border-mg-accent bg-mg-accent/10",
        padded && "p-3.5",
        interactive &&
          !selected &&
          "transition hover:border-mg-secondary/40 hover:bg-mg-selected",
        className,
      )}
      {...props}
    >
      {children}
    </Tag>
  );
}
