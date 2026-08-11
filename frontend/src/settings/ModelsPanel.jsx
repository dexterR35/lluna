import { useMemo, useState } from "react";
import {
  Box,
  Clock3,
  Download,
  ExternalLink,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from "../icons";
import { api } from "../api/client";
import {
  Badge,
  CompactButton,
  EmptyState,
  ProgressBar,
  Switch,
  Select,
  useToast,
} from "../components";
import { useServerStore } from "../state/serverStore";
import { SettingsForm } from "./SettingsForm";
import { AddModelDialog, HuggingFaceConnection } from "./AddModelDialog";
import { capabilityIssues } from "../models/modelManifestCapabilities";
import { formatTransferProgress, useCancelInstall } from "../models/downloadFormat";
import { CapabilityEditor } from "./CapabilityEditor";

/** @param {import("../types").DownloadJob} job */
function formatTransfer(job) {
  return (
    formatTransferProgress(job) || "Download progress will appear here."
  );
}

/**
 * @param {string} modelId
 * @returns {{section: string, keys: string[]} | null}
 */
function optionsForModel(modelId) {
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

/** @type {{id: string, label: string, match: (model: import("../types").ModelInventory) => boolean}[]} */
const MODEL_SECTIONS = [
  {
    id: "generation",
    label: "Image generation",
    match: (model) =>
      model.id.startsWith("generate:") || model.task === "text-to-image",
  },
  {
    id: "enhancement",
    label: "Enhancement",
    match: (model) =>
      model.id.startsWith("realesrgan") || model.task === "image-upscaling",
  },
  {
    id: "low_light",
    label: "Low light",
    match: (model) =>
      model.id === "mirnet" || model.task === "image-restoration",
  },
  {
    id: "object",
    label: "Object selection",
    match: (model) =>
      model.id === "sam2" ||
      model.id === "grounding-dino" ||
      model.task === "object-detection",
  },
  {
    id: "background_removal",
    label: "Background removal",
    match: (model) => model.id.startsWith("birefnet") || model.task === "image-segmentation",
  },
  {
    id: "subtitle",
    label: "Subtitle & text",
    match: (model) =>
      [
        "sttn-auto",
        "sttn-detection",
        "lama",
        "propainter",
        "paddleocr-server",
        "paddleocr-mobile",
      ].includes(model.id) ||
      model.task === "inpainting" ||
      model.task === "text-recognition",
  },
  {
    id: "custom",
    label: "Custom",
    match: (model) => Boolean(model.dynamic),
  },
  {
    id: "other",
    label: "Other",
    match: () => true,
  },
];

/**
 * SAM2 and Grounding DINO always install/uninstall together as one pair on
 * the backend (backend/tools/installers/select_object.py), so present them
 * as a single "Select Object" row instead of two rows that happen to
 * trigger the same server-side action.
 * @param {import("../types").ModelInventory[]} models
 */
function mergeSelectObjectModels(models) {
  const sam2 = models.find((model) => model.id === "sam2");
  const dino = models.find((model) => model.id === "grounding-dino");
  if (!sam2 || !dino) return models;
  const merged = {
    ...sam2,
    display_name: "Select Object (SAM2 + Grounding DINO)",
    purpose: "Point/box/text-prompted subject selection.",
    installed: sam2.installed && dino.installed,
    enabled: sam2.enabled && dino.enabled,
    can_install: !(sam2.installed && dino.installed) && (sam2.can_install || dino.can_install),
    can_uninstall: sam2.can_uninstall || dino.can_uninstall,
    can_toggle: sam2.can_toggle && dino.can_toggle,
  };
  return [merged, ...models.filter((model) => model.id !== "sam2" && model.id !== "grounding-dino")];
}

/** @param {import("../types").ModelInventory[]} models */
function groupModels(models) {
  models = mergeSelectObjectModels(models);
  /** @type {Map<string, import("../types").ModelInventory[]>} */
  const buckets = new Map(MODEL_SECTIONS.map((section) => [section.id, []]));
  for (const model of models) {
    const section = model.dynamic
      ? MODEL_SECTIONS.find((item) => item.id === "custom")
      : MODEL_SECTIONS.find(
          (item) => item.id !== "other" && item.id !== "custom" && item.match(model),
        ) || MODEL_SECTIONS.at(-1);
    buckets.get(section?.id || "other")?.push(model);
  }
  return MODEL_SECTIONS.map((section) => ({
    ...section,
    models: buckets.get(section.id) || [],
  })).filter((section) => section.models.length > 0);
}

/** @param {import("../types").ModelInventory} model @param {import("../types").DownloadJob | undefined} job @param {boolean} requesting */
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
    return { tone: /** @type {const} */ ("accent"), label: "Adding…" };
  }
  if (model.state === "needs_configuration") {
    return { tone: /** @type {const} */ ("warning"), label: "Needs setup" };
  }
  if (model.state === "incompatible") {
    return { tone: /** @type {const} */ ("error"), label: "Incompatible" };
  }
  if (model.installed) {
    return model.enabled
      ? { tone: /** @type {const} */ ("success"), label: "Enabled" }
      : { tone: /** @type {const} */ ("warning"), label: "Disabled" };
  }
  return { tone: /** @type {const} */ ("neutral"), label: "Not installed" };
}

