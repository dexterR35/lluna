import { forwardRef } from "react";
import { LoaderCircle } from "lucide-react";
import { cn, focusRing } from "./utils";

/** @typedef {Omit<import("react").ButtonHTMLAttributes<HTMLButtonElement>, "disabled"> & {variant?: "primary"|"secondary"|"danger"|"ghost", loading?: boolean, disabled?: boolean}} ButtonProps */

/** @param {ButtonProps} props @param {import("react").ForwardedRef<HTMLButtonElement>} ref */
function ButtonComponent(
  {
    children,
    variant = "primary",
    loading = false,
    className = "",
    disabled = false,
    ...props
  },
  ref,
) {
  const variants = {
    primary:
      "border border-mg-accent bg-mg-accent text-white hover:brightness-110",
    secondary:
      "border border-mg-border bg-mg-elevated text-mg-primary hover:border-mg-secondary/40 hover:bg-mg-selected",
    danger:
      "border border-mg-error/70 bg-mg-error/10 text-mg-error hover:bg-mg-error hover:text-white",
    ghost:
      "border border-transparent text-mg-secondary hover:bg-mg-elevated hover:text-mg-primary",
  };
  return (
    <button
      ref={ref}
      type="button"
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex min-h-8 cursor-pointer items-center justify-center gap-1.5 rounded-full px-3 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-40",
        focusRing,
        variants[variant],
        className,
      )}
      {...props}
    >
      {loading && <LoaderCircle aria-hidden className="size-3.5 animate-spin" />}
      {children}
    </button>
  );
}

export const Button = forwardRef(ButtonComponent);
