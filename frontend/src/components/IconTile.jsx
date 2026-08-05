import { cn } from "./utils";

/** @typedef {"sm"|"md"|"lg"} IconTileSize */

const SIZES = {
  sm: "size-6 rounded-lg",
  md: "size-8 rounded-xl",
  lg: "size-10 rounded-2xl",
};

/**
 * Reusable icon surface used in panels, library rows, dialogs, and nodes.
 * @param {{
 *   children?: import("react").ReactNode,
 *   size?: IconTileSize,
 *   className?: string,
 *   as?: "span"|"div"|"button",
 * } & import("react").HTMLAttributes<HTMLElement>} props
 */
export function IconTile({
  children,
  size = "md",
  className = "",
  as: Tag = "span",
  ...props
}) {
  return (
    <Tag
      className={cn(
        "grid shrink-0 place-items-center border border-mg-border bg-mg-elevated text-mg-secondary transition",
        SIZES[size] || SIZES.md,
        className,
      )}
      {...props}
    >
      {children}
    </Tag>
  );
}
