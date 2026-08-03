/** @param {{value?: number, label?: string, showLabel?: boolean}} props */
export function ProgressBar({ value = 0, label = "Progress", showLabel = false }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="grid gap-1.5">
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={clamped}
        className="h-1.5 overflow-hidden rounded-full bg-mg-app"
      >
        <div
          className="h-full rounded-full bg-gradient-to-r from-mg-accent to-mg-running transition-[width]"
          style={{ width: `${clamped}%` }}
        />
      </div>
      {showLabel && (
        <span className="flex justify-between text-[10px] text-mg-muted">
          <span>{label}</span>
          <strong className="font-medium text-mg-secondary">
            {Math.round(clamped)}%
          </strong>
        </span>
      )}
    </div>
  );
}
