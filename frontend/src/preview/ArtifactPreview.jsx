import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Download,
  Hand,
  Image as ImageIcon,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "../icons";
import { api, artifactObjectUrl, artifactThumbnailUrl } from "../api/client";
import { Badge, Button, EmptyState, LoadingState } from "../components";
import { useArtifactSaver } from "./useArtifactSaver";
import {
  normalizeSubtitleArea,
  subtitleAreaFromDrag,
  subtitleAreaStyle,
} from "./videoRegions";

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

/** @param {{state: import("../types").ArtifactPreviewState, alt: string, fit?: string, className?: string, controls?: boolean}} props */
function ArtifactMedia({
  state,
  alt,
  fit = "contain",
  className = "",
  controls = true,
}) {
  const url = state.url || undefined;
  if (state.metadata?.mediaType?.startsWith("video/"))
    return (
      <video
        src={url}
        aria-label={alt}
        controls={controls}
        muted={!controls}
        className={`${fit === "cover" ? "object-cover" : "object-contain"} ${className}`}
      />
    );
  if (state.metadata?.mediaType?.startsWith("audio/"))
    return (
      <div
        className={`flex items-center justify-center bg-mg-app ${className}`}
      >
        <audio
          src={url}
          aria-label={alt}
          controls
          className="w-full max-w-full px-2"
        />
      </div>
    );
  return (
    <img
      src={url}
      alt={alt}
      className={`${fit === "cover" ? "object-cover" : "object-contain"} ${className}`}
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

/** @param {{artifactId?: string, schemaId?: string, fit?: string, ratio?: string, label?: string, size?: "sm"|"md", useOriginal?: boolean}} props */
export function ArtifactThumbnail({
  artifactId,
  schemaId,
  fit = "cover",
  ratio = "wide",
  label = "Node output",
  size = "md",
  useOriginal = false,
}) {
  const state = useArtifact(artifactId, {
    thumbnail: !useOriginal,
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
/** @param {{artifactIds: string[], schemaId?: string, fit?: string, label?: string}} props */
export function ArtifactThumbGrid({
  artifactIds,
  schemaId,
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
            fit={fit}
            size="sm"
            label={`${label} ${index + 1}`}
          />
        </div>
      ))}
    </div>
  );
}

/** @param {{artifactId?: string, artifactIds?: string[], schemaId?: string, compact?: boolean, zoomable?: boolean, points?: Array<{x: number, y: number, label?: number}>, onPointAdd?: (point: {x: number, y: number, label: number}) => void, subtitleAreas?: number[][], onSubtitleAreaAdd?: (area: number[]) => void, onSubtitleAreasClear?: () => void, saveable?: boolean, statusLabel?: string}} props */
export function ArtifactPreview({
  artifactId,
  artifactIds,
  schemaId,
  compact = false,
  zoomable = true,
  points = [],
  onPointAdd,
  subtitleAreas = [],
  onSubtitleAreaAdd,
  onSubtitleAreasClear,
  saveable = true,
  statusLabel = "Stored locally",
}) {
  const ids = artifactIds?.length ? artifactIds : artifactId ? [artifactId] : [];
  const primaryId = ids.at(-1);
  const state = useArtifact(primaryId);
  const save = useArtifactSaver(ids, state, schemaId);
  const mediaWidth = state.metadata?.width || 0;
  const mediaHeight = state.metadata?.height || 0;
  const isVideo = Boolean(state.metadata?.mediaType?.startsWith("video/"));
  const [zoom, setZoom] = useState(1);
  const [panMode, setPanMode] = useState(false);
  const [panning, setPanning] = useState(false);
  const stageRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const panStart = useRef(
    /** @type {{x: number, y: number, left: number, top: number} | null} */ (null),
  );
  const [selectingArea, setSelectingArea] = useState(false);
  const [areaDrag, setAreaDrag] = useState(
    /** @type {{start: {x: number, y: number}, current: {x: number, y: number}} | null} */ (null),
  );
  useEffect(() => {
    setZoom(1);
    setPanMode(false);
    setPanning(false);
    panStart.current = null;
    setSelectingArea(false);
    setAreaDrag(null);
  }, [primaryId]);
  // A plain click means something else while these are active (add a point,
  // draw a removal box) - drag-to-pan only turns on by itself the rest of the
  // time, matching how the main canvas already behaves (no mode toggle
  // needed there either). The Move button still force-enables it either way.
  const canDragPan = !onPointAdd && !selectingArea;
  const dragPanActive = zoomable && (panMode || canDragPan);
  const contentRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  // CSS `zoom` resizes the scrollable content asynchronously relative to the
  // state update that triggers it, and the content sits centered (not flush
  // top-left) whenever it's smaller than the stage on an axis - so scrollLeft
  // alone can't tell us where the cursor lands on the image. The wheel
  // handler instead records the cursor as a fraction of the content's own
  // (pre-zoom) box, and a layout effect - which runs after the browser has
  // relaid-out the content at the new size - re-derives the content's
  // top-left in scroll space from its actual post-zoom geometry and scrolls
  // so that same fraction lands back under the cursor.
  const pendingZoomOrigin = useRef(
    /** @type {{fracX: number, fracY: number, cursorLeft: number, cursorTop: number} | null} */ (
      null
    ),
  );
  useEffect(() => {
    const stage = stageRef.current;
    const content = contentRef.current;
    if (!stage || !content || !zoomable) return undefined;
    /** @param {WheelEvent} event */
    function onWheel(event) {
      if (!stage || !content) return;
      event.preventDefault();
      const stageBounds = stage.getBoundingClientRect();
      const contentBounds = content.getBoundingClientRect();
      const cursorLeft = event.clientX - stageBounds.left;
      const cursorTop = event.clientY - stageBounds.top;
      const fracX = contentBounds.width
        ? (event.clientX - contentBounds.left) / contentBounds.width
        : 0.5;
      const fracY = contentBounds.height
        ? (event.clientY - contentBounds.top) / contentBounds.height
        : 0.5;
      setZoom((previous) => {
        const step = previous * 0.0015 * -event.deltaY;
        const next = Math.min(4, Math.max(0.5, previous + step));
        if (next === previous) return previous;
        pendingZoomOrigin.current = { fracX, fracY, cursorLeft, cursorTop };
        return next;
      });
    }
    stage.addEventListener("wheel", onWheel, { passive: false });
    return () => stage.removeEventListener("wheel", onWheel);
    // stageRef/contentRef.current are null until the stage below actually
    // mounts (the early returns above skip it entirely while
    // loading/erroring) - re-run once state.url flips truthy so the listener
    // attaches to the real nodes.
  }, [zoomable, state.url]);
  useLayoutEffect(() => {
    const stage = stageRef.current;
    const content = contentRef.current;
    const pending = pendingZoomOrigin.current;
    if (!stage || !content || !pending) return;
    pendingZoomOrigin.current = null;
    const stageBounds = stage.getBoundingClientRect();
    const contentBounds = content.getBoundingClientRect();
    // Content's top-left in scroll space, i.e. where it'd sit if scrollLeft/
    // Top were reset to 0 - derived from where it's actually rendered now.
    const contentScrollLeft =
      contentBounds.left - stageBounds.left + stage.scrollLeft;
    const contentScrollTop =
      contentBounds.top - stageBounds.top + stage.scrollTop;
    stage.scrollLeft =
      contentScrollLeft + pending.fracX * contentBounds.width - pending.cursorLeft;
    stage.scrollTop =
      contentScrollTop + pending.fracY * contentBounds.height - pending.cursorTop;
  }, [zoom]);
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

  const boundedAreas = subtitleAreas.flatMap((area) => {
    const bounded = normalizeSubtitleArea(area, mediaWidth, mediaHeight);
    return bounded ? [bounded] : [];
  });
  const draftArea = areaDrag
    ? subtitleAreaFromDrag(
        areaDrag.start,
        areaDrag.current,
        mediaWidth,
        mediaHeight,
      )
    : null;

  /** @param {import("react").PointerEvent<HTMLDivElement>} event */
  function mediaPoint(event) {
    const bounds = event.currentTarget.getBoundingClientRect();
    return {
      x: ((event.clientX - bounds.left) / bounds.width) * mediaWidth,
      y: ((event.clientY - bounds.top) / bounds.height) * mediaHeight,
    };
  }

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
              onClick={() => {
                setZoom(1);
                if (stageRef.current) {
                  stageRef.current.scrollLeft = 0;
                  stageRef.current.scrollTop = 0;
                }
              }}
            >
              <RotateCcw className="ui-icon-sm" />
            </Button>
            <Button
              variant={panMode ? "primary" : "ghost"}
              className="min-h-6 px-1.5"
              aria-label="Move preview"
              aria-pressed={panMode}
              onClick={() => {
                setPanMode((value) => !value);
                setSelectingArea(false);
                setAreaDrag(null);
              }}
            >
              <Hand className="ui-icon-sm" />
            </Button>
          </div>
        )}
        {isVideo && onSubtitleAreaAdd && (
          <div className="ui-actions mr-auto">
            <Button
              variant={selectingArea ? "primary" : "secondary"}
              className="min-h-6 px-2 text-[9px]"
              onClick={() => {
                setSelectingArea((value) => !value);
                setPanMode(false);
                setAreaDrag(null);
              }}
            >
              {selectingArea ? "Finish selecting" : "Draw removal area"}
            </Button>
            <Button
              variant="ghost"
              className="min-h-6 px-2 text-[9px]"
              disabled={!boundedAreas.length}
              onClick={onSubtitleAreasClear}
            >
              Clear areas
            </Button>
            <Badge tone={boundedAreas.length ? "accent" : "neutral"} size="xs">
              {boundedAreas.length} area{boundedAreas.length === 1 ? "" : "s"}
            </Badge>
          </div>
        )}
        <PreviewMeta metadata={state.metadata} />
      </div>
      <div
        ref={stageRef}
        className={`ui-preview-stage checkerboard overflow-auto ${dragPanActive ? (panning ? "cursor-grabbing" : "cursor-grab") : ""} ${compact ? "min-h-28 max-h-52" : "min-h-44 max-h-[26rem]"}`}
        onPointerDown={
          dragPanActive
            ? (event) => {
                if (event.button !== 0) return;
                event.preventDefault();
                event.currentTarget.setPointerCapture(event.pointerId);
                panStart.current = {
                  x: event.clientX,
                  y: event.clientY,
                  left: event.currentTarget.scrollLeft,
                  top: event.currentTarget.scrollTop,
                };
                setPanning(true);
              }
            : undefined
        }
        onPointerMove={
          dragPanActive
            ? (event) => {
                const start = panStart.current;
                if (!start) return;
                event.currentTarget.scrollLeft =
                  start.left - (event.clientX - start.x);
                event.currentTarget.scrollTop =
                  start.top - (event.clientY - start.y);
              }
            : undefined
        }
        onPointerUp={() => {
          panStart.current = null;
          setPanning(false);
        }}
        onPointerCancel={() => {
          panStart.current = null;
          setPanning(false);
        }}
      >
        <div
          ref={contentRef}
          className={`relative inline-grid place-items-center ${onPointAdd ? "cursor-crosshair" : ""}`}
          style={{ zoom }}
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
            className={`${compact ? "max-h-52" : "max-h-[26rem]"} col-start-1 row-start-1 block max-w-full`}
          />
          {isVideo && mediaWidth > 0 && mediaHeight > 0 && (
            <div
              aria-label="Video removal area canvas"
              className={`absolute inset-0 col-start-1 row-start-1 ${selectingArea ? "cursor-crosshair" : "pointer-events-none"}`}
              onPointerDown={
                selectingArea
                  ? (event) => {
                      event.preventDefault();
                      event.currentTarget.setPointerCapture(event.pointerId);
                      const point = mediaPoint(event);
                      setAreaDrag({ start: point, current: point });
                    }
                  : undefined
              }
              onPointerMove={
                selectingArea && areaDrag
                  ? (event) =>
                      setAreaDrag((value) =>
                        value
                          ? { ...value, current: mediaPoint(event) }
                          : value,
                      )
                  : undefined
              }
              onPointerUp={
                selectingArea && areaDrag
                  ? (event) => {
                      const area = subtitleAreaFromDrag(
                        areaDrag.start,
                        mediaPoint(event),
                        mediaWidth,
                        mediaHeight,
                      );
                      setAreaDrag(null);
                      if (area) onSubtitleAreaAdd?.(area);
                    }
                  : undefined
              }
              onPointerCancel={() => setAreaDrag(null)}
            >
              {boundedAreas.map((area, index) => (
                <span
                  key={`${area.join("-")}-${index}`}
                  className="pointer-events-none absolute border-2 border-mg-accent bg-mg-accent/20 shadow-[0_0_0_1px_rgba(0,0,0,0.5)]"
                  style={subtitleAreaStyle(area, mediaWidth, mediaHeight)}
                >
                  <span className="absolute -top-5 left-0 rounded bg-mg-accent px-1.5 py-0.5 text-[8px] font-semibold text-white">
                    Remove {index + 1}
                  </span>
                </span>
              ))}
              {draftArea && (
                <span
                  className="pointer-events-none absolute border-2 border-dashed border-white bg-mg-accent/15"
                  style={subtitleAreaStyle(draftArea, mediaWidth, mediaHeight)}
                />
              )}
            </div>
          )}
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
          {isVideo && onSubtitleAreaAdd
            ? selectingArea
              ? "Drag a rectangle over the text to remove"
              : boundedAreas.length
                ? `${boundedAreas.length} removal area${boundedAreas.length === 1 ? "" : "s"} selected`
                : "Pause on a frame, then draw the text area"
            : statusLabel}
        </span>
        {saveable && (
          <Button
            variant="secondary"
            onClick={save}
            className="min-h-6 px-2 text-[9px]"
          >
            <Download className="ui-icon-sm" />
            {ids.length > 1 ? `Save ${ids.length}` : "Save"}
          </Button>
        )}
      </div>
    </div>
  );
}