/** @param {{model: import("../types").ModelInventory}} props */
function ModelCapabilitySummary({ model }) {
  const caps = /** @type {Record<string, any>} */ (model.capabilities || {});
  const variant = /** @type {Record<string, any>} */ (model.variant || {});
  const controls = [
    caps.negativePrompt === true && "negative prompt",
    caps.guidance === true && "guidance",
    caps.seed === true && "seed",
    caps.loraStrength && "LoRA strength",
    caps.controlStrength && "ControlNet",
    caps.denoiseStrength && "denoise strength",
    caps.tileSize && "tiling",
  ].filter(Boolean);
  const facts = [
    ["Variant", [variant.kind, variant.quantization].filter(Boolean).join(" · ")],
    ["Steps", caps.steps ? `${caps.steps.default} default · ${caps.steps.minimum}–${caps.steps.maximum}` : "Not used"],
    ["Sizes", (caps.supportedWidths || []).length ? (caps.supportedWidths || []).join(", ") : caps.widthMultiple ? `multiples of ${caps.widthMultiple}` : "Task-specific"],
    ["Dtypes", (caps.dtypes || []).join(", ") || "Runtime default"],
    ["Inputs", (caps.inputs || []).join(", ") || "Unresolved"],
    ["Outputs", (caps.outputs || []).join(", ") || "Unresolved"],
  ];
  return (
    <div className="ui-stack-sm ui-rule mt-2.5 pt-2.5">
      <div className="grid gap-2 md:grid-cols-3">
        {facts.map(([label, value]) => (
          <div key={label}>
            <p className="ui-kicker-plain">{label}</p>
            <p className="ui-copy-body mt-0.5">{value}</p>
          </div>
        ))}
      </div>
      <div className="ui-actions justify-start">
        {controls.length ? controls.map((control) => <Badge key={String(control)} tone="accent">{control}</Badge>) : <Badge tone="neutral">No optional controls</Badge>}
        <Badge tone={caps.complete ? "success" : "warning"}>{caps.provenance || "unknown"}</Badge>
      </div>
      {variant.baseModel && <p className="ui-help">Compatible base model: {variant.baseModel}</p>}
    </div>
  );
}

