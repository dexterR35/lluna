import { useEffect, useState } from "react";
import { Card, Select, TextField } from "../components";

const VARIANTS = ["base", "distilled", "quantized", "lora", "controlnet", "inpainting", "upscaler", "finetune", "unknown"];
const BOOL_OPTIONS = [
  { value: "", label: "Unknown" },
  { value: "true", label: "Supported" },
  { value: "false", label: "Not supported" },
];

/** @param {unknown} value */
function csv(value) {
  return Array.isArray(value) ? value.join(", ") : "";
}

/** @param {string} value @param {boolean} [numbers] */
function parseCsv(value, numbers = false) {
  const values = value.split(",").map((item) => item.trim()).filter(Boolean);
  return numbers ? values.map(Number).filter((item) => Number.isInteger(item) && item > 0) : values;
}

/** @param {{manifest: Record<string, any>, onChange: (manifest: Record<string, any>) => void}} props */
export function CapabilityEditor({ manifest, onChange }) {
  const caps = manifest.capabilities || {};
  const variant = manifest.variant || { kind: "unknown" };
  const generation = ["text-to-image", "image-to-image", "inpainting"].includes(manifest.task);

  function setCaps(/** @type {Record<string, any>} */ patch) {
    onChange({
      ...manifest,
      capabilities: {
        ...caps,
        ...patch,
        provenance: "reviewed-manifest",
        tasks: [manifest.task],
      },
      needsConfiguration: true,
    });
  }
  function setVariant(/** @type {Record<string, any>} */ patch) {
    onChange({ ...manifest, variant: { ...variant, ...patch }, needsConfiguration: true });
  }
  function setBool(/** @type {string} */ key, /** @type {string} */ value) {
    setCaps({ [key]: value === "" ? null : value === "true" });
  }
  function setNumberContract(/** @type {string} */ key, /** @type {string} */ field, /** @type {string} */ value) {
    const next = { ...(caps[key] || {}), [field]: value };
    delete next.values;
    setCaps({ [key]: next });
  }

  return (
    <Card className="ui-stack-sm">
      <div>
        <p className="ui-copy-title">Model capability contract</p>
        <p className="ui-copy-muted mt-1">Only confirmed controls are exposed at runtime. Unknown values keep the model disabled.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <Select label="Variant" value={variant.kind || "unknown"} options={VARIANTS.map((value) => ({ value, label: value }))} onChange={(event) => setVariant({ kind: event.target.value })} />
        <TextField label="Base model" value={variant.baseModel || ""} placeholder="owner/base-model (when applicable)" onChange={(event) => setVariant({ baseModel: event.target.value })} />
        {variant.kind === "quantized" && <TextField label="Quantization" value={variant.quantization || ""} placeholder="fp8, int8, int4…" onChange={(event) => setVariant({ quantization: event.target.value })} />}
        <TextField label="Architecture" value={variant.architecture || ""} onChange={(event) => setVariant({ architecture: event.target.value })} />
        <CsvField label="Inputs" value={caps.inputs} placeholder="prompt, image, mask…" onChange={(value) => setCaps({ inputs: value })} />
        <CsvField label="Outputs" value={caps.outputs} placeholder="image, text, boxes…" onChange={(value) => setCaps({ outputs: value })} />
        <CsvField label="Dtypes" value={caps.dtypes} placeholder="bf16, fp16, fp8…" onChange={(value) => setCaps({ dtypes: value })} />
      </div>
      {generation && (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            {["negativePrompt", "guidance", "seed"].map((key) => (
              <Select key={key} label={key.replace(/([A-Z])/g, " $1")} value={typeof caps[key] === "boolean" ? String(caps[key]) : ""} options={BOOL_OPTIONS} onChange={(event) => setBool(key, event.target.value)} />
            ))}
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {["minimum", "default", "maximum"].map((field) => (
              <TextField key={field} type="number" label={`Steps ${field}`} value={caps.steps?.[field] ?? ""} onChange={(event) => setNumberContract("steps", field, event.target.value)} />
            ))}
            <CsvField label="Supported widths" value={caps.supportedWidths} numbers placeholder="512, 768, 1024" onChange={(value) => setCaps({ supportedWidths: value })} />
            <CsvField label="Supported heights" value={caps.supportedHeights} numbers placeholder="512, 768, 1024" onChange={(value) => setCaps({ supportedHeights: value })} />
            {caps.guidance === true && ["minimum", "default", "maximum"].map((field) => (
              <TextField key={`guidance-${field}`} type="number" label={`Guidance ${field}`} value={caps.guidanceScale?.[field] ?? ""} onChange={(event) => setNumberContract("guidanceScale", field, event.target.value)} />
            ))}
          </div>
        </>
      )}
      {variant.kind === "lora" && <RangeEditor label="LoRA strength" value={caps.loraStrength} onChange={(value) => setCaps({ loraStrength: value })} />}
      {variant.kind === "controlnet" && <div className="ui-stack-sm"><RangeEditor label="Control strength" value={caps.controlStrength} onChange={(value) => setCaps({ controlStrength: value })} /><RangeEditor label="Control start" value={caps.controlStart} onChange={(value) => setCaps({ controlStart: value })} /><RangeEditor label="Control end" value={caps.controlEnd} onChange={(value) => setCaps({ controlEnd: value })} /></div>}
      {(manifest.task === "inpainting" || variant.kind === "inpainting") && <RangeEditor label="Denoise strength" value={caps.denoiseStrength} onChange={(value) => setCaps({ denoiseStrength: value })} />}
      {(manifest.task === "image-upscaling" || variant.kind === "upscaler") && <div className="grid gap-3 md:grid-cols-3"><CsvField label="Scales" value={caps.scales} numbers placeholder="2, 4" onChange={(value) => setCaps({ scales: value })} /><RangeEditor label="Tile size" value={caps.tileSize} onChange={(value) => setCaps({ tileSize: value })} /><RangeEditor label="Tile overlap" value={caps.tileOverlap} onChange={(value) => setCaps({ tileOverlap: value })} /></div>}
    </Card>
  );
}

/** @param {{label: string, value?: unknown[], placeholder?: string, numbers?: boolean, onChange: (value: any[]) => void}} props */
function CsvField({ label, value, placeholder, numbers = false, onChange }) {
  const external = csv(value);
  const [draft, setDraft] = useState(external);
  useEffect(() => setDraft(external), [external]);
  return <TextField label={label} value={draft} placeholder={placeholder} onChange={(event) => setDraft(event.target.value)} onBlur={() => onChange(parseCsv(draft, numbers))} />;
}

/** @param {{label: string, value?: Record<string, any>, onChange: (value: Record<string, any>) => void}} props */
function RangeEditor({ label, value = {}, onChange }) {
  return (
    <div className="grid gap-2 md:grid-cols-3">
      {["minimum", "default", "maximum"].map((field) => (
        <TextField key={field} type="number" label={`${label} ${field}`} value={value?.[field] ?? ""} onChange={(event) => onChange({ ...value, [field]: event.target.value })} />
      ))}
    </div>
  );
}
