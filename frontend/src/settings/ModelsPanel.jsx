import { useState } from "react";
import { Box, Clock3, Download, ListOrdered, Trash2 } from "lucide-react";
import { api } from "../api/client";
import {
  Badge,
  Button,
  CompactButton,
  EmptyState,
  ProgressBar,
  Switch,
  useToast,
} from "../components";
import { useServerStore } from "../state/serverStore";
import { SettingsForm } from "./SettingsForm";

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

/**
 * @param {string} modelId
 * @returns {{section: string, keys: string[]} | null}
 */
export function optionsForModel(modelId) {
  if (modelId.startsWith("bg-remove:")) {
    return { section: "background_removal", keys: ["mode"] };
  }
  if (modelId.startsWith("generate:")) {
    return { section: "generation", keys: ["mode", "width", "height", "steps"] };
  }
  if (modelId === "realesrgan-x2" || modelId === "realesrgan-x4") {
    return {
      section: "enhancement",
      keys: ["mode", "max_long_edge", "denoise_enabled", "denoise_strength"],
    };
  }
  if (modelId === "mirnet") {
    return { section: "low_light", keys: ["mode", "max_long_edge"] };
  }
  if (modelId === "sam2" || modelId === "grounding-dino") {
    return { section: "object_selection", keys: ["more_complex"] };
  }
  if (
    modelId === "sttn-auto" ||
    modelId === "sttn-detection" ||
    modelId === "lama" ||
    modelId === "propainter"
  ) {
    return {
      section: "subtitle",
      keys: [
        "inpaint_mode",
        "sttn_neighbor_stride",
        "sttn_reference_length",
        "sttn_max_load_num",
        "propainter_max_load_num",
        "mask_expansion_px",
        "hardware_acceleration",
      ],
    };
  }
  if (modelId === "paddleocr-server" || modelId === "paddleocr-mobile") {
    return {
      section: "subtitle",
      keys: [
        "subtitle_detect_mode",
        "selection_areas",
        "box_tolerance_x_px",
        "box_tolerance_y_px",
        "timeline_before_frames",
        "timeline_after_frames",
      ],
    };
  }
  return null;
}

/** @param {import("../types").ModelInventory} model */
function modelStatus(model, job, requesting) {
  if (job?.state === "active" || job?.state === "stopping") {
    return { tone: /** @type {const} */ ("running"), label: "Installing" };
  }
  if (job?.state === "queued") {
    return {
      tone: /** @type {const} */ ("accent"),
      label: `Queued · ${job.position}`,
    };
  }
  if (requesting) {
    return { tone: /** @type {const} */ ("accent"), label: "Adding to queue" };
  }
  if (model.installed) {
    return model.enabled
      ? { tone: /** @type {const} */ ("success"), label: "Enabled" }
      : { tone: /** @type {const} */ ("warning"), label: "Disabled" };
  }
  return { tone: /** @type {const} */ ("neutral"), label: "Not installed" };
}