/** @param {{model: import("../types").ModelInventory, onSaved: () => void}} props */
function DynamicModelConfiguration({ model, onSaved }) {
  const toast = useToast();
  const [manifest, setManifest] = useState(/** @type {Record<string, any>} */ ({
    ...(model.manifest || {}),
    task: String(model.task || model.manifest?.task || "custom"),
    adapter: String(model.adapter || model.manifest?.adapter || "transformers"),
  }));
  const [saving, setSaving] = useState(false);
  const task = manifest.task;
  const adapter = manifest.adapter;
  const unresolved = capabilityIssues(manifest);
  const runtime = /** @type {Record<string, string>} */ ({
    diffusers: "diffusers-torch",
    transformers: "transformers-torch",
    paddle: "paddle",
  })[adapter];
  async function save() {
    setSaving(true);
    try {
      await api(`/api/models/${encodeURIComponent(model.id)}/manifest`, {
        method: "PUT",
        body: JSON.stringify({
          ...manifest,
          runtime: {
            ...(manifest.runtime || {}),
            profile: runtime,
          },
          needsConfiguration: false,
        }),
      });
      toast.push("Model configuration saved.", "success");
      onSaved();
    } catch (error) {
      toast.push(
        error instanceof Error ? error.message : String(error),
        "error",
      );
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="ui-stack-sm">
      <div className="grid gap-2 md:grid-cols-2">
        <Select
          label="Task"
          value={task}
          onChange={(event) => setManifest({ ...manifest, task: event.target.value, capabilities: { ...(manifest.capabilities || {}), tasks: [] } })}
          options={[
            "text-to-image", "image-to-image", "image-segmentation", "object-detection",
            "image-upscaling", "image-restoration", "inpainting", "text-recognition",
            "text-generation", "automatic-speech-recognition", "custom",
          ].map((value) => ({ value, label: value.replaceAll("-", " ") }))}
        />
        <Select
          label="Runtime"
          value={adapter}
          onChange={(event) => setManifest({ ...manifest, adapter: event.target.value })}
          options={[
            ["diffusers", "Diffusers + PyTorch"], ["transformers", "Transformers + PyTorch"],
            ["paddle", "Paddle"],
          ].map(([value, label]) => ({ value, label }))}
        />
      </div>
      <CapabilityEditor manifest={manifest} onChange={setManifest} />
      {unresolved.length > 0 && <p className="ui-help text-mg-warning">Still required: {unresolved.join(", ")}.</p>}
      <CompactButton variant="secondary" disabled={saving || unresolved.length > 0} onClick={() => void save()}>
        {saving ? "Saving…" : "Save reviewed manifest"}
      </CompactButton>
    </div>
  );
}

/** @param {{model: import("../types").ModelInventory, onChanged: () => void}} props */
function SupirSetup({ model, onChanged }) {
  const toast = useToast();
  const [importing, setImporting] = useState(/** @type {string | null} */ (null));
  const setup = model.setup || {};

  async function importFile(/** @type {"Q"|"F"|"sdxl"} */ kind) {
    const desktop = window.llunaDesktop;
    if (!desktop) return;
    setImporting(kind);
    try {
      const grant = await desktop.selectModelFile();
      if (!grant) return;
      await api("/api/models/supir/checkpoint", {
        method: "POST",
        body: JSON.stringify({ grantId: grant.grantId, kind }),
      });
      await onChanged();
      toast.push(`${kind === "sdxl" ? "SDXL base" : `SUPIR v0-${kind}`} imported.`, "success");
    } catch (error) {
      toast.push(error instanceof Error ? error.message : String(error), "error");
    } finally {
      setImporting(null);
    }
  }

  return (
    <div className="ui-stack-sm ui-rule mt-2.5 pt-2.5">
      <div>
        <p className="ui-copy-title">Official SUPIR setup</p>
        <p className="ui-help">
          Non-commercial use only. Lluna uses the pinned official runtime and verifies every
          downloaded checkpoint before installation.
        </p>
      </div>
      <div className="ui-actions justify-start">
        <CompactButton variant="secondary" onClick={() => void window.llunaDesktop?.openExternal("supir-downloads")}>
          <ExternalLink className="ui-icon-sm" /> Official weights
        </CompactButton>
        <CompactButton variant="secondary" onClick={() => void window.llunaDesktop?.openExternal("supir")}>
          <ExternalLink className="ui-icon-sm" /> Source & license
        </CompactButton>
        <CompactButton variant="secondary" onClick={() => void window.llunaDesktop?.openExternal("supir-mirror")}>
          <ExternalLink className="ui-icon-sm" /> HF weight mirror
        </CompactButton>
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {[
          ["Q", "SUPIR v0-Q", true, setup.v0Q],
          ["F", "SUPIR v0-F", false, setup.v0F],
          ["sdxl", "SDXL 1.0 base", true, setup.sdxl],
        ].map(([kind, label, required, ready]) => (
          <CompactButton
            key={String(kind)}
            variant="secondary"
            disabled={Boolean(importing)}
            onClick={() => void importFile(/** @type {"Q"|"F"|"sdxl"} */ (kind))}
          >
            <Upload className="ui-icon-sm" />
            {ready ? `${label} ready` : `${importing === kind ? "Importing…" : "Import"} ${label}`}
            {required && !ready ? " *" : ""}
          </CompactButton>
        ))}
      </div>
      <p className="ui-help">
        Install automatically downloads checksum-pinned SUPIR v0-Q from the XCogni community mirror,
        official Stability AI SDXL, the pinned source, isolated runtime, text encoders, and LLaVA.
        Manual import remains available above. Both v0-Q and v0-F are installed. Expect roughly 70 GB
        of downloads and at least 80 GB free disk space.
      </p>
    </div>
  );
}

/**
 * @param {{
 *   model: import("../types").ModelInventory,
 *   job?: import("../types").DownloadJob,
 *   recent?: import("../types").DownloadJob,
 *   requesting: boolean,
 *   settings: Record<string, any> | null | undefined,
 *   expanded: boolean,
 *   onToggleExpand: () => void,
 *   onAction: (model: import("../types").ModelInventory, operation: "install"|"enable"|"disable"|"remove") => void,
 *   onCancelInstall: (job: import("../types").DownloadJob) => void,
 *   onConfigured: () => void,
 * }} props
 */
function ModelRow({
  model,
  job,
  recent,
  requesting,
  settings,
  expanded,
  onToggleExpand,
  onAction,
  onCancelInstall,
  onConfigured,
}) {
  const installing = job?.state === "active" || job?.state === "stopping";
  const queued = job?.state === "queued";
  const status = modelStatus(model, job, requesting);
  const optionSpec = optionsForModel(model.id);
  const sectionValues =
    optionSpec && settings?.[optionSpec.section]
      ? /** @type {Record<string, any>} */ (settings[optionSpec.section])
      : null;
  const purpose =
    String(model.purpose || model.manifest?.description || "").trim() ||
    "Local inference";

  return (
    <article className="ui-list-item py-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="ui-actions gap-1.5">
            <h4 className="truncate text-[12px] font-semibold tracking-tight text-mg-primary">
              {model.display_name || model.id}
            </h4>
            <Badge size="xs" tone={status.tone}>
              {status.label}
            </Badge>
          </div>
          <p className="ui-copy-muted mt-0.5 leading-4">{purpose}</p>
        </div>
        <div className="ui-actions shrink-0 gap-1.5">
          <Switch
            label="Enabled"
            checked={Boolean(model.installed && model.enabled)}
            disabled={Boolean(job) || !model.installed || !model.can_toggle}
            onChange={(enabled) =>
              void onAction(model, enabled ? "enable" : "disable")
            }
          />
          {!model.installed && model.can_install && !job && (
            <CompactButton
              variant="primary"
              onClick={() => void onAction(model, "install")}
            >
              {requesting ? (
                "Adding…"
              ) : (
                <>
                  <Download className="ui-icon-sm" /> Install
                </>
              )}
            </CompactButton>
          )}
          {job && (
            <CompactButton variant="secondary" disabled>
              {queued && <Clock3 className="ui-icon-sm" />}
              {job.state === "stopping"
                ? "Rolling back…"
                : installing
                  ? "Installing…"
                  : `Queued · ${job.position}`}
            </CompactButton>
          )}
          {job && job.state !== "stopping" && (
            <CompactButton
              variant="secondary"
              onClick={() => void onCancelInstall(job)}
              aria-label={`Cancel installation of ${model.display_name || model.id}`}
            >
              <X className="ui-icon-sm" /> Cancel
            </CompactButton>
          )}
          {!model.installed && !model.can_install && (
            <Badge size="xs" tone="neutral">
              Bundled
            </Badge>
          )}
          {model.installed && model.can_uninstall && !job && (
            <CompactButton
              variant="secondary"
              onClick={() => void onAction(model, "remove")}
            >
              <Trash2 className="ui-icon-sm" /> Uninstall
            </CompactButton>
          )}
          {((optionSpec && sectionValues) || model.capabilities || model.needs_configuration) && (
            <CompactButton onClick={onToggleExpand}>
              {expanded ? "Hide" : "Options"}
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
      {expanded && optionSpec && sectionValues && (
        <div className="ui-stack-sm ui-rule mt-2.5 pt-2.5">
          <SettingsForm
            section={optionSpec.section}
            values={sectionValues}
            keys={optionSpec.keys}
          />
        </div>
      )}
      {expanded && model.capabilities && <ModelCapabilitySummary model={model} />}
      {expanded && model.id === "supir" && (
        <SupirSetup model={model} onChanged={onConfigured} />
      )}
      {expanded && model.needs_configuration && (
        <div className="ui-stack-sm ui-rule mt-2.5 pt-2.5">
          <DynamicModelConfiguration model={model} onSaved={onConfigured} />
        </div>
      )}
      {model.runtime &&
      (model.runtime.reasons?.length || model.runtime.warnings?.length) ? (
        <div className="mt-1.5">
          {[
            ...(model.runtime.reasons || []),
            ...(model.runtime.warnings || []),
          ].map((message) => (
            <p key={message} className="ui-help text-mg-warning">
              {message}
            </p>
          ))}
        </div>
      ) : null}
    </article>
  );
}

export function ModelsPanel() {
  const toast = useToast();
  const models = useServerStore((store) => store.models);
  const downloads = useServerStore((store) => store.downloads);
  const settings = useServerStore((store) => store.settings);
  const refreshDownloads = useServerStore((store) => store.refreshDownloads);
  const cancelDownloadJob = useCancelInstall();
  const setLifecycleState = useServerStore(
    (store) => store.setModelLifecycleState,
  );
  const [expanded, setExpanded] = useState(/** @type {string | null} */ (null));
  const [addOpen, setAddOpen] = useState(false);
  const [rescanning, setRescanning] = useState(false);
  const updateSettings = useServerStore((store) => store.updateSettings);
  const refreshModels = useServerStore((store) => store.refreshModels);
  const sections = useMemo(() => groupModels(models), [models]);

  /** @param {import("../types").DownloadJob} job */
  function cancelInstall(job) {
    return cancelDownloadJob(job.jobId);
  }

  async function rescan() {
    setRescanning(true);
    try {
      const result = await api("/api/models/rescan", { method: "POST" });
      useServerStore.setState({ models: result.models });
      toast.push(
        `Scanned · ${result.discovered} custom model${result.discovered === 1 ? "" : "s"}.`,
        "success",
      );
    } catch (error) {
      toast.push(
        error instanceof Error ? error.message : String(error),
        "error",
      );
    } finally {
      setRescanning(false);
    }
  }

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
      toast.push(
        error instanceof Error ? error.message : String(error),
        "error",
      );
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

  return (
    <div className="ui-stack">
      <HuggingFaceConnection />

      <div className="ui-actions gap-1.5">
        <CompactButton variant="secondary" onClick={() => void rescan()}>
          <RefreshCw
            className={`ui-icon-sm ${rescanning ? "animate-spin" : ""}`}
          />
          Rescan
        </CompactButton>
        <CompactButton variant="secondary" onClick={() => setAddOpen(true)}>
          <Plus className="ui-icon-sm" /> Add model
        </CompactButton>
      </div>

      {settings?.models && (
        <div className="grid gap-2 sm:grid-cols-2">
          <Switch
            label="Watch model folder"
            checked={Boolean(settings.models.auto_scan)}
            onChange={(value) =>
              void updateSettings({ models: { auto_scan: value } })
            }
          />
          <Switch
            label="Prefer SafeTensors"
            checked={Boolean(settings.models.prefer_safetensors)}
            onChange={(value) =>
              void updateSettings({ models: { prefer_safetensors: value } })
            }
          />
          <Switch
            label="Allow legacy pickle weights"
            checked={Boolean(settings.models.allow_pickle_weights)}
            onChange={(value) =>
              void updateSettings({ models: { allow_pickle_weights: value } })
            }
          />
          <Switch
            label="Allow trusted remote model code"
            checked={Boolean(settings.models.allow_remote_code)}
            onChange={(value) =>
              void updateSettings({ models: { allow_remote_code: value } })
            }
          />
        </div>
      )}

      <AddModelDialog open={addOpen} onClose={() => setAddOpen(false)} />

      {sections.length ? (
        <div className="ui-stack gap-5">
          {sections.map((section) => (
            <section key={section.id} className="ui-stack-sm">
              <p className="ui-kicker-plain">{section.label}</p>
              <div className="ui-list">
                {section.models.map((model) => {
                  const job = [
                    ...downloads.active,
                    ...downloads.pending,
                  ].find((item) => (item.modelId || item.key) === model.id);
                  const recent = (downloads.recent || []).find(
                    (item) =>
                      (item.modelId || item.key) === model.id &&
                      ["failed", "cancelled"].includes(item.state),
                  );
                  return (
                    <ModelRow
                      key={model.id}
                      model={model}
                      job={job}
                      recent={recent}
                      requesting={model.state === "requesting"}
                      settings={settings}
                      expanded={expanded === model.id}
                      onToggleExpand={() =>
                        setExpanded((value) =>
                          value === model.id ? null : model.id,
                        )
                      }
                      onAction={action}
                      onCancelInstall={cancelInstall}
                      onConfigured={() => {
                        void refreshModels();
                      }}
                    />
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<Box className="ui-icon-lg" />}
          title="No model catalog available"
        />
      )}
    </div>
  );
}
