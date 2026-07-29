# Alpha matting and professional edge refinement

## Pipeline

```text
source
 → coarse subject alpha
 → apply explicit foreground/background/unknown trimap constraints
 → matte/refine unknown band
 → morphology (contract/expand)
 → edge-aware smooth/feather
 → RGB spill decontamination
 → protect-alpha union
 → alpha/RGB quality checks
```

The protect union can occur before inspection and after model alpha, but it must
precede export. If no protect layer exists—or all protect pixels are zero—the model
result is unchanged.

## Trimap and unknown band

Generate a starting trimap from alpha thresholds plus erosion/dilation. Users can
paint foreground, background, and unknown roles. Unknown is resolved by a matting
provider using the original image, never a background-replaced preview.

Hair, fur, smoke, motion-blurred edges, veils, and glass require training/benchmark
fixtures distinct from solid products. Semi-transparent recovery must estimate both
alpha and uncontaminated foreground color; alpha alone cannot reconstruct glass
that refracts an unknown background. Label this result approximate and retain the
original pixels for later re-evaluation.

## Edge operations

- **Contract/expand:** signed subpixel distance in source pixels; morphology for
  integer preview, distance-field resampling for final.
- **Feather:** symmetric or inside/outside falloff with radius and curve.
- **Edge-aware smoothing:** guided/joint bilateral refinement using source luma and
  chroma; preserve hard high-contrast boundaries.
- **Hole cleanup:** fill only components under a configured area unless user marks
  intentional holes.
- **Component cleanup:** remove disconnected islands under area/confidence limits.
- **Edge contrast/density:** reshape alpha only in an explicit transition band.

All radii are source-pixel units and scale correctly in proxies.

## Spill and decontamination

The current RGB fringe cleanup becomes one mode. Add:

- sampled background-color suppression for green/blue/white spill;
- nearest reliable foreground-color propagation;
- hue/saturation spill neutralization with skin-tone protection;
- foreground color estimation for soft alpha;
- edge-only strength and transition width.

Never globally desaturate the subject. Keep alpha and RGB steps independent, show
a spill-only difference view, and test saturated clothing/hair against false color
removal.

## Inspection and quality control

Views: alpha grayscale, black, white, checkerboard, red overlay, edge band,
difference from original/model alpha, and contamination heatmap. Quality analyzers
report—not silently “fix”—halos, residual background chroma, isolated alpha pixels,
holes, stair-steps, and excessive transition width.

## Node split

Use separate nodes:

- `segment.background`
- `mask.protect_union`
- `matte.trimap`
- `alpha.morphology`
- `alpha.edge_smooth`
- `rgb.decontaminate`
- `quality.alpha_inspect`

This lets a user reorder or disable RGB cleanup without rerunning segmentation.

## Acceptance

- No-mask output is byte-identical to the segmentation path within declared codec
  tolerance.
- A 100% protect pixel yields alpha 255; soft protect uses `max`, not addition.
- Mask/source dimension mismatch is transformed explicitly or rejected.
- Hair/glass corpus improves boundary metrics without unacceptable opaque-subject
  regression.
- Transparent PNG round-trip preserves alpha and declared ICC.
- CPU path succeeds without CUDA.
