import { cn } from "./utils";

export function Panel({ title, subtitle, icon, actions, children, className = "", bodyClassName = "" }) {
  return <section className={cn("ui-panel border-mg-border", className)}>
    {(title || actions) && <header className="ui-panel-header">
      {icon && <span className="ui-panel-icon">{icon}</span>}
      <div className="min-w-0 flex-1">
        {title && <h2 className="ui-panel-title">{title}</h2>}
        {subtitle && <p className="ui-panel-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-1">{actions}</div>}
    </header>}
    <div className={cn("min-h-0 flex-1", bodyClassName)}>{children}</div>
  </section>;
}
