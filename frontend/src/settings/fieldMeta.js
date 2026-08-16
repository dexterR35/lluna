/** @param {string} value */
export function titleCase(value) {
  return value
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

/** @typedef {{label: string, description?: string, choices?: (string|number)[], hide?: boolean}} FieldMeta */

/** @type {Record<string, FieldMeta>} */
export const FIELD_META = {
  smart_cache_enabled: {
    label: "Smart cache",
    description:
      "Reuse unchanged deterministic node outputs. Generative nodes still run unless deterministic reuse is supported.",
  },
  run_history_limit: {
    label: "Run history limit",
    description: "Maximum completed runs kept in this local session.",
  },
  job_watchdog_seconds: {
    label: "Job watchdog (seconds)",
    description: "Fail a worker job when it stops reporting progress for this long.",
  },
  idle_release_seconds: {
    label: "Idle release (seconds)",
    description:
      "Release loaded model memory after this many idle seconds. Use 0 to keep models loaded.",
  },
  check_updates_on_startup: {
    label: "Check for updates on startup",
  },
  soft_defaults_applied: { label: "Soft defaults", hide: true },
  enabled_models: {
    label: "Enabled models",
    hide: true,
    description: "Managed from the Models section.",
  },

  "subtitle.inpaint_mode": {
    label: "Inpaint mode",
    description: "Algorithm used to repair subtitle regions.",
    choices: ["sttn-auto", "sttn-det", "lama", "propainter"],
  },
  "subtitle.subtitle_detect_mode": {
    label: "Detection mode",
    description: "OCR detector used to find subtitle text.",
    choices: ["PP_OCRv5_MOBILE", "PP_OCRv5_SERVER"],
  },
  "subtitle.selection_areas": {
    label: "Selection areas",
    description: "Normalized regions scanned for subtitles (y0,y1,x0,x1).",
  },
  "subtitle.sttn_neighbor_stride": { label: "STTN neighbor stride" },
  "subtitle.sttn_reference_length": { label: "STTN reference length" },
  "subtitle.sttn_max_load_num": { label: "STTN max frames" },
  "subtitle.propainter_max_load_num": { label: "ProPainter max frames" },
  "subtitle.mask_expansion_px": { label: "Mask expansion (px)" },
  "subtitle.area_y_axis_difference_px": { label: "Area Y difference (px)" },
  "subtitle.timeline_before_frames": { label: "Frames before" },
  "subtitle.timeline_after_frames": { label: "Frames after" },
  "subtitle.vertical_box_tolerance_px": { label: "Vertical box tolerance (px)" },
  "subtitle.box_tolerance_x_px": { label: "Box tolerance X (px)" },
  "subtitle.box_tolerance_y_px": { label: "Box tolerance Y (px)" },

  "enhancement.mode": {
    label: "Default model",
    description: "Preferred upscaling model.",
  },
  "enhancement.max_long_edge": {
    label: "Max long edge",
    description: "Limit output resolution by long edge.",
  },
  "enhancement.denoise_enabled": { label: "Denoise" },
  "enhancement.denoise_strength": {
    label: "Denoise strength",
    choices: ["safe", "medium"],
  },

  "low_light.mode": {
    label: "Default model",
    description: "Preferred low-light restoration model.",
  },
  "low_light.max_long_edge": {
    label: "Max long edge",
    description: "Maximum working resolution long edge.",
  },

  "generation.mode": {
    label: "Default model",
    description: "Preferred generation model.",
  },
  "generation.width": { label: "Width" },
  "generation.height": { label: "Height" },
  "generation.steps": { label: "Steps" },

  "object_selection.confidence_threshold": {
    label: "Confidence threshold",
    description: "Minimum SAM 3.1 match confidence before accepting a result.",
  },
  "object_selection.mask_threshold": {
    label: "Mask threshold",
    description: "Cutoff used to turn SAM 3.1's soft mask into a binary selection.",
  },

  // Flat aliases used by model option panels
  inpaint_mode: {
    label: "Inpaint mode",
    choices: ["sttn-auto", "sttn-det", "lama", "propainter"],
  },
  subtitle_detect_mode: {
    label: "Detection mode",
    choices: ["PP_OCRv5_MOBILE", "PP_OCRv5_SERVER"],
  },
  selection_areas: { label: "Selection areas" },
  hardware_acceleration: {
    label: "Hardware acceleration",
    description: "Use GPU acceleration when available, across all processing.",
  },
  sttn_neighbor_stride: { label: "STTN neighbor stride" },
  sttn_reference_length: { label: "STTN reference length" },
  sttn_max_load_num: { label: "STTN max frames" },
  propainter_max_load_num: { label: "ProPainter max frames" },
  mask_expansion_px: { label: "Mask expansion (px)" },
  box_tolerance_x_px: { label: "Box tolerance X (px)" },
  box_tolerance_y_px: { label: "Box tolerance Y (px)" },
  timeline_before_frames: { label: "Frames before" },
  timeline_after_frames: { label: "Frames after" },
  mode: { label: "Default model" },
  max_long_edge: { label: "Max long edge" },
  denoise_enabled: { label: "Denoise" },
  denoise_strength: { label: "Denoise strength", choices: ["safe", "medium"] },
  width: { label: "Width" },
  height: { label: "Height" },
  steps: { label: "Steps" },
  confidence_threshold: {
    label: "Confidence threshold",
    description: "Minimum SAM 3.1 match confidence before accepting a result.",
  },
  mask_threshold: {
    label: "Mask threshold",
    description: "Cutoff used to turn SAM 3.1's soft mask into a binary selection.",
  },
};

/** Ordered preference sections shown in Settings. */
export const PREFERENCE_SECTIONS = [
  {
    id: "editor",
    label: "Editor",
    description: "Canvas appearance and workspace behavior.",
  },
  {
    id: "runtime",
    label: "Runtime",
    description: "Execution, caching, and memory release behavior.",
  },
  {
    id: "subtitle",
    label: "Subtitle",
    description: "Detection and inpainting defaults for subtitle removal.",
  },
  {
    id: "enhancement",
    label: "Enhancement",
    description: "Upscaling and denoise defaults.",
  },
  {
    id: "low_light",
    label: "Low Light",
    description: "Low-light restoration defaults.",
  },
  {
    id: "generation",
    label: "Generation",
    description: "Image generation size and sampling defaults.",
  },
  {
    id: "object_selection",
    label: "Object Selection",
    description: "Segmentation and text-grounded selection defaults.",
  },
];
