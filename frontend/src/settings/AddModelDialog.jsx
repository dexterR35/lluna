import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  ExternalLink,
  FileBox,
  FolderOpen,
  Link2,
  LockKeyhole,
  ShieldCheck,
} from "../icons";
import { api } from "../api/client";
import {
  Badge,
  Button,
  Card,
  CompactButton,
  Dialog,
  Select,
  Tabs,
  TextField,
  useToast,
} from "../components";
import { useServerStore } from "../state/serverStore";
import { useManifestValidation } from "../models/modelManifestCapabilities";
import { CapabilityEditor } from "./CapabilityEditor";

const TASKS = [
  "text-to-image",
  "image-to-image",
  "image-segmentation",
  "object-detection",
  "image-upscaling",
  "image-restoration",
  "inpainting",
  "text-recognition",
  "text-generation",
  "image-to-text",
  "automatic-speech-recognition",
  "custom",
];
const ADAPTERS = [
  ["diffusers", "diffusers-torch", "Diffusers + PyTorch"],
  ["transformers", "transformers-torch", "Transformers + PyTorch"],
];

/** @param {number | null | undefined} bytes */
function size(bytes) {
  if (!Number.isFinite(bytes) || !bytes) return "Size unavailable";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes,
    index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
}

/** @param {{open: boolean, onClose: () => void}} props */
export function AddModelDialog({ open, onClose }) {
  const toast = useToast();
  const refreshModels = useServerStore((state) => state.refreshModels);
  const refreshDownloads = useServerStore((state) => state.refreshDownloads);
  const [sourceType, setSourceType] = useState("huggingface");
  const [value, setValue] = useState("");
  const [grant, setGrant] = useState(/** @type {import("../types").DesktopGrant | null} */ (null));
  const [analysis, setAnalysis] = useState(/** @type {Record<string, any> | null} */ (null));
  const [manifest, setManifest] = useState(/** @type {Record<string, any> | null} */ (null));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const manifestValidation = useManifestValidation(manifest);

  useEffect(() => {
    if (!open) {
      setAnalysis(null);
      setManifest(null);
      setGrant(null);
      setValue("");
      setError("");
      setBusy(false);
    }
  }, [open]);

  const adapter = useMemo(
    () => ADAPTERS.find(([id]) => id === manifest?.adapter),
    [manifest?.adapter],
  );

  async function chooseLocal() {
    const desktop = window.llunaDesktop;
    if (!desktop) {
      setError("Local model selection is available in the Lluna desktop app.");
      return null;
    }
    const selected =
      sourceType === "local-folder"
        ? await desktop.selectModelFolder()
        : await desktop.selectModelFile();
    if (selected) setGrant(selected);
    return selected;
  }

  async function analyze() {
    setBusy(true);
    setError("");
    try {
      let selected = grant;
      if (sourceType !== "huggingface" && !selected) selected = await chooseLocal();
      if (sourceType !== "huggingface" && !selected) return;
      const result = await api("/api/models/analyze", {
        method: "POST",
        body: JSON.stringify({
          sourceType,
          value,
          grantId: selected?.grantId || "",
        }),
      });
      setAnalysis(result);
      setManifest(result.manifest);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function changeAdapter(/** @type {string} */ next) {
    const selected = ADAPTERS.find(([id]) => id === next) || ADAPTERS.at(-1);
    if (!selected) return;
    const suffix = ".safetensors";
    const hasSafeWeights = (manifest?.expectedFiles || []).some((/** @type {string} */ name) => name.endsWith(suffix));
    const blockingReasons = sourceType !== "huggingface" ? [] :
      ["diffusers", "transformers"].includes(next) && !hasSafeWeights
        ? [`This repository does not expose ${suffix} weights that Lluna can load safely.`]
        : [];
    setAnalysis((current) => current ? { ...current, blockingReasons, installable: !blockingReasons.length } : current);
    setManifest((current) => ({
      ...current,
      adapter: selected[0],
      runtime: {
        ...(current?.runtime || {}),
        profile: selected[1],
      },
      security: {
        trustRemoteCode: false,
        preferSafetensors: true,
        allowPickle: false,
      },
      needsConfiguration: true,
    }));
  }

  async function install() {
    if (!manifest) return;
    setBusy(true);
    setError("");
    try {
      await api("/api/models/import", {
        method: "POST",
        body: JSON.stringify({
          sourceType,
          manifest: { ...manifest, needsConfiguration: false },
          grantId: grant?.grantId || "",
        }),
      });
      await Promise.all([refreshModels(), refreshDownloads()]);
      toast.push(
        sourceType === "huggingface"
          ? "Model added to the installation queue."
          : "Local model imported.",
        "success",
      );
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  const review = Boolean(analysis && manifest);
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={review ? "Review model" : "Add model"}
      description={
        review
          ? "Confirm compatibility, security, and storage before installing."
          : "Install from Hugging Face or import weights already on this device."
      }
      wide
      footer={
        review ? (
          <>
            <Button variant="ghost" onClick={() => { setAnalysis(null); setManifest(null); }}>
              Back
            </Button>
            <Button
              loading={busy}
              disabled={Boolean(
                analysis?.blockingReasons?.length ||
                manifestValidation.validating ||
                manifestValidation.issues.length
              )}
              onClick={() => void install()}
            >
              {sourceType === "huggingface" ? "Install model" : "Import model"}
            </Button>
          </>
        ) : (
          <Button loading={busy} onClick={() => void analyze()} disabled={sourceType === "huggingface" && !value.trim()}>
            Analyze model
          </Button>
        )
      }
    >
      {!analysis || !manifest ? (
        <div className="ui-stack">
          <Tabs
            value={sourceType}
            onChange={(next) => { setSourceType(next); setGrant(null); setError(""); }}
            tabs={[
              { id: "huggingface", label: "Hugging Face", icon: <Link2 className="ui-icon-sm" /> },
              { id: "local-folder", label: "Local folder", icon: <FolderOpen className="ui-icon-sm" /> },
              { id: "local-file", label: "Model file", icon: <FileBox className="ui-icon-sm" /> },
            ]}
          />
          {sourceType === "huggingface" ? (
            <TextField
              label="Repository link"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder="https://huggingface.co/owner/model"
              hint="Lluna reads metadata first and pins installation to the analyzed commit."
              autoFocus
            />
          ) : (
            <Card className="ui-action-row">
              <div>
                <p className="ui-copy-title">{grant?.name || (sourceType === "local-folder" ? "Choose a model folder" : "Choose a model file")}</p>
                <p className="ui-copy-muted">The source is copied into Lluna's managed custom model directory.</p>
              </div>
              <Button variant="secondary" onClick={() => void chooseLocal()}>
                <FolderOpen className="ui-icon" /> Choose
              </Button>
            </Card>
          )}
          <Card className="flex gap-3">
            <ShieldCheck className="ui-icon-lg shrink-0 text-mg-success" />
            <div>
              <p className="ui-copy-title">SafeTensors required</p>
              <p className="ui-copy-body mt-1">
                Custom models cannot contain pickle weights or remote Python code.
                Reviewed built-in runtimes handle explicitly verified legacy checkpoints.
              </p>
            </div>
          </Card>
          {error && <p role="alert" className="ui-help text-mg-error">{error}</p>}
        </div>
      ) : (
        <div className="ui-stack">
          <div className="grid gap-3 md:grid-cols-2">
            <TextField label="Display name" value={manifest.name || ""} onChange={(event) => setManifest({ ...manifest, name: event.target.value })} />
            <TextField label="Model id" value={manifest.id || ""} readOnly hint="Stable id used by workflows and settings." />
            <Select label="Task" value={manifest.task} options={TASKS.map((task) => ({ value: task, label: task.replaceAll("-", " ") }))} onChange={(event) => setManifest({ ...manifest, task: event.target.value, capabilities: { ...(manifest.capabilities || {}), tasks: [] }, needsConfiguration: true })} />
            <Select label="Runtime adapter" value={manifest.adapter} options={ADAPTERS.map(([id, , label]) => ({ value: id, label }))} onChange={(event) => changeAdapter(event.target.value)} />
          </div>
          <CapabilityEditor manifest={manifest} onChange={setManifest} />
          {manifestValidation.issues.length > 0 && (
            <p role="alert" className="ui-help text-mg-warning">Needs configuration: {manifestValidation.issues.join(", ")}.</p>
          )}
          <div className="grid gap-3 md:grid-cols-3">
            <Card><p className="ui-kicker-plain">Download</p><p className="ui-copy-title mt-1">{size(analysis.downloadBytes)}</p></Card>
            <Card><p className="ui-kicker-plain">License</p><p className="ui-copy-title mt-1">{manifest.license || "See model card"}</p></Card>
            <Card><p className="ui-kicker-plain">Runtime</p><p className="ui-copy-title mt-1">{adapter?.[2] || manifest.runtime?.profile}</p></Card>
          </div>
          <Card>
            <div className="ui-actions justify-between">
              <p className="ui-copy-title">Compatibility</p>
              <Badge tone={analysis.runtime.compatible ? "success" : "warning"}>
                {analysis.runtime.compatible ? "Compatible" : "Review required"}
              </Badge>
            </div>
            {[...(analysis.runtime.reasons || []), ...(analysis.runtime.warnings || [])].map((/** @type {string} */ message) => (
              <p key={message} className="ui-copy-body mt-1">• {message}</p>
            ))}
            {!analysis.runtime.reasons?.length && !analysis.runtime.warnings?.length && (
              <p className="ui-copy-body mt-1"><CheckCircle2 className="mr-1 inline size-3.5 text-mg-success" />Runtime and hardware checks passed.</p>
            )}
          </Card>
          {manifest.gated && (
            <Card className="ui-action-row border-mg-warning/50">
              <div><p className="ui-copy-title"><LockKeyhole className="mr-1 inline ui-icon" />Gated repository</p><p className="ui-copy-muted">Accept the model license on Hugging Face before installing.</p></div>
              <Button variant="secondary" onClick={() => void window.llunaDesktop?.openHuggingFace(analysis.repoUrl)}>
                Open model card <ExternalLink className="ui-icon-sm" />
              </Button>
            </Card>
          )}
          {(analysis.securityWarnings || []).map((/** @type {string} */ message) => <p key={message} className="ui-help">{message}</p>)}
          {(analysis.blockingReasons || []).map((/** @type {string} */ message) => <p key={message} role="alert" className="ui-help text-mg-error">{message}</p>)}
          {error && <p role="alert" className="ui-help text-mg-error">{error}</p>}
        </div>
      )}
    </Dialog>
  );
}

export function HuggingFaceConnection() {
  const toast = useToast();
  const [status, setStatus] = useState({
    connected: false,
    account: "",
    storage: "none",
  });
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    void api("/api/huggingface/status")
      .then(async (value) => {
        if (!alive) return;
        setStatus(value);
        if (value.connected) {
          try {
            const verified = await api("/api/huggingface/status?verify=true");
            if (alive) setStatus(verified);
          } catch {
            // Keep the saved connection visible while offline.
          }
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  async function connect() {
    setBusy(true);
    try {
      const value = await api("/api/huggingface/connect", {
        method: "POST",
        body: JSON.stringify({ token }),
      });
      setStatus(value);
      setToken("");
      toast.push(`Connected as ${value.account}.`, "success");
    } catch (error) {
      toast.push(
        error instanceof Error ? error.message : String(error),
        "error",
      );
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    try {
      setStatus(await api("/api/huggingface/connect", { method: "DELETE" }));
      toast.push("Hugging Face disconnected.", "success");
    } catch (error) {
      toast.push(
        error instanceof Error ? error.message : String(error),
        "error",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ui-action-row gap-2">
      <div className="min-w-0">
        <p className="text-[12px] font-semibold tracking-tight text-mg-primary">
          Hugging Face
        </p>
        <p className="ui-copy-muted mt-0.5 truncate">
          {status.connected
            ? `Connected${status.account ? ` as ${status.account}` : ""}`
            : "Token for gated and private models"}
        </p>
      </div>
      <div className="ui-actions shrink-0 gap-1.5">
        {!status.connected && (
          <TextField
            bare
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="hf_…"
            className="min-w-40 max-w-52"
            aria-label="Hugging Face token"
          />
        )}
        {status.connected && (
          <Badge size="xs" tone="success">
            Connected
          </Badge>
        )}
        <CompactButton
          variant={status.connected ? "danger" : "secondary"}
          disabled={busy || (!status.connected && token.length < 8)}
          onClick={() => void (status.connected ? disconnect() : connect())}
        >
          {busy ? "…" : status.connected ? "Disconnect" : "Connect"}
        </CompactButton>
      </div>
    </div>
  );
}
