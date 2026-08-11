/**
 * Shared Lucide icon + accent registry for Lluna.
 * Import icons and resolvers from here — not from lucide-react.
 */
export {
  AlertTriangle,
  AudioLines,
  Ban,
  Blocks,
  Box,
  CaptionsOff,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Cpu,
  Database,
  Download,
  ExternalLink,
  Eye,
  FileBox,
  FileImage,
  Film,
  FolderOpen,
  Hash,
  Hand,
  History,
  Image,
  Image as ImageIcon,
  Images,
  Layers3,
  Link2,
  ListOrdered,
  LoaderCircle,
  LockKeyhole,
  Logs,
  Minus,
  Monitor,
  Moon,
  MousePointer2,
  Paintbrush,
  PanelLeftClose,
  PanelLeftOpen,
  Pause,
  Play,
  Plus,
  Redo2,
  RefreshCw,
  RotateCcw,
  Save,
  Scan,
  Scissors,
  ScrollText,
  Search,
  Settings,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  Stethoscope,
  Subtitles,
  Sun,
  TextCursorInput,
  Trash2,
  Type,
  Undo2,
  Upload,
  Wand2,
  Wifi,
  WifiOff,
  Workflow,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

import {
  AlertTriangle,
  AudioLines,
  Ban,
  Blocks,
  Box,
  CaptionsOff,
  Check,
  Clock3,
  Cpu,
  Eye,
  FileBox,
  FileImage,
  Film,
  FolderOpen,
  Hash,
  Image,
  Images,
  Layers3,
  ListOrdered,
  LoaderCircle,
  Monitor,
  Moon,
  MousePointer2,
  Paintbrush,
  Pause,
  Play,
  RefreshCw,
  Save,
  Scan,
  Scissors,
  Sparkles,
  Square,
  Subtitles,
  Sun,
  TextCursorInput,
  Type,
  Wand2,
  X,
  ZoomIn,
} from "lucide-react";

/** @typedef {import("react").ComponentType<{className?: string, "aria-hidden"?: boolean, style?: import("react").CSSProperties}>} AppIcon */

/** Shared accent palette for flows, categories, library icons, ports, and links. */
/** @type {Readonly<Record<string, string>>} */
export const FLOW_COLORS = Object.freeze({
  teal: "#63cbb6",
  blue: "#70b7f8",
  violet: "#a393fa",
  amber: "#e8b768",
  rose: "#ef7182",
  slate: "#9298a7",
});

/** Aliases so Image / IMAGE / film / VIDEO all hit the same key. */
/** @type {Readonly<Record<string, string>>} */
const ALIASES = Object.freeze({
  film: "video",
  scan: "mask",
  prompt: "text",
  string: "text",
  integer: "number",
  seed: "number",
  paintbrush: "color",
  save: "output",
});

/** @param {string | undefined} name */
function key(name) {
  const raw = String(name || "")
    .split("/")[0]
    .trim()
    .toLowerCase();
  return ALIASES[raw] || raw;
}

/** One icon per name — nodes, ports, and categories share these. */
/** @type {Readonly<Record<string, AppIcon>>} */
const ICONS = Object.freeze({
  image: Image,
  images: Images,
  video: Film,
  mask: Scan,
  alpha: Layers3,
  audio: AudioLines,
  text: Type,
  number: Hash,
  boolean: Square,
  enum: ListOrdered,
  color: Paintbrush,
  file: FileImage,
  path: FileBox,
  directory: FolderOpen,
  model: Box,
  input: Image,
  output: Save,
  sparkles: Sparkles,
  "zoom-in": ZoomIn,
  scissors: Scissors,
  sun: Sun,
  layers: Layers3,
  "mouse-pointer-2": MousePointer2,
  "captions-off": CaptionsOff,
  eye: Eye,
  play: Play,
  "text-cursor-input": TextCursorInput,
});

/** One flow color per name — same keys as ICONS. */
/** @type {Readonly<Record<string, string>>} */
const COLORS = Object.freeze({
  image: FLOW_COLORS.blue,
  video: FLOW_COLORS.violet,
  mask: FLOW_COLORS.amber,
  alpha: FLOW_COLORS.teal,
  color: FLOW_COLORS.teal,
  text: FLOW_COLORS.amber,
  enum: FLOW_COLORS.amber,
  audio: FLOW_COLORS.rose,
  number: FLOW_COLORS.rose,
  boolean: FLOW_COLORS.rose,
  input: FLOW_COLORS.teal,
  output: FLOW_COLORS.rose,
  file: FLOW_COLORS.teal,
  path: FLOW_COLORS.teal,
  directory: FLOW_COLORS.teal,
  model: FLOW_COLORS.slate,
});

/** Run / node status → Lucide component. */
/** @type {Readonly<Record<string, AppIcon>>} */
export const STATUS_ICONS = Object.freeze({
  RUNNING: LoaderCircle,
  SUCCEEDED: Check,
  FAILED: X,
  CACHED: Sparkles,
  PAUSED: Pause,
  PAUSE_REQUESTED: Clock3,
  DISABLED: Ban,
  INVALID: AlertTriangle,
  STALE: RefreshCw,
});

/** Settings preference section → Lucide component. */
/** @type {Readonly<Record<string, AppIcon>>} */
export const SECTION_ICONS = Object.freeze({
  editor: Monitor,
  runtime: Cpu,
  subtitle: Subtitles,
  enhancement: Sparkles,
  low_light: Moon,
  generation: Wand2,
  object_selection: MousePointer2,
  models: Box,
});

/** @param {string | undefined} icon */
export function resolveNodeIcon(icon) {
  return ICONS[key(icon)] || Box;
}

/** @param {string | undefined} type */
export function resolvePortIcon(type) {
  return ICONS[key(type)] || Box;
}

/** @param {string | undefined} category */
export function resolveCategoryIcon(category) {
  return ICONS[key(category)] || Blocks;
}

/** @param {string | undefined} status */
export function resolveStatusIcon(status) {
  return STATUS_ICONS[status || ""] || Box;
}

/** @param {string | undefined} category */
export function resolveCategoryColor(category) {
  return COLORS[key(category)] || FLOW_COLORS.slate;
}

/** @param {string | undefined} type */
export function resolvePortColor(type) {
  return COLORS[key(type)] || FLOW_COLORS.slate;
}

/** @param {string | undefined} name */
export function resolveFlowColor(name) {
  return FLOW_COLORS[name || ""] || FLOW_COLORS.teal;
}

/** @param {string | undefined} section */
export function resolveSectionIcon(section) {
  return SECTION_ICONS[section || ""] || Box;
}

/** @param {string} source @param {string} target */
export function compatibleTypes(source, target) {
  return source === target || (source === "INTEGER" && target === "NUMBER");
}
