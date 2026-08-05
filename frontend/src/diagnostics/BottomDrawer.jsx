import {
  AlertTriangle,
  CheckCircle2,
  Download,
  History,
  ListOrdered,
  ScrollText,
  Stethoscope,
  X,
} from "../icons";
import {
  Badge,
  Button,
  EmptyState,
  Panel,
  ProgressBar,
  Tabs,
  useToast,
} from "../components";
import { useDesktopStore } from "../state/desktopStore";
import { useEditorStore } from "../state/editorStore";
import { useRunStore } from "../state/runStore";
import { useServerStore } from "../state/serverStore";

/** @param {number | null | undefined} bytes */
function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes == null || bytes < 0) return null;
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = units[0];
  for (let index = 1; value >= 1024 && index < units.length; index += 1) {
    value /= 1024;
    unit = units[index];
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${unit}`;
}

/** @param {number | null | undefined} seconds */
function formatEta(seconds) {
  if (!Number.isFinite(seconds) || seconds == null || seconds < 0) return null;
  const rounded = Math.ceil(seconds);
  if (rounded < 60) return `${rounded}s remaining`;
  return `${Math.ceil(rounded / 60)}m remaining`;
}

/** @param {import("../types").DownloadJob} item */
function downloadSubtitle(item) {
  if (item.state === "failed" || item.state === "cancelled") {
    return item.error || "The model install did not complete.";
  }
  if (item.state === "completed") {
    return item.detail || "Installed";
  }
  if (item.state === "queued") {
    return item.position === 1
      ? "Next in queue"
      : `${item.position} installs ahead`;
  }
  const downloaded = formatBytes(item.downloadedBytes);
  const total = formatBytes(item.totalBytes);
  const speed = formatBytes(item.bytesPerSecond);
  const eta = formatEta(item.etaSeconds);
  const parts = [];
  if (downloaded && total) parts.push(`${downloaded} of ${total}`);
  else if (downloaded) parts.push(downloaded);
  if (speed) parts.push(`${speed}/s`);
  if (eta) parts.push(eta);
  return parts.join(" · ") || "Preparing download";
}

/** @param {{issue: import("../types").ValidationIssue, label?: string | null, onFocus: (id: string) => void}} props */
function ProblemRow({ issue, label, onFocus }) {
  const clickable = Boolean(issue.nodeId);
  const tone =
    issue.severity === "error" ? "text-mg-error" : "text-mg-warning";
  const className = `ui-row ${tone}${clickable ? "" : ""}`;
  const body = (
    <>
      <AlertTriangle className="ui-icon" />
      <div className="min-w-0 flex-1">
        <strong className="ui-copy-title text-[11px]">{issue.code}</strong>
        {label ? <p className="ui-copy-muted">{label}</p> : null}
        <p className="ui-copy-body mt-0.5">{issue.message}</p>
        {issue.action ? (
          <p className="ui-copy-muted mt-1">{issue.action}</p>
        ) : null}
      </div>
    </>
  );
  if (clickable) {
    return (
      <button
        type="button"
        onClick={() => issue.nodeId && onFocus(issue.nodeId)}
        className={className}
      >
        {body}
      </button>
    );
  }
  return <div className={className}>{body}</div>;
}

/** @param {{issues: import("../types").ValidationIssue[]}} props */
export function BottomDrawer({ issues }) {
  const toast = useToast();
  const tab = useDesktopStore((store) => store.drawerTab);
  const set = useDesktopStore((store) => store.setValue);
  const logs = useRunStore((store) => store.logs);
  const run = useRunStore((store) => store.run);
  const queue = useRunStore((store) => store.queue);
  const history = useRunStore((store) => store.history);
  const cancelRun = useRunStore((store) => store.cancel);
  const downloads = useServerStore((store) => store.downloads);
  const cancelDownload = useServerStore((store) => store.cancelDownload);
  const diagnostics = useServerStore((store) => store.diagnostics);
  const nodes = useEditorStore((store) => store.nodes);
  const focusNode = useEditorStore((store) => store.focusNode);
  const labels = Object.fromEntries(
    nodes.map((node) => [
      node.id,
      node.data.label || node.data.definition?.name || node.data.schemaId,
    ]),
  );
  async function cancelInstall(/** @type {number} */ jobId) {
    try {
      await cancelDownload(jobId);
      toast.push("Cancellation requested. Partial installation is being rolled back.", "success");
    } catch (error) {
      toast.push(
        error instanceof Error ? error.message : String(error),
        "error",
      );
    }
  }
  const downloadCount =
    (downloads?.active?.length || 0) +
    (downloads?.pending?.length || 0) +
    (downloads?.recent || []).filter((item) => item.state === "failed").length;
  const tabs = [
    {
      id: "queue",
      label: "Queue",
      icon: <ListOrdered className="ui-icon-sm" />,
      count: (queue.running ? 1 : 0) + queue.pending.length || undefined,
    },
    {
      id: "logs",
      label: "Run log",
      icon: <ScrollText className="ui-icon-sm" />,
      count: logs.length || undefined,
    },
    {
      id: "downloads",
      label: "Downloads",
      icon: <Download className="ui-icon-sm" />,
      count: downloadCount || undefined,
    },
    {
      id: "problems",
      label: "Problems",
      icon: <AlertTriangle className="ui-icon-sm" />,
      count: issues.length || undefined,
    },
    {
      id: "diagnostics",
      label: "Diagnostics",
      icon: <Stethoscope className="ui-icon-sm" />,
    },
  ];

  return (
    <Panel
      className="h-full border-t border-mg-border"
      bodyClassName="flex min-h-0 flex-col"
    >
      <Tabs
        tabs={tabs}
        value={tab}
        onChange={(value) => set("drawerTab", value)}
      />
      <div className="min-h-0 flex-1 overflow-auto p-3 text-[11px]">
        {tab === "queue" && (
          <div className="ui-stack">
            {queue.running && (
              <div className="ui-stack-sm">
                <div className="ui-action-row">
                  <div className="min-w-0">
                    <p className="ui-copy-title text-[11px]">Running workflow</p>
                    <p className="ui-copy-muted truncate font-mono">
                      {queue.running.runId}
                    </p>
                  </div>
                  <Badge size="xs" tone="running">
                    {queue.running.progress || 0}%
                  </Badge>
                </div>
                <ProgressBar value={queue.running.progress || 0} />
              </div>
            )}
            {queue.pending.map((item) => (
              <div key={item.runId} className="ui-action-row">
                <div className="min-w-0">
                  <p className="ui-copy-title text-[11px]">
                    Queue position {item.queuePosition}
                  </p>
                  <p className="ui-copy-muted truncate font-mono">
                    {item.runId}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  className="min-h-7 px-2 text-[10px]"
                  onClick={() => void cancelRun(item.runId)}
                >
                  Cancel
                </Button>
              </div>
            ))}
            {!queue.running && !queue.pending.length && (
              <EmptyState
                icon={<ListOrdered className="ui-icon-lg" />}
                title="Execution queue is empty"
                description="Ctrl+Enter queues a workflow. Ctrl+Shift+Enter puts it next."
              />
            )}
            {history.length > 0 && (
              <div>
                <p className="ui-kicker-plain mb-1.5 ui-inline">
                  <History className="ui-icon-sm" /> Recent runs
                </p>
                <div className="ui-list">
                  {history.slice(0, 10).map((item) => (
                    <div key={item.runId} className="ui-action-row py-1.5">
                      <span className="ui-copy-body truncate font-mono text-[9px]">
                        {item.runId}
                      </span>
                      <Badge
                        size="xs"
                        tone={
                          item.status === "COMPLETED"
                            ? "success"
                            : item.status === "FAILED"
                              ? "error"
                              : "neutral"
                        }
                      >
                        {item.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        {tab === "logs" &&
          (logs.length ? (
            <div role="log" className="ui-stack-xs">
              {logs.map((line) => (
                <div key={line.id} className="ui-log-line">
                  <span className="text-mg-muted">
                    {new Date(
                      line.timestamp || Date.now(),
                    ).toLocaleTimeString("en-US")}
                  </span>
                  <span>{line.message}</span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<ScrollText className="ui-icon-lg" />}
              title="No run log"
              description="Execution messages appear here."
            />
          ))}
        {tab === "downloads" && (
          <div className="ui-stack-sm">
            {[
              ...(downloads?.active || []),
              ...(downloads?.pending || []),
              ...(downloads?.recent || []),
            ].map((item) => (
              <div
                key={item.jobId || `${item.kind}-${item.key}`}
                className="ui-list-item"
              >
                <div className="ui-action-row mb-2">
                  <div className="min-w-0">
                    <p className="ui-copy-title truncate text-[11px]">
                      {item.modelId || item.key}
                    </p>
                    <p className="ui-copy-muted">{downloadSubtitle(item)}</p>
                  </div>
                  <Badge
                    size="xs"
                    tone={
                      item.state === "failed"
                        ? "error"
                        : item.state === "cancelled"
                          ? "warning"
                          : item.state === "completed"
                            ? "success"
                            : item.state === "queued"
                              ? "accent"
                              : "running"
                    }
                  >
                    {item.state === "failed"
                      ? "Failed"
                      : item.state === "cancelled"
                        ? "Cancelled"
                        : item.state === "completed"
                          ? "Installed"
                          : item.state === "queued"
                            ? `Queued · ${item.position}`
                            : item.state === "stopping"
                              ? "Rolling back"
                              : "Installing"}
                  </Badge>
                  {["active", "queued"].includes(item.state) && (
                    <Button
                      variant="ghost"
                      className="min-h-7 px-2 text-[10px]"
                      onClick={() => void cancelInstall(item.jobId)}
                      aria-label={`Cancel installation of ${item.modelId || item.key}`}
                    >
                      <X className="ui-icon-sm" /> Cancel
                    </Button>
                  )}
                </div>
                {["active", "stopping", "queued"].includes(item.state) && (
                  <ProgressBar
                    value={item.state === "queued" ? 0 : item.progress}
                    indeterminate={
                      item.state !== "queued" && item.progress == null
                    }
                    label={
                      item.state === "queued"
                        ? `Queue position ${item.position}`
                        : ""
                    }
                    showLabel
                  />
                )}
              </div>
            ))}
            {!(
              downloads?.active?.length ||
              downloads?.pending?.length ||
              downloads?.recent?.length
            ) && (
              <EmptyState
                icon={<Download className="ui-icon-lg" />}
                title="Download queue is empty"
              />
            )}
          </div>
        )}
        {tab === "problems" &&
          (issues.length ? (
            <div className="ui-stack-sm">
              {issues.map((issue, index) => (
                <ProblemRow
                  key={`${issue.code}-${index}`}
                  issue={issue}
                  label={issue.nodeId ? labels[issue.nodeId] : null}
                  onFocus={focusNode}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<CheckCircle2 className="ui-icon-lg" />}
              title="No workflow problems"
            />
          ))}
        {tab === "diagnostics" && (
          <pre className="ui-copy-body whitespace-pre-wrap font-mono text-[9px] leading-4">
            {JSON.stringify(diagnostics, null, 2)}
          </pre>
        )}
      </div>
      {run && (
        <div className="ui-rule p-2.5">
          <ProgressBar
            value={run.progress || 0}
            label={`Run ${run.status}`}
            showLabel
          />
        </div>
      )}
    </Panel>
  );
}
