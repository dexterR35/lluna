import { useEffect } from "react";
import { DropdownMenu } from "./DropdownMenu";

/** @param {{open: boolean, x: number, y: number, items: import("./DropdownMenu").DropdownEntry[], onSelect: (id: string) => void, onClose: () => void}} props */
export function ContextMenu({ open, x, y, items, onSelect, onClose }) {
  useEffect(() => {
    if (!open) return;
    const close = () => onClose();
    document.addEventListener("pointerdown", close);
    document.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("scroll", close, true);
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div
      className="fixed z-50 overflow-hidden rounded-2xl border border-mg-border bg-mg-panel shadow-soft"
      style={{ left: x, top: y }}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <DropdownMenu
        items={items}
        onSelect={(id) => {
          onSelect(id);
          onClose();
        }}
      />
    </div>
  );
}
