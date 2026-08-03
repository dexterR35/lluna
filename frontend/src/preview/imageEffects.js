export const IMAGE_EFFECT_OPTIONS = [
  { value: "none", label: "Original" },
  { value: "vivid", label: "Vivid" },
  { value: "soft", label: "Soft light" },
  { value: "warm", label: "Warm" },
  { value: "cool", label: "Cool" },
  { value: "mono", label: "Monochrome" },
];

export const IMAGE_EFFECTS = {
  none: "none",
  vivid: "saturate(1.35) contrast(1.08)",
  mono: "grayscale(1) contrast(1.08)",
  soft: "saturate(.82) brightness(1.08) contrast(.92)",
  warm: "sepia(.18) saturate(1.16) hue-rotate(-8deg) contrast(1.02)",
  cool: "saturate(.94) hue-rotate(12deg) contrast(1.05)",
};
