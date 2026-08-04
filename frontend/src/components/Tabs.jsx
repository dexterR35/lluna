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
      className={cn("ui-tabs", className)}
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
            "ui-tab",
            focusRing,
            value === tab.id && "is-active",
          )}
        >
          {tab.icon}
          {tab.label}
          {tab.count !== undefined && (
            <span className="ui-tab-count">{tab.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}
