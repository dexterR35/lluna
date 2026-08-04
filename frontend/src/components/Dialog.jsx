import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { IconButton } from "./IconButton";

/** @param {{open: boolean, onClose: () => void, title: import("react").ReactNode, description?: import("react").ReactNode, children?: import("react").ReactNode, footer?: import("react").ReactNode, wide?: boolean, className?: string, bodyClassName?: string}} props */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  wide = false,
  className = "",
  bodyClassName = "",
}) {
  const panel = useRef(/** @type {HTMLElement | null} */ (null));
  const previous = useRef(/** @type {HTMLElement | null} */ (null));
  useEffect(() => {
    if (!open) return;
    previous.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const node = panel.current;
    const firstControl = node?.querySelector(
      /** @type {string} */ (
        "button,input,select,textarea,[tabindex]:not([tabindex='-1'])"
      ),
    );
    if (firstControl instanceof HTMLElement) firstControl.focus();
    function key(/** @type {KeyboardEvent} */ event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
      if (event.key === "Tab" && node) {
        const focusable = [
          ...node.querySelectorAll(
            /** @type {string} */ (
              "button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex]:not([tabindex='-1'])"
            ),
          ),
        ].filter((item) => item instanceof HTMLElement);
        if (!focusable.length) return;
        const first = focusable[0],
          last = focusable.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous.current?.focus();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/65 p-6 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        aria-describedby={description ? "dialog-description" : undefined}
        className={`max-h-[86vh] w-full ${wide ? "max-w-5xl" : "max-w-xl"} overflow-hidden rounded-mg-lg border border-mg-border bg-mg-panel shadow-soft ${className}`}
      >
        <header className="ui-preview-bar is-header h-auto items-start justify-between gap-3 px-4 py-3.5">
          <div className="min-w-0">
            <h2
              id="dialog-title"
              className="ui-copy-title"
            >
              {title}
            </h2>
            {description && (
              <p
                id="dialog-description"
                className="ui-copy-body mt-1 leading-5"
              >
                {description}
              </p>
            )}
          </div>
          <IconButton label="Close dialog" onClick={onClose}>
            <X className="ui-icon" />
          </IconButton>
        </header>
        <div className={`max-h-[68vh] overflow-auto p-4 ${bodyClassName}`}>
          {children}
        </div>
        {footer && (
          <footer className="ui-actions ui-rule justify-end bg-mg-app/40 p-3">
            {footer}
          </footer>
        )}
      </section>
    </div>
  );
}
