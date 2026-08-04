import { useState } from "react";
import { FileImage, Film, LoaderCircle, Upload } from "lucide-react";
import {
  Button,
  IconTile,
  NumberField,
  Select,
  Switch,
  TextArea,
  TextField,
} from "../components";

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

  /** @param {() => Promise<import("../types").DesktopGrant | import("../types").DesktopGrant[] | null | undefined>} action */
  async function selectGrant(action) {
    setError("");
    setLoading(true);
    try {
      const selection = await action();
      const grants = Array.isArray(selection)
        ? selection
        : selection
          ? [selection]
          : [];
      if (!grants.length) return;
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
    const desktop = window.midgardDesktop;
    if (!desktop) return;
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
    const files = [...event.dataTransfer.files].filter((item) =>
      acceptsFile(item, kind),
    );
    if (!files.length) {
      setError(
        kind === "video"
          ? "Drop a supported video file."
          : "Drop a supported image file.",
      );
      return;
    }
    const desktop = window.midgardDesktop;
    if (!desktop?.registerDroppedFiles) {
      setError("File drop is available in the desktop app.");
      return;
    }
    await selectGrant(async () => {
      const grants = await desktop.registerDroppedFiles(
        multiple ? files : files.slice(0, 1),
      );
      return multiple ? grants : grants.at(0);
    });
  }

  if (definition.type === "saveFile")
    return (
      <div className="grid gap-1.5">
        <span className="text-[11px] font-medium text-mg-secondary">
          {definition.label}
        </span>
        <Button variant="secondary" onClick={choose} disabled={loading}>
          {loading && <LoaderCircle className="size-3 animate-spin" />}
          {value ? "Change save location" : "Choose save location"}
        </Button>
      </div>
    );

  const KindIcon = kind === "video" ? Film : FileImage;
  return (
    <div className="grid gap-1.5">
      <span className="text-[11px] font-medium text-mg-secondary">
        {definition.label}
      </span>
      <div
        role="button"
        tabIndex={0}
        aria-label={`Drop ${multiple ? `${kind} files` : `${kind} file`}`}
        className={`grid min-h-28 place-items-center rounded-2xl border border-dashed px-4 py-3 text-center transition ${dragging ? "border-mg-accent bg-mg-accent/10" : "border-mg-border bg-mg-app/45 hover:border-mg-secondary/60"}`}
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
        <div className="grid justify-items-center gap-1.5">
          <IconTile className="bg-mg-elevated text-mg-accent">
            {loading ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <KindIcon className="size-4" />
            )}
          </IconTile>
          <strong className="text-[10px] font-semibold text-mg-primary">
            {dragging
              ? `Drop ${multiple ? `${kind} files` : kind} now`
              : multiple && selectedCount
                ? `${selectedCount} images selected`
                : selectedName || `Drop ${kind} here`}
          </strong>
          <span className="text-[9px] text-mg-muted">
            {selectedCount
              ? multiple
                ? "Choose or drop files to replace this queue"
                : "Drop another file to replace it"
              : multiple
                ? "or choose multiple local files"
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
            <Upload className="size-3" />
            {selectedCount
              ? "Replace"
              : multiple
                ? "Choose files"
                : "Choose file"}
          </Button>
        </div>
      </div>
      {error && (
        <span role="alert" className="text-[9px] text-mg-error">
          {error}
        </span>
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
      <Switch
        label={definition.label}
        checked={Boolean(value)}
        onChange={onChange}
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
  if (definition.options?.length)
    return (
      <Select
        label={definition.label}
        hint={definition.description}
        value={String(value ?? "")}
        options={definition.options}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  if (["file", "files", "saveFile"].includes(definition.type))
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
