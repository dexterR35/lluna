import { cn, focusRing } from "./utils";

/** @typedef {{separator: true} | {separator?: false, id: string, label: string, shortcut?: string, disabled?: boolean}} DropdownEntry */

/** @param {{items: DropdownEntry[], onSelect: (id: string) => void}} props */
export function DropdownMenu({ items, onSelect }) {
  return (
    <div role="menu" className="grid min-w-52 gap-0.5 p-1.5">
      {items.map((entry, index) =>
        entry.separator ? (
          <hr key={index} className="my-1 border-mg-border" />
        ) : (
          <button
            key={entry.id}
            role="menuitem"
            disabled={entry.disabled}
            onClick={() => onSelect(entry.id)}
            className={cn(
              "flex min-h-9 items-center justify-between rounded-mg px-3 text-left text-[12px] text-mg-primary hover:bg-mg-elevated disabled:opacity-40",
              focusRing,
            )}
          >
            <span>{entry.label}</span>
            {entry.shortcut && (
              <kbd className="text-[10px] text-mg-muted">{entry.shortcut}</kbd>
            )}
          </button>
        ),
      )}
    </div>
  );
}
