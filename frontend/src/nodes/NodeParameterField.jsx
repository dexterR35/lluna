import { useState } from "react";
import {
  LoaderCircle,
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
    const desktop = window.midgardDesktop;
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
    const desktop = window.midgardDesktop;
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
