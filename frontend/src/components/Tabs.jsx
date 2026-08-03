import { cn, focusRing } from "./utils";

/** @typedef {{id: string, label: import("react").ReactNode, icon?: import("react").ReactNode, count?: number}} TabItem */

/** @param {{tabs: TabItem[], value: string, onChange: (id: string) => void, label?: string, className?: string}} props */
export function Tabs({
  tabs,
  value,
  onChange,
  label = "Tabs",
  className = "",
}) {
  function key(
    /** @type {import("react").KeyboardEvent<HTMLButtonElement>} */ event,
    /** @type {number} */ index,
  ) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft")
      next = (index - 1 + tabs.length) % tabs.length;
    else return;
    event.preventDefault();
    onChange(tabs[next].id);
    const target = event.currentTarget.parentElement?.children[next];
    if (target instanceof HTMLElement) target.focus();
  }
  return (
    <div
      role="tablist"
      aria-label={label}
      className={cn(
        "flex h-11 items-center gap-1 border-b border-mg-border px-2.5",
        className,
      )}
    >
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={value === tab.id}
          tabIndex={value === tab.id ? 0 : -1}
          onKeyDown={(event) => key(event, index)}
          onClick={() => onChange(tab.id)}
          className={cn(
            "inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[11px] font-medium transition",
            focusRing,
            value === tab.id
              ? "bg-mg-elevated text-mg-primary"
              : "text-mg-muted hover:bg-mg-app hover:text-mg-secondary",
          )}
        >
          {tab.icon}
          {tab.label}
          {tab.count !== undefined && (
            <span className="rounded-full bg-mg-app px-1.5 text-[9px] tabular-nums text-mg-secondary">
              {tab.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
