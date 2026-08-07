import { useCallback, useMemo, useState } from "react";
import { X } from "../icons";
import { IconButton } from "./IconButton";
import { ToastContext } from "./ToastContext";

/** @typedef {{id: string, message: string, tone: string}} ToastRecord */

/** @param {{children: import("react").ReactNode}} props */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState(/** @type {ToastRecord[]} */ ([]));
  const dismiss = useCallback(
    /** @param {string} id */ (id) =>
      setToasts((items) => items.filter((item) => item.id !== id)),
    [],
  );
  const push = useCallback(
    /** @param {string} message @param {string} [tone] */ (
      message,
      tone = "info",
    ) => {
      const id = crypto.randomUUID();
      setToasts((items) => [...items, { id, message, tone }]);
      setTimeout(() => dismiss(id), 5000);
      return id;
    },
    [dismiss],
  );
  const value = useMemo(() => ({ push, dismiss }), [push, dismiss]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="fixed bottom-8 right-5 z-[70] grid w-80 gap-2"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className={`flex items-center gap-3 rounded-mg-lg border border-mg-border bg-mg-panel p-3 text-sm text-mg-primary  ${toast.tone === "error" ? "border-mg-error/60" : ""}`}
          >
            <span className="flex-1">{toast.message}</span>
            <IconButton
              label="Dismiss notification"
              onClick={() => dismiss(toast.id)}
            >
              <X className="size-4" />
            </IconButton>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
