import { Cpu, Wifi, WifiOff } from "lucide-react";
import { Badge } from "../components";
import { useRunStore } from "../state/runStore";
import { useServerStore } from "../state/serverStore";

/** @param {{zoom: number}} props */
export function StatusBar({ zoom }) {
  const connection = useRunStore((store) => store.connection);
  const run = useRunStore((store) => store.run);
  const capabilities = useServerStore((store) => store.capabilities);
  const error = run?.error?.message;
  return (
    <footer className="flex h-full items-center gap-3 border-t border-mg-border bg-mg-panel px-3.5 text-[10px] text-mg-muted">
      <span className="flex items-center gap-1.5">
        {connection === "connected" ? (
          <Wifi className="size-3 text-mg-success" />
        ) : (
          <WifiOff className="size-3 text-mg-warning" />
        )}
        <span
          className={
            connection === "connected" ? "text-mg-secondary" : "text-mg-warning"
          }
        >
          {connection === "connected"
            ? "Backend ready"
            : `Backend ${connection}`}
        </span>
      </span>
      <span className="ui-divider !h-3" />
      <span className="flex items-center gap-1.5">
        <Cpu className="size-3" />
        {capabilities?.gpu?.name ||
          capabilities?.backends?.join(", ") ||
          "Detecting hardware"}
      </span>
      {error && (
        <span className="min-w-0 truncate text-mg-error" title={error}>
          {error}
        </span>
      )}
      <span className="ml-auto tabular-nums text-mg-secondary">
        {Math.round(zoom * 100)}%
      </span>
      {run && (
        <Badge
          tone={
            run.status === "RUNNING"
              ? "running"
              : run.status === "FAILED"
                ? "error"
                : "neutral"
          }
        >
          {run.status} · {run.progress || 0}%
        </Badge>
      )}
    </footer>
  );
}
