import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Download,
  Image as ImageIcon,
} from "lucide-react";
import { api, artifactObjectUrl, saveArtifact } from "../api/client";
import { Badge, Button, EmptyState, LoadingState } from "../components";
import { useToast } from "../components/ToastContext";
import { IMAGE_EFFECTS } from "./imageEffects";

/** @param {string | undefined} artifactId */
function useArtifact(artifactId) {
  const [state, setState] = useState(
    /** @type {import("../types").ArtifactPreviewState} */ ({
      url: null,
      metadata: null,
      error: null,
    }),
  );
  useEffect(() => {
    let alive = true;
    /** @type {string | undefined} */
    let url;
    if (!artifactId) {
      setState({ url: null, metadata: null, error: null });
      return undefined;
    }
    setState({ url: null, metadata: null, error: null });
    Promise.all([
      artifactObjectUrl(artifactId),
      api(`/api/artifacts/${artifactId}/metadata`),
    ])
      .then(([value, metadata]) => {
        url = value;
        if (alive) setState({ url: value, metadata, error: null });
      })
      .catch(
        (error) =>
          alive &&
          setState({
            url: null,
            metadata: null,
            error: error instanceof Error ? error.message : String(error),
          }),
      );
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [artifactId]);
  return state;
}

/** @param {{state: import("../types").ArtifactPreviewState, alt: string, effect?: string, fit?: string, className?: string, controls?: boolean}} props */
function ArtifactMedia({
  state,
  alt,
  effect = "none",
  fit = "contain",
  className = "",
  controls = true,
}) {
  const style = { filter: IMAGE_EFFECTS[effect] || IMAGE_EFFECTS.none };
  const url = state.url || undefined;
  if (state.metadata?.mediaType?.startsWith("video/"))
    return (
      <video
        src={url}
        aria-label={alt}
        controls={controls}
        muted={!controls}
        className={`${fit === "cover" ? "object-cover" : "object-contain"} ${className}`}
        style={style}
      />
    );
  return (
    <img
      src={url}
      alt={alt}
      className={`${fit === "cover" ? "object-cover" : "object-contain"} ${className}`}
      style={style}
    />
  );
}

/** @param {string | undefined} artifactId @param {import("../types").ArtifactPreviewState} state */
function useArtifactSaver(artifactId, state) {
  const toast = useToast();
  return async function save() {
    if (!artifactId || !state.url) return;
    const desktop = window.midgardDesktop;
    if (!desktop) {
      const anchor = document.createElement("a");
      anchor.href = state.url;
      anchor.download = state.metadata?.mediaType?.startsWith("video/")
        ? "midgard-output.mp4"
        : "midgard-output.png";
      anchor.click();
      return;
    }
    try {
      const kind = state.metadata?.mediaType?.startsWith("video/")
        ? "video"
        : "image";
      const grant = await desktop.selectSaveFile(kind);
      if (!grant) return;
      const result = await saveArtifact(artifactId, grant.grantId);
      toast.push(`Saved ${result.name}`);
    } catch (error) {
      toast.push(
        error instanceof Error ? error.message : String(error),
        "error",
      );
    }
  };
}

/** @param {number | undefined} value */
function formatBytes(value) {
  if (!value) return null;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

/** @param {{metadata: import("../types").ArtifactMetadata | null}} props */
function PreviewMeta({ metadata }) {
  const dimensions =
    metadata?.width && metadata?.height
      ? `${metadata.width} × ${metadata.height}`
      : null;
  const type = metadata?.mediaType?.split("/").at(-1)?.toUpperCase();
  const duration = metadata?.duration
    ? `${metadata.duration.toFixed(1)}s`
    : null;
  return (
    <div
      className="flex min-w-0 flex-wrap items-center justify-end gap-1.5"
      aria-label="Media metadata"
    >
      {dimensions && <Badge size="xs">{dimensions}</Badge>}
      {type && <Badge size="xs">{type}</Badge>}
      {metadata?.byteSize && (
        <Badge size="xs">{formatBytes(metadata.byteSize)}</Badge>
      )}
      {duration && <Badge size="xs">{duration}</Badge>}
      {metadata?.frameCount && (
        <Badge size="xs">{metadata.frameCount} frames</Badge>
      )}
      {metadata?.alpha && <Badge size="xs">Alpha</Badge>}
    </div>
  );
}

/** @param {{artifactId?: string, effect?: string, fit?: string, ratio?: string, label?: string}} props */
export function ArtifactThumbnail({
  artifactId,
  effect = "none",
  fit = "cover",
  ratio = "wide",
  label = "Node output",
}) {
  const state = useArtifact(artifactId);
  const save = useArtifactSaver(artifactId, state);
  const height =
    ratio === "square"
      ? "min-h-[168px] flex-1"
      : ratio === "cinema"
        ? "h-24"
        : "h-28";
  if (!artifactId) return null;
  if (state.error)
    return (
      <div
        className={`${height} flex items-center justify-center gap-1.5 border-y border-mg-border bg-mg-error/5 text-[9px] text-mg-error`}
      >
        <AlertTriangle className="size-3" />
        Preview unavailable
      </div>
    );
  if (!state.url)
    return (
      <div
        className={`${height} animate-pulse border-y border-mg-border bg-mg-app/70`}
        aria-label={`Loading ${label}`}
      />
    );
  return (
    <div
      className={`checkerboard group/preview relative ${height} overflow-hidden border-y border-mg-border bg-mg-app`}
    >
      <ArtifactMedia
        state={state}
        alt={label}
        effect={effect}
        fit={fit}
        controls={false}
        className="size-full"
      />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-black/70 to-transparent opacity-0 transition group-hover/preview:opacity-100" />
      <button
        type="button"
        className="nodrag absolute bottom-1.5 right-1.5 grid size-7 place-items-center rounded-lg border border-white/10 bg-black/65 text-white opacity-0 backdrop-blur transition hover:bg-black/90 group-hover/preview:opacity-100 focus-visible:opacity-100"
        aria-label={`Save ${label}`}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation();
          void save();
        }}
      >
        <Download className="size-3" />
      </button>
    </div>
  );
}

