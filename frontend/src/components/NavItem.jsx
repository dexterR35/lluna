import { cn } from "./utils";

/**
 * @param {{
 *   active?: boolean,
 *   icon?: import("react").ReactNode,
 *   children: import("react").ReactNode,
 *   className?: string,
 * } & import("react").ButtonHTMLAttributes<HTMLButtonElement>} props
 */
export function NavItem({ active = false, icon, children, className = "", ...props }) {
  return (
    <button
      type="button"
      className={cn("ui-nav-item", active && "is-active", className)}
      {...props}
    >
      {icon}
      <span className="truncate">{children}</span>
    </button>
  );
}
