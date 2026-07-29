# Color, restoration, and computational photography

## Color editing nodes

Implement RGB/per-channel curves, levels, exposure, contrast, gamma, black point,
HSL/HSV, LAB adjustments, selective color, gradient maps, three-way color wheels,
white balance, LUTs, and HDR tone mapping under the shared color contract.

Reference-grade matching analyzes exposure, white point, tone curve, palette, and
local regions, then creates normal adjustment nodes. Skin-tone protection is a
linked editable mask, not a hidden exception. Neutral-point white balance stores
the sampled source coordinate and resulting temperature/tint transform.

## Restoration pipeline

Each correction remains a separate node:

```text
scan/lens correction → dust/scratch/crease repair
→ denoise / JPEG / moiré removal → deblur
→ missing-region reconstruction → face restoration
→ faded-color recovery or colorization → grain reconstruction
```

Available capabilities cover:

- scratch, dust, crease, and film damage;
- old photograph and torn/missing corner reconstruction;
- identity-controlled face reconstruction;
- camera-shake, motion, and defocus deblur;
- JPEG blocking/ringing and moiré removal;
- separate chromatic and luminance noise;
- scanning pattern/paper texture and uneven illumination;
- editable monochrome colorization;
- faded color and contrast recovery;
- seeded film-grain reconstruction after denoise.

Model-backed repairs return masks/confidence and candidates where content is
invented. Deblur exposes strength and ringing suppression; warn when the estimated
kernel is unreliable.

## Computational photography

### Multi-input alignment

HDR merge, focus stacking, panorama, multi-frame denoise, and multi-frame
super-resolution share a registration service:

- read capture timestamps/exposure/focal metadata;
- detect and match features;
- estimate global transform, then optional local flow;
- expose rejected frames and alignment residual;
- keep manual control points and crop.

### HDR

Align exposures, estimate response if needed, deghost moving regions with editable
masks, produce a float HDR asset, and apply tone mapping separately.

### Focus stacking

Compute focus confidence per aligned frame, regularize the selection map, blend
across depth boundaries, and expose source-frame regions for correction.

### Panorama

Support cylindrical/spherical projection, seam selection, exposure compensation,
multiband blending, horizon adjustment, and content-aware crop.

### Multi-frame restoration

Temporal/spatial alignment drives denoise or super-resolution. Reject moving or
misaligned regions rather than hallucinating detail. Keep the chosen reference.

## Lens and geometry correction

Native calibrated nodes handle perspective/keystone, horizon level, lens profile
distortion, chromatic aberration, vignette, and rolling shutter. Profile absence is
explicit; manual coefficients remain available.

Depth-of-field simulation/refocus uses an editable depth map, portrait-depth repair,
synthetic aperture, and bokeh shape. It follows the edge-safe procedure in
[Compositing](compositing-relighting.md).

## Acceptance

- Zero-strength/identity color nodes preserve pixels within bit-depth tolerance.
- HDR input order does not change the registered result.
- Alignment reports failure instead of blending grossly mismatched inputs.
- Restoration difference views distinguish repaired and generated regions.
- Denoise/grain tests balance noise reduction, detail retention, and synthetic
  texture consistency.
- Lens correction round-trips coordinates for masks and retouch anchors.
