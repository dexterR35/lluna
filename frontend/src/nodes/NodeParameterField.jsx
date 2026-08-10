import { useState } from "react";
import {
  LoaderCircle,
  Plus,
  Upload,
  resolveCategoryColor,
  resolveNodeIcon,
} from "../icons";
import {
  Button,
  IconTile,
  NumberField,
  Select,
  Switch,
  TextArea,
  TextField,
} from "../components";
import { MAX_BATCH_IMAGES } from "../api/client";

/** @param {Pick<import("../types").NodeDefinition, "schemaId"> | undefined} nodeDefinition */
function mediaKind(nodeDefinition) {
  const schemaId = nodeDefinition?.schemaId || "";
  if (schemaId.includes("video")) return "video";
  if (schemaId.includes("mask")) return "mask";
  return "image";
}

/** @param {File} file @param {string} kind */
function acceptsFile(file, kind) {
  if (kind === "video")
    return (
      file.type.startsWith("video/") ||
      /\.(mp4|mov|mkv|webm|avi)$/i.test(file.name)
    );
  return (
    file.type.startsWith("image/") ||
    /\.(png|jpe?g|webp|gif|bmp|tiff?|avif)$/i.test(file.name)
  );
}

/** @typedef {{definition: import("../types").ParameterDefinition, nodeDefinition?: Pick<import("../types").NodeDefinition, "schemaId">, value?: unknown, selectedName?: string, onChange: (value: unknown, selection?: import("../types").DesktopGrant | import("../types").DesktopGrant[]) => void}} ParameterFieldProps */
/** @param {ParameterFieldProps} props */
function FileField({
  definition,
  nodeDefinition,
  value,
  selectedName,
  onChange,
}) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const kind = mediaKind(nodeDefinition);
  const multiple = definition.type === "files";
  const selectedCount = Array.isArray(value) ? value.length : value ? 1 : 0;

  /** @param {() => Promise<import("../types").DesktopGrant | import("../types").DesktopGrant[] | null | undefined>} action @param {string} [notice] */
  async function selectGrant(action, notice = "") {
    setError(notice);
    setLoading(true);
    try {
      const selection = await action();
      let grants = Array.isArray(selection)
        ? selection
        : selection
          ? [selection]
          : [];
      if (!grants.length) return;
      if (multiple && grants.length > MAX_BATCH_IMAGES) {
        grants = grants.slice(0, MAX_BATCH_IMAGES);
        setError(
          `Maximum ${MAX_BATCH_IMAGES} images. Extra files were ignored.`,
        );
      }
      if (multiple) onChange(grants.map((grant) => grant.grantId), grants);
      else onChange(grants[0].grantId, grants[0]);
    } catch (selectionError) {
      setError(
        selectionError instanceof Error
          ? selectionError.message
          : "Could not load this file.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function choose() {
    const desktop = window.llunaDesktop;
    if (!desktop) return;
    if (definition.type === "directory")
      return selectGrant(() => desktop.selectDirectory());
    if (definition.type === "saveFile")
      return selectGrant(() =>
        desktop.selectSaveFile(kind === "video" ? "video" : "image"),
      );
    if (kind === "video")
      return selectGrant(async () => (await desktop.selectVideoFiles()).at(0));
    if (kind === "mask") return selectGrant(() => desktop.selectMaskFile());
    return selectGrant(async () => {
      const grants = await desktop.selectImageFiles();
      return multiple ? grants : grants.at(0);
    });
  }

  /** @param {import("react").DragEvent<HTMLDivElement>} event */
  async function drop(event) {
    event.preventDefault();
    setDragging(false);
    const accepted = [...event.dataTransfer.files].filter((item) =>
      acceptsFile(item, kind),
    );
    if (!accepted.length) {
      setError(
        kind === "video"
          ? "Drop a supported video file."
          : "Drop a supported image file.",
      );
      return;
    }
    const truncated = multiple && accepted.length > MAX_BATCH_IMAGES;
    const files = accepted.slice(0, multiple ? MAX_BATCH_IMAGES : 1);
    const desktop = window.llunaDesktop;
    if (!desktop?.registerDroppedFiles) {
      setError("File drop is available in the desktop app.");
      return;
    }
    await selectGrant(
      async () => {
        const grants = await desktop.registerDroppedFiles(files);
        return multiple ? grants : grants.at(0);
      },
      truncated
        ? `Maximum ${MAX_BATCH_IMAGES} images. Extra files were ignored.`
        : "",
    );
  }

  if (["directory", "saveFile"].includes(definition.type))
    return (
      <div className="ui-field-label">
        <span>{definition.label}</span>
        <Button variant="secondary" onClick={choose} disabled={loading}>
          {loading && <LoaderCircle className="ui-icon-sm animate-spin" />}
          {value
            ? selectedName ||
              (definition.type === "directory"
                ? "Change destination folder"
                : "Change save location")
            : definition.type === "directory"
              ? "Choose destination folder"
              : "Choose save location"}
        </Button>
      </div>
    );

  const KindIcon = resolveNodeIcon(kind);
  const accent = resolveCategoryColor(
    kind === "video" ? "Video" : kind === "mask" ? "Mask" : "Image",
  );
  return (
    <div className="ui-field-label">
      <span>{definition.label}</span>
      <div
        role="button"
        tabIndex={0}
        aria-label={`Drop ${multiple ? `${kind} files` : `${kind} file`}`}
        className={`ui-dropzone ${dragging ? "is-active" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
          setDragging(true);
        }}
        onDragLeave={(event) => {
          if (
            !(event.relatedTarget instanceof Node) ||
            !event.currentTarget.contains(event.relatedTarget)
          )
            setDragging(false);
        }}
        onDrop={drop}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            void choose();
          }
        }}
      >
        <div className="ui-stack-xs justify-items-center">
          <IconTile
            className="bg-mg-elevated"
            style={{ color: accent }}
          >
            {loading ? (
              <LoaderCircle className="ui-icon-lg animate-spin" />
            ) : (
              <KindIcon className="ui-icon-lg" style={{ color: accent }} />
            )}
          </IconTile>
          <strong className="ui-copy-title text-[10px]">
            {dragging
              ? `Drop ${multiple ? `up to ${MAX_BATCH_IMAGES} ${kind} files` : kind} now`
              : multiple && selectedCount
                ? `${selectedCount} of ${MAX_BATCH_IMAGES} images selected`
                : selectedName || `Drop ${kind} here`}
          </strong>
          <span className="ui-copy-muted text-[9px]">
            {selectedCount
              ? multiple
                ? "Choose or drop files to replace this queue"
                : "Drop another file to replace it"
              : multiple
                ? `or choose up to ${MAX_BATCH_IMAGES} local files`
                : "or choose a local file"}
          </span>
          <Button
            variant="secondary"
            className="mt-1 min-h-7 px-2.5 text-[9px]"
            onClick={(event) => {
              event.stopPropagation();
              void choose();
            }}
            disabled={loading}
          >
            <Upload className="ui-icon-sm" />
            {selectedCount
              ? "Replace"
              : multiple
                ? "Choose files"
                : "Choose file"}
          </Button>
        </div>
      </div>
      {error && (
        <span role="alert" className="ui-help text-mg-error">
          {error}
        </span>
      )}
    </div>
  );
}

/**
 * Repeating "which LoRA, how strongly" rows.
 *
 * LoRAs stack, so this is a list rather than a dropdown: a style adapter and a
 * subject adapter are normally used together, each at its own weight. The
 * options come from the backend, which lists every installed LoRA rather than
 * only those matching the node's current model — the base model can be changed
 * after a LoRA is chosen, and the pairing is verified when the graph runs.
 *
 * @param {{
 *   definition: import("../types").ParameterDefinition,
 *   value: unknown,
 *   onChange: (next: unknown) => void,
 * }} props
 */
function LoraListField({ definition, value, onChange }) {
  const options = definition.options || [];
  const rows = Array.isArray(value) ? value : [];
  const used = new Set(rows.map((row) => String(row?.modelId ?? "")));
  const unused = options.filter((option) => !used.has(String(option.value)));

  /** @param {number} index @param {Record<string, unknown>} patch */
  const update = (index, patch) =>
    onChange(rows.map((row, at) => (at === index ? { ...row, ...patch } : row)));

  if (!options.length)
    return (
      <div className="ui-stack-xs">
        <span className="ui-copy-title text-[10px]">{definition.label}</span>
        <span className="ui-help">
          No LoRAs installed yet. Add one from Settings → Models → Add model.
        </span>
      </div>
    );

  return (
    <div className="ui-stack-xs">
      <span className="ui-copy-title text-[10px]">{definition.label}</span>
      {definition.description && (
        <span className="ui-help">{definition.description}</span>
      )}
      {rows.map((row, index) => {
        const modelId = String(row?.modelId ?? "");
        const weight = Number(row?.weight ?? 1);
        const choices = options.filter(
          (option) =>
            String(option.value) === modelId || !used.has(String(option.value)),
        );
        return (
          <div
            key={`${modelId}-${index}`}
            className="ui-stack-xs rounded border border-mg-border p-2"
          >
            {/* Explicit ids: these components derive an id from the label, and
                every row shares the same labels, which would otherwise emit
                duplicate DOM ids and wire each row's label to the first row. */}
            <Select
              id={`${definition.id}-model-${index}`}
              label="LoRA"
              value={modelId}
              options={choices}
              onChange={(event) => update(index, { modelId: event.target.value })}
            />
            <NumberField
              id={`${definition.id}-weight-${index}`}
              label="Weight"
              value={String(weight)}
              min={-2}
              max={2}
              step={0.05}
              hint="1.0 applies the LoRA as trained. Lower blends it in; negative inverts it."
              onChange={(event) =>
                update(index, { weight: Number(event.target.value) })
              }
            />
            <Button
              variant="secondary"
              className="min-h-7 px-2.5 text-[9px]"
              onClick={() => onChange(rows.filter((_row, at) => at !== index))}
            >
              Remove
            </Button>
          </div>
        );
      })}
      {unused.length > 0 && (
        <Button
          variant="secondary"
          className="min-h-7 px-2.5 text-[9px]"
          onClick={() =>
            onChange([...rows, { modelId: String(unused[0].value), weight: 1 }])
          }
        >
          <Plus className="ui-icon-sm" />
          Add LoRA
        </Button>
      )}
    </div>
  );
}

/** @param {ParameterFieldProps} props */
export function NodeParameterField({
  definition,
  nodeDefinition,
  value,
  selectedName,
  onChange,
}) {
  if (definition.type === "lora-list")
    return (
      <LoraListField
        definition={definition}
        value={value}
        onChange={onChange}
      />
    );
  const common = {
    label: definition.label,
    hint: definition.description,
    value: String(value ?? ""),
    onChange: (
      /** @type {import("react").ChangeEvent<HTMLInputElement>} */ event,
    ) => onChange(event.target.value),
  };
  if (definition.type === "boolean")
    return (
      <div className="ui-stack-xs">
        <Switch
          label={definition.label}
          checked={Boolean(value)}
          onChange={onChange}
        />
        {definition.description && (
          <span className="ui-help">{definition.description}</span>
        )}
      </div>
    );
  if (definition.options?.length)
    return (
      <Select
        label={definition.label}
        hint={definition.description}
        value={String(value ?? definition.default ?? "")}
        options={definition.options}
        onChange={(event) => {
          const selected = definition.options?.find(
            (option) => String(option.value) === event.target.value,
          );
          onChange(selected?.value ?? event.target.value);
        }}
      />
    );
  if (["number", "integer"].includes(definition.type))
    return (
      <NumberField
        {...common}
        min={definition.minimum}
        max={definition.maximum}
        step={definition.step || (definition.type === "integer" ? 1 : "any")}
        onChange={(event) =>
          onChange(
            definition.type === "integer"
              ? Number.parseInt(event.target.value || "0", 10)
              : Number(event.target.value),
          )
        }
      />
    );
  if (definition.type === "textarea" || definition.type === "json")
    return (
      <TextArea
        {...common}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  if (["file", "files", "directory", "saveFile"].includes(definition.type))
    return (
      <FileField
        definition={definition}
        nodeDefinition={nodeDefinition}
        value={value}
        selectedName={selectedName}
        onChange={onChange}
      />
    );
  return <TextField {...common} />;
}