export function ModelsPanel() {
  const toast = useToast();
  const models = useServerStore((store) => store.models);
  const downloads = useServerStore((store) => store.downloads);
  const settings = useServerStore((store) => store.settings);
  const refreshDownloads = useServerStore((store) => store.refreshDownloads);
  const setLifecycleState = useServerStore(
    (store) => store.setModelLifecycleState,
  );
  const [expanded, setExpanded] = useState(/** @type {string | null} */ (null));

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
    const modelPath = encodeURIComponent(model.id);
    try {
      const result = await api(
        `/api/models/${modelPath}${operation === "remove" ? "" : `/${operation}`}`,
        { method: operation === "remove" ? "DELETE" : "POST" },
      );
      if (operation === "install") {
        const jobId = Number(result?.jobId);
        for (const delay of [0, 150, 350, 750, 1500]) {
          if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
          const snapshot = await refreshDownloads();
          const job = [
            ...snapshot.active,
            ...snapshot.pending,
            ...(snapshot.recent || []),
          ].find((item) =>
            Number.isFinite(jobId)
              ? item.jobId === jobId
              : (item.modelId || item.key) === model.id,
          );
          if (job?.state === "failed" || job?.state === "cancelled") {
            toast.push(
              job.error ||
                (job.state === "cancelled"
                  ? "Model installation was cancelled."
                  : "Model installation failed."),
              "error",
            );
            break;
          }
          if (job || model.installed) break;
        }
      }
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
    <div className="ui-stack">
      {(activeJob || downloads.pending.length > 0) && (
        <div className="ui-stack-sm">
          <div className="ui-action-row">
            <div className="ui-inline min-w-0">
              <ListOrdered className="ui-icon-lg text-mg-running" />
              <div className="min-w-0">
                <p className="ui-copy-title truncate text-xs">
                  {activeJob
                    ? `Installing ${activeModel?.display_name || activeJob.modelId || activeJob.key}`
                    : "Model install queue"}
                </p>
                <p className="ui-copy-muted">
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

      <div className="ui-list">
        {models.length ? (
          models.map((model) => {
            const job = [...downloads.active, ...downloads.pending].find(
              (item) => (item.modelId || item.key) === model.id,
            );
            const recent = (downloads.recent || []).find(
              (item) =>
                (item.modelId || item.key) === model.id &&
                ["failed", "cancelled"].includes(item.state),
            );
            const installing =
              job?.state === "active" || job?.state === "stopping";
            const queued = job?.state === "queued";
            const requesting = model.state === "requesting";
            const status = modelStatus(model, job, requesting);
            const optionSpec = optionsForModel(model.id);
            const sectionValues =
              optionSpec && settings?.[optionSpec.section]
                ? /** @type {Record<string, any>} */ (
                    settings[optionSpec.section]
                  )
                : null;
            const isOpen = expanded === model.id;
            return (
              <article key={model.id} className="ui-list-item">
                <div className="ui-inline">
                  <div className="min-w-0 flex-1">
                    <div className="ui-actions">
                      <h3 className="ui-copy-title">
                        {model.display_name || model.id}
                      </h3>
                      <Badge tone={status.tone}>{status.label}</Badge>
                    </div>
                    <p className="ui-copy-body mt-0.5">
                      {model.purpose || "Local inference"} ·{" "}
                      {model.license || "See upstream license"}
                    </p>
                  </div>
                  <Switch
                    label="Enabled"
                    checked={Boolean(model.installed && model.enabled)}
                    disabled={
                      Boolean(job) || !model.installed || !model.can_toggle
                    }
                    onChange={(enabled) =>
                      void action(model, enabled ? "enable" : "disable")
                    }
                  />
                  <div className="ui-actions">
                    {!model.installed && model.can_install && !job && (
                      <Button
                        loading={requesting}
                        onClick={() => void action(model, "install")}
                      >
                        {!requesting && <Download className="ui-icon" />}
                        {requesting ? "Adding…" : "Install"}
                      </Button>
                    )}
                    {job && (
                      <Button variant="secondary" loading={installing} disabled>
                        {queued && <Clock3 className="ui-icon" />}
                        {installing
                          ? "Installing…"
                          : `Queued · ${job.position}`}
                      </Button>
                    )}
                    {!model.installed && !model.can_install && (
                      <Badge tone="neutral">Bundled</Badge>
                    )}
                    {model.installed && model.can_uninstall && !job && (
                      <Button
                        variant="danger"
                        onClick={() => void action(model, "remove")}
                      >
                        <Trash2 className="ui-icon" />
                        Uninstall
                      </Button>
                    )}
                    {optionSpec && sectionValues && (
                      <CompactButton
                        onClick={() =>
                          setExpanded((value) =>
                            value === model.id ? null : model.id,
                          )
                        }
                      >
                        {isOpen ? "Hide options" : "Options"}
                      </CompactButton>
                    )}
                  </div>
                </div>
                {job && (
                  <div className="mt-2">
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
                      <p className="ui-help mt-1">{formatTransfer(job)}</p>
                    )}
                  </div>
                )}
                {!job && !requesting && !model.installed && recent && (
                  <p role="alert" className="ui-help mt-2 text-mg-error">
                    {recent.error ||
                      (recent.state === "cancelled"
                        ? "Installation was cancelled. Try Install again."
                        : "Installation failed. Try again or open Downloads for details.")}
                  </p>
                )}
                {isOpen && optionSpec && sectionValues && (
                  <div className="ui-stack-sm ui-rule mt-3 pt-3">
                    <p className="ui-kicker-plain">Tuning options</p>
                    <SettingsForm
                      section={optionSpec.section}
                      values={sectionValues}
                      keys={optionSpec.keys}
                    />
                  </div>
                )}
              </article>
            );
          })
        ) : (
          <EmptyState
            icon={<Box className="ui-icon-lg" />}
            title="No model catalog available"
          />
        )}
      </div>
    </div>
  );
}
