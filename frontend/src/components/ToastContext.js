import { createContext, useContext } from "react";
/** @typedef {{push: (message: string, tone?: string) => string, dismiss: (id: string) => void}} ToastApi */
export const ToastContext = createContext(/** @type {ToastApi | null} */(null));
export function useToast() { const value = useContext(ToastContext); if (!value) throw new Error("useToast requires ToastProvider"); return value; }
