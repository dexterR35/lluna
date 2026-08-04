import { Box, Clock3, Download, ListOrdered, Trash2 } from "lucide-react";
import { api } from "../api/client";
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  ProgressBar,
  Switch,
  useToast,
} from "../components";
import { useDesktopStore } from "../state/desktopStore";
import { useServerStore } from "../state/serverStore";

export function ModelsDialog() {
  const toast = useToast();
  const open = useDesktopStore((store) => store.modelsOpen);
  const set = useDesktopStore((store) => store.setValue);
  const models = useServerStore((store) => store.models);
  const downloads = useServerStore((store) => store.downloads);
  const refreshDownloads = useServerStore((store) => store.refreshDownloads);
  const setLifecycleState = useServerStore(
    (store) => store.setModelLifecycleState,
  );

  async function confirmState(
    /** @type {string} */ modelId,
    /** @type {(model: import("../types").ModelInventory) => boolean} */ matches,
  ) {
    for (const delay of [150, 350, 750, 1500, 3000]) {
      await new Promise((resolve) => setTimeout(resolve, delay));
      /** @type {import("../types").ModelInventory[]} */
      let inventory;
      try {
        inventory = await api("/api/models");
      } catch {
        return;
      }
      const model = inventory.find((item) => item.id === modelId);
      if (model && matches(model)) {
        useServerStore.setState({ models: inventory });
        return;
      }
    }
  }

  async function action(
    /** @type {import("../types").ModelInventory} */ model,
    /** @type {"install"|"enable"|"disable"|"remove"} */ operation,
  ) {
    if (operation === "install") {
      setLifecycleState(model.id, { state: "requesting" });
    }
    try {
      await api(
        `/api/models/${model.id}${operation === "remove" ? "" : `/${operation}`}`,
        { method: operation === "remove" ? "DELETE" : "POST" },
      );
    } catch (error) {
      if (operation === "install") {
        setLifecycleState(model.id, { state: "not_installed" });
      }
      toast.push(error instanceof Error ? error.message : String(error), "error");
      return;
    }
    if (operation === "install") {
      try {
        await refreshDownloads();
      } catch (error) {
        toast.push(
          error instanceof Error ? error.message : String(error),
          "error",
        );
      } finally {
        setLifecycleState(model.id, { state: "not_installed" });
      }
      return;
    }
    if (operation === "enable") {
      setLifecycleState(model.id, { enabled: true });
      void confirmState(model.id, (item) => item.installed && item.enabled);
    } else if (operation === "disable") {
      setLifecycleState(model.id, { enabled: false });
      void confirmState(model.id, (item) => !item.enabled);
    } else if (operation === "remove") {
      setLifecycleState(model.id, {
        installed: false,
        enabled: false,
        state: "not_installed",
      });
      void confirmState(model.id, (item) => !item.installed);
    }
  }
  const activeJob = downloads.active[0];
  const activeModel = activeJob
    ? models.find((model) => model.id === (activeJob.modelId || activeJob.key))
    : null;
  return (
    <Dialog
      open={open}
      onClose={() => set("modelsOpen", false)}
      title="Local model manager"
      description="Models remain on this device. Review each license before use."
      wide
      className="!max-w-4xl"
    >
      {(activeJob || downloads.pending.length > 0) && (
        <div className="mb-3 rounded-2xl border border-mg-running/25 bg-mg-running/5 p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2">
              <ListOrdered className="size-4 shrink-0 text-mg-running" />
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-mg-primary">
                  {activeJob
                    ? `Installing ${activeModel?.display_name || activeJob.modelId || activeJob.key}`
                    : "Model install queue"}
                </p>
                <p className="text-[10px] text-mg-muted">
                  One model installs at a time, in the order added.
                </p>
              </div>
            </div>
            <Badge tone="running">
              {downloads.pending.length
                ? `${downloads.pending.length} waiting`
                : "Active"}
            </Badge>
          </div>
          {activeJob && (
            <ProgressBar
              value={activeJob.progress}
              indeterminate={activeJob.progress == null}
              label={activeJob.detail || "Preparing download"}
              showLabel
            />
          )}
        </div>
      )}
      <div className="divide-y divide-mg-border">
        {models.length ? (
          models.map((model) => {
            const job = [...downloads.active, ...downloads.pending].find(
              (item) => (item.modelId || item.key) === model.id,
            );
            const installing =
              job?.state === "active" || job?.state === "stopping";
            const queued = job?.state === "queued";
            const requesting = model.state === "requesting";
            return (
              <article
                key={model.id}
                className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3 first:pt-0 last:pb-0"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-[13px] font-semibold tracking-tight">
                      {model.display_name || model.id}
                    </h3>
                    <Badge
                      tone={
                        installing
                          ? "running"
                          : queued || requesting
                            ? "accent"
                            : model.installed
                              ? model.enabled
                                ? "success"
                                : "warning"
                              : "neutral"
                      }
                    >
                      {installing
                        ? "Installing"
                        : queued
                          ? `Queued · ${job.position}`
                          : requesting
                            ? "Adding to queue"
                            : model.installed
                              ? model.enabled
                                ? "Enabled"
                                : "Disabled"
                              : "Not installed"}
                    </Badge>
                  </div>
                  <p className="mt-0.5 text-[11px] text-mg-secondary">
                    {model.purpose || "Local inference"} ·{" "}
                    {model.license || "See upstream license"}
                  </p>
                </div>
                <Switch
                  label="Show in node model selectors"
                  checked={Boolean(model.installed && model.enabled)}
                  disabled={
                    Boolean(job) || !model.installed || !model.can_toggle
                  }
                  onChange={(enabled) =>
                    void action(model, enabled ? "enable" : "disable")
                  }
                />
                <div className="flex flex-wrap gap-2">
                  {!model.installed && model.can_install && !job && (
                    <Button
                      loading={requesting}
                      onClick={() => void action(model, "install")}
                    >
                      {!requesting && <Download className="size-4" />}
                      {requesting ? "Adding…" : "Install"}
                    </Button>
                  )}
                  {job && (
                    <Button variant="secondary" loading={installing} disabled>
                      {queued && <Clock3 className="size-4" />}
                      {installing ? "Installing…" : `Queued · ${job.position}`}
                    </Button>
                  )}
                  {!model.installed && !model.can_install && (
                    <Badge tone="neutral">
                      Provided by application installation
                    </Badge>
                  )}
                  {model.installed && model.can_uninstall && !job && (
                    <Button
                      variant="danger"
                      onClick={() => void action(model, "remove")}
                    >
                      <Trash2 className="size-4" />
                      Uninstall
                    </Button>
                  )}
                </div>
                {job && (
                  <div className="order-last mt-1 w-full rounded-xl border border-mg-border bg-mg-app/40 px-3 py-2">
                    <ProgressBar
                      value={queued ? 0 : job.progress}
                      indeterminate={installing && job.progress == null}
                      label={
                        installing
                          ? job.detail || "Preparing download"
                          : job.position === 1
                            ? "Next to install"
                            : `${job.position} installs ahead`
                      }
                      showLabel
                    />
                    {installing && (
                      <p className="mt-1 text-[9px] text-mg-muted">
                        {formatTransfer(job)}
                      </p>
                    )}
                  </div>
                )}
              </article>
            );
          })
        ) : (
          <EmptyState
            icon={<Box className="size-5" />}
            title="No model catalog available"
          />
        )}
      </div>
    </Dialog>
  );
}

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
  const minutes = Math.ceil(rounded / 60);
  return `${minutes}m remaining`;
}

/** @param {import("../types").DownloadJob} job */
function formatTransfer(job) {
  const downloaded = formatBytes(job.downloadedBytes);
  const total = formatBytes(job.totalBytes);
  const speed = formatBytes(job.bytesPerSecond);
  const eta = formatEta(job.etaSeconds);
  const parts = [];
  if (downloaded && total) parts.push(`${downloaded} of ${total}`);
  else if (downloaded) parts.push(downloaded);
  if (speed) parts.push(`${speed}/s`);
  if (eta) parts.push(eta);
  return parts.join(" · ") || "Download progress will appear here.";
}
