import { cn } from "./utils";

/**
 * Reusable surface card — nodes, dialogs, drawers, and settings share this.
 * @param {{
 *   children?: import("react").ReactNode,
 *   className?: string,
 *   as?: "article"|"div"|"section"|"li"|"button",
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
        "rounded-2xl border bg-mg-node",
        selected
          ? "border-mg-accent bg-mg-accent/10"
          : "border-mg-border",
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
