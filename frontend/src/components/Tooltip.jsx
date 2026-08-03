/** @param {{content: import("react").ReactNode, children: import("react").ReactNode}} props */
export function Tooltip({ content, children }) {
  return (
    <span className="group relative inline-flex">
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 hidden -translate-x-1/2 whitespace-nowrap rounded-xl border border-mg-border bg-mg-elevated px-2.5 py-1 text-[11px] text-mg-primary shadow-soft group-hover:block group-focus-within:block"
      >
        {content}
      </span>
    </span>
  );
}
