import { useEffect, useRef } from "react";
/** @param {{open: boolean, onClose: () => void, anchor: import("react").ReactNode, children: import("react").ReactNode, align?: "left"|"right"}} props */
export function Popover({ open, onClose, anchor, children, align = "left" }) {
  const ref = useRef(/** @type {HTMLSpanElement | null} */ (null));
  useEffect(() => {
    if (!open) return;
    const close = (/** @type {PointerEvent} */ event) => {
      if (event.target instanceof Node && !ref.current?.contains(event.target))
        onClose();
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open, onClose]);
  return (
    <span ref={ref} className="relative inline-flex">
      {anchor}
      {open && (
        <span
          role="dialog"
          className={`absolute top-full z-40 mt-2 min-w-56 rounded-2xl border border-mg-border bg-mg-panel p-2 shadow-soft ${align === "right" ? "right-0" : "left-0"}`}
        >
          {children}
        </span>
      )}
    </span>
  );
}
