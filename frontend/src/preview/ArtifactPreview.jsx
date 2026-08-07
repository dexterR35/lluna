import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Download,
  Image as ImageIcon,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "../icons";
import { api, artifactObjectUrl, artifactThumbnailUrl } from "../api/client";
import { Badge, Button, EmptyState, LoadingState } from "../components";
import { IMAGE_EFFECTS } from "./imageEffects";
import { useArtifactSaver } from "./useArtifactSaver";

/** @param {string | undefined} artifactId @param {{thumbnail?: boolean, maxEdge?: number}} [options] */
function useArtifact(artifactId, options = {}) {
  const thumbnail = options.thumbnail === true;
  const maxEdge = options.maxEdge || 256;
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
    const media = thumbnail
      ? artifactThumbnailUrl(artifactId, { maxEdge })
      : artifactObjectUrl(artifactId);
    Promise.all([media, api(`/api/artifacts/${artifactId}/metadata`)])
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
  }, [artifactId, thumbnail, maxEdge]);
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
      className="ui-actions min-w-0 justify-end"
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

/** @param {{artifactId?: string, schemaId?: string, effect?: string, fit?: string, ratio?: string, label?: string, size?: "sm"|"md"}} props */
export function ArtifactThumbnail({
  artifactId,
  schemaId,
  effect = "none",
  fit = "cover",
  ratio = "wide",
  label = "Node output",
  size = "md",
}) {
  const state = useArtifact(artifactId, {
    thumbnail: true,
    maxEdge: size === "sm" ? 128 : 256,
  });
  const save = useArtifactSaver(artifactId, state, schemaId);
  const height =
    size === "sm"
      ? "h-full min-h-0"
      : ratio === "square"
        ? "min-h-[196px] flex-1"
        : ratio === "cinema"
          ? "h-24"
          : "h-28";
  if (!artifactId) return null;
  if (state.error)
    return (
      <div
        className={`${height} flex items-center justify-center gap-1.5 border-y border-mg-border bg-mg-error/5 text-[9px] text-mg-error`}
      >
        <AlertTriangle className="ui-icon-sm" />
        {size === "sm" ? "!" : "Preview unavailable"}
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
      className={`checkerboard group/preview relative ${height} overflow-hidden border-y border-mg-border bg-mg-app ${size === "sm" ? "border-0" : ""}`}
    >
      <ArtifactMedia
        state={state}
        alt={label}
        effect={effect}
        fit={fit}
        controls={false}
        className="size-full"
      />
      {size !== "sm" && (
        <>
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-black/70 to-transparent opacity-0 transition group-hover/preview:opacity-100" />
          <button
            type="button"
            className="nodrag absolute bottom-1.5 right-1.5 grid size-7 place-items-center rounded-mg border border-white/10 bg-black/65 text-white opacity-0 transition hover:bg-black/90 group-hover/preview:opacity-100 focus-visible:opacity-100"
            aria-label={`Save ${label}`}
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.stopPropagation();
              void save();
            }}
          >
            <Download className="ui-icon-sm" />
          </button>
        </>
      )}
    </div>
  );
}

/** Compact multi-image thumb grid for node bodies (thumbnails only). */
/** @param {{artifactIds: string[], schemaId?: string, effect?: string, fit?: string, label?: string}} props */
export function ArtifactThumbGrid({
  artifactIds,
  schemaId,
  effect = "none",
  fit = "cover",
  label = "Node output",
}) {
  const ids = artifactIds.slice(0, 10);
  if (!ids.length) return null;
  return (
    <div
      className="lluna-node-thumbs"
      aria-label={`${label} thumbnails`}
    >
      {ids.map((id, index) => (
        <div key={id} className="lluna-node-thumb">
          <ArtifactThumbnail
            artifactId={id}
            schemaId={schemaId}
            effect={effect}
            fit={fit}
            size="sm"
            label={`${label} ${index + 1}`}
          />
        </div>
      ))}
    </div>
  );
}

