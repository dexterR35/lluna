import { cn } from "./utils";

/**
 * @param {{
 *   title: import("react").ReactNode,
 *   description?: import("react").ReactNode,
 *   className?: string,
 * }} props
 */
export function SectionHeader({ title, description, className = "" }) {
  return (
    <header className={cn("ui-settings-header", className)}>
      <h3 className="ui-copy-title">{title}</h3>
      {description && <p className="ui-copy-muted">{description}</p>}
    </header>
  );
}
