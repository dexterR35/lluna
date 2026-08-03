import { ChevronDown } from "lucide-react";
import { cn,focusRing } from "./utils";

export function Accordion({items,openIds,onToggle}) {
  return <div className="grid gap-2">{items.map(item => {
    const open = openIds.includes(item.id);
    return <section key={item.id} className={cn("ui-section overflow-hidden transition", open && "border-mg-secondary/30 bg-mg-elevated")}>
      <button type="button" aria-expanded={open} onClick={()=>onToggle(item.id)} className={cn("ui-section-header w-full text-left",focusRing)}>
        {item.icon && <span className="text-mg-secondary">{item.icon}</span>}
        <span className="min-w-0 flex-1">
          <span className="block truncate">{item.label}</span>
          {item.description && <span className="mt-0.5 block truncate text-[9px] font-normal text-mg-muted">{item.description}</span>}
        </span>
        {item.badge}
        <ChevronDown className={cn("size-3.5 text-mg-muted transition",open&&"rotate-180 text-mg-secondary")}/>
      </button>
      {open && <div className="border-t border-mg-border/80 p-3">{item.content}</div>}
    </section>;
  })}</div>;
}