/** @param {{artifactId?: string, artifactIds?: string[], schemaId?: string, effect?: string, compact?: boolean, zoomable?: boolean, points?: Array<{x: number, y: number, label?: number}>, onPointAdd?: (point: {x: number, y: number, label: number}) => void}} props */
export function ArtifactPreview({
  artifactId,
  artifactIds,
  schemaId,
  effect = "none",
  compact = false,
  zoomable = true,
  points = [],
  onPointAdd,
}) {
  const ids = artifactIds?.length ? artifactIds : artifactId ? [artifactId] : [];
  const primaryId = ids.at(-1);
  const state = useArtifact(primaryId);
  const save = useArtifactSaver(ids, state, schemaId);
  const mediaWidth = state.metadata?.width || 0;
  const mediaHeight = state.metadata?.height || 0;
  const isVideo = Boolean(state.metadata?.mediaType?.startsWith("video/"));
  const [zoom, setZoom] = useState(1);
  useEffect(() => setZoom(1), [primaryId]);
  if (!primaryId)
    return (
      <EmptyState
        icon={<ImageIcon className="ui-icon-lg" />}
        title="No preview yet"
        description="Run this node or parent flow to create a local result."
        compact
      />
    );
  if (state.error)
    return (
      <EmptyState
        icon={<AlertTriangle className="ui-icon-lg" />}
        title="Preview unavailable"
        description={state.error}
        compact
      />
    );
  if (!state.url) return <LoadingState label="Loading preview" />;

  return (
    <div className="ui-preview">
      <div className="ui-preview-bar is-header">
        {zoomable && (
          <div className="ui-actions mr-auto" aria-label="Preview zoom controls">
            <Button
              variant="ghost"
              className="min-h-6 px-1.5"
              aria-label="Zoom out"
              disabled={zoom <= 0.5}
              onClick={() => setZoom((value) => Math.max(0.5, value - 0.25))}
            >
              <ZoomOut className="ui-icon-sm" />
            </Button>
            <span className="min-w-9 text-center text-[9px] tabular-nums text-mg-muted">
              {Math.round(zoom * 100)}%
            </span>
            <Button
              variant="ghost"
              className="min-h-6 px-1.5"
              aria-label="Zoom in"
              disabled={zoom >= 4}
              onClick={() => setZoom((value) => Math.min(4, value + 0.25))}
            >
              <ZoomIn className="ui-icon-sm" />
            </Button>
            <Button
              variant="ghost"
              className="min-h-6 px-1.5"
              aria-label="Reset zoom"
              disabled={zoom === 1}
              onClick={() => setZoom(1)}
            >
              <RotateCcw className="ui-icon-sm" />
            </Button>
          </div>
        )}
        <PreviewMeta metadata={state.metadata} />
      </div>
      <div
        className={`ui-preview-stage checkerboard overflow-auto ${compact ? "min-h-28 max-h-52" : "min-h-44 max-h-[26rem]"}`}
      >
        <div
          className={`relative inline-grid place-items-center transition-transform ${onPointAdd ? "cursor-crosshair" : ""}`}
          style={{ transform: `scale(${zoom})`, transformOrigin: "center" }}
          onClick={
            onPointAdd &&
            mediaWidth &&
            mediaHeight &&
            !isVideo
              ? (event) => {
                  const bounds = event.currentTarget.getBoundingClientRect();
                  onPointAdd({
                    x: Math.max(
                      0,
                      Math.min(
                        mediaWidth,
                        ((event.clientX - bounds.left) / bounds.width) *
                          mediaWidth,
                      ),
                    ),
                    y: Math.max(
                      0,
                      Math.min(
                        mediaHeight,
                        ((event.clientY - bounds.top) / bounds.height) *
                          mediaHeight,
                      ),
                    ),
                    label: event.shiftKey ? 0 : 1,
                  });
                }
              : undefined
          }
        >
          <ArtifactMedia
            state={state}
            alt="Completed output preview"
            effect={effect}
            className={`${compact ? "max-h-52" : "max-h-[26rem]"} col-start-1 row-start-1 block max-w-full`}
          />
          {mediaWidth > 0 &&
            mediaHeight > 0 &&
            points.map((point, index) => (
              <span
                key={`${point.x}-${point.y}-${index}`}
              className={`pointer-events-none absolute grid size-4 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-white text-[8px] font-bold text-white ${point.label === 0 ? "bg-mg-error" : "bg-mg-success"}`}
                style={{
                  left: `${(point.x / mediaWidth) * 100}%`,
                  top: `${(point.y / mediaHeight) * 100}%`,
                }}
              >
                {point.label === 0 ? "−" : "+"}
              </span>
            ))}
        </div>
      </div>
      <div className="ui-preview-bar is-footer">
        <span className="size-1.5 rounded-full bg-mg-success" />
        <span className="ui-copy-muted min-w-0 flex-1 truncate text-[9px]">
          Stored locally
        </span>
        <Button
          variant="secondary"
          onClick={save}
          className="min-h-6 px-2 text-[9px]"
        >
          <Download className="ui-icon-sm" />
          {ids.length > 1 ? `Save ${ids.length}` : "Save"}
        </Button>
      </div>
    </div>
  );
}