/** @param {{artifactId?: string, effect?: string, compact?: boolean}} props */
export function ArtifactPreview({
  artifactId,
  effect = "none",
  compact = false,
}) {
  const state = useArtifact(artifactId);
  const save = useArtifactSaver(artifactId, state);
  if (!artifactId)
    return (
      <EmptyState
        icon={<ImageIcon className="size-4" />}
        title="No preview yet"
        description="Run this node or parent flow to create a local result."
        compact
      />
    );
  if (state.error)
    return (
      <EmptyState
        icon={<AlertTriangle className="size-4" />}
        title="Preview unavailable"
        description={state.error}
        compact
      />
    );
  if (!state.url) return <LoadingState label="Loading preview" />;

  return (
    <div className="overflow-hidden rounded-2xl border border-mg-border bg-mg-app">
      <div className="flex h-9 items-center gap-2 border-b border-mg-border bg-mg-elevated/80 px-2.5">
 
     
        <span className="flex-1" />
        <PreviewMeta metadata={state.metadata} />
      </div>
      <div
        className={`checkerboard relative grid place-items-center overflow-hidden ${compact ? "min-h-28 max-h-52" : "min-h-44 max-h-[26rem]"}`}
      >
        <ArtifactMedia
          state={state}
          alt="Completed output preview"
          effect={effect}
          className={`${compact ? "max-h-52" : "max-h-[26rem]"} max-w-full`}
        />
      </div>
      <div className="flex min-h-9 items-center gap-2 border-t border-mg-border bg-mg-elevated/50 px-2">
        <span className="size-1.5 rounded-full bg-mg-success" />
        <span className="min-w-0 flex-1 truncate text-[9px] text-mg-muted">
          Stored locally
        </span>
        <Button
          variant="secondary"
          onClick={save}
          className="min-h-6 px-2 text-[9px]"
        >
          <Download className="size-3" />
          Save
        </Button>
      </div>
    </div>
  );
}
