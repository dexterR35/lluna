import { forwardRef } from "react";
import { cn, focusRing } from "./utils";

/** @typedef {import("react").ButtonHTMLAttributes<HTMLButtonElement> & {label: string}} IconButtonProps */

/** @param {IconButtonProps} props @param {import("react").ForwardedRef<HTMLButtonElement>} ref */
function IconButtonComponent(
  { label, children, className = "", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      aria-label={label}
      title={label}
      className={cn(
        "grid size-8 shrink-0 cursor-pointer place-items-center rounded-full border border-transparent text-mg-secondary transition hover:border-mg-border hover:bg-mg-elevated hover:text-mg-primary disabled:cursor-not-allowed disabled:opacity-40",
        focusRing,
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export const IconButton = forwardRef(IconButtonComponent);
