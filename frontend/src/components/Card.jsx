import { cn } from "./utils";

/**
 * Reusable surface card — panels, drawers, and previews share this.
 * @param {{
 *   children?: import("react").ReactNode,
 *   className?: string,
 *   padded?: boolean,
 * } & import("react").HTMLAttributes<HTMLDivElement>} props
 */
export function Card({ children, className = "", padded = true, ...props }) {
  return (
    <div className={cn("ui-card", padded && "p-3.5", className)} {...props}>
      {children}
    </div>
  );
}
