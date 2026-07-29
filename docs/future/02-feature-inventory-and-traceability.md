# Complete feature inventory and traceability

This is the loss-prevention checklist for the requested roadmap. Every requested
capability appears here and maps to an implementation document. IDs are permanent;
removed ideas are marked rejected with rationale rather than deleted.

## Core masking and interaction

| ID | Capability | Status | Design |
|---|---|---|---|
| MASK-001 | Multiple independent mask regions or layers | foundation | [Masking](image/masking-selection.md) |
| MASK-002 | Add, subtract, protect, erase, invert, and clear mask modes | foundation | [Masking](image/masking-selection.md) |
| MASK-003 | Brush, rectangle, lasso, polygon, and AI object-selection tools | foundation | [Masking](image/masking-selection.md) |
| MASK-004 | Feather, smoothing, expand/shrink, and edge-aware refinement | foundation | [Masking](image/masking-selection.md) |
| MASK-005 | Adjustable brush size, hardness, opacity, and spacing | foundation | [Masking](image/masking-selection.md) |
| MASK-006 | Separate mask-history snapshots with better undo/redo | foundation | [Operation graph](architecture/operation-graph.md) |
| MASK-007 | Fast low-resolution previews, then full-resolution processing | planned-native | [Jobs/cache](architecture/jobs-cache-recovery.md) |
| MASK-008 | Process only the changed bounding region | foundation | [Jobs/cache](architecture/jobs-cache-recovery.md) |
| MASK-009 | Debounced canvas redraw and cancellable background inference | foundation | [Jobs/cache](architecture/jobs-cache-recovery.md) |
| MASK-010 | Save/load masks and optional PNG export | foundation | [Project format](architecture/project-format.md) |
| MASK-011 | Protect selection survives background removal; no mask means normal removal | current | [Alpha/matting](image/alpha-matting.md) |
| MASK-012 | Trimap foreground/background/unknown regions | planned-native | [Alpha/matting](image/alpha-matting.md) |
| MASK-013 | Hair, fur, glass, smoke, motion-blur, and translucent-object matting | planned-model | [Alpha/matting](image/alpha-matting.md) |
| MASK-014 | Positive and negative AI selection points | planned-model | [Masking](image/masking-selection.md) |
| MASK-015 | Select similar by color, texture, or semantic meaning | planned-model | [Masking](image/masking-selection.md) |
| MASK-016 | Semantic select: sky, skin, hair, face, clothes, foreground, background, individual objects | planned-model | [Masking](image/masking-selection.md) |
| MASK-017 | Edge-snapping polygon/lasso and magnetic lasso | planned-native | [Masking](image/masking-selection.md) |
| MASK-018 | Color-, luminosity-, and depth-range masks | planned-model | [Masking](image/masking-selection.md) |
| MASK-019 | Intersection, union, difference, and exclusive-or | planned-native | [Masking](image/masking-selection.md) |
| MASK-020 | Parent/child groups and mask-linked adjustment layers | planned-native | [Operation graph](architecture/operation-graph.md) |
| MASK-021 | Density and edge-contrast controls | planned-native | [Masking](image/masking-selection.md) |
| MASK-022 | Hole removal and disconnected-region cleanup | planned-native | [Masking](image/masking-selection.md) |
| MASK-023 | Black, white, checkerboard, red-overlay, and difference edge views | planned-native | [Alpha/matting](image/alpha-matting.md) |

## Alpha, comparison, project, and batch

| ID | Capability | Status | Design |
|---|---|---|---|
| ALPHA-001 | White/green spill removal and edge decontamination | foundation | [Alpha/matting](image/alpha-matting.md) |
| ALPHA-002 | Hair/fur refinement; contract/expand; feather; edge-aware smoothing | foundation | [Alpha/matting](image/alpha-matting.md) |
| ALPHA-003 | Recover semi-transparent glass and veils | research | [Alpha/matting](image/alpha-matting.md) |
| VIEW-001 | Draggable slider, split, original/result toggle | current | [Image editor](image/README.md) |
| VIEW-002 | Alpha-only, checkerboard, edge inspection, 100% pixel inspection | current | [Alpha/matting](image/alpha-matting.md) |
| PROJ-001 | Editable project with source media, mask layers, retouch history, model/settings, crop/selections, previews | planned-native | [Project format](architecture/project-format.md) |
| BATCH-001 | Reusable pipelines and presets with per-file overrides | planned-native | [Operation graph](architecture/operation-graph.md) |
| BATCH-002 | Resumable/reorderable queues | planned-native | [Jobs/cache](architecture/jobs-cache-recovery.md) |
| BATCH-003 | Example: remove background → refine edges → upscale 2× → enhance face → export PNG | planned-native | [Roadmap](delivery/roadmap.md) |

## Image improvement, compositing, and relighting

| ID | Capability | Status | Design |
|---|---|---|---|
| IMG-001 | Automatic subject shadow/contact shadow generation | planned-model | [Compositing](image/compositing-relighting.md) |
| IMG-002 | Background replacement with perspective/color matching | planned-model | [Compositing](image/compositing-relighting.md) |
| IMG-003 | Subject relighting to match a new background | research | [Compositing](image/compositing-relighting.md) |
| IMG-004 | Face restoration with skin-detail preservation | planned-model | [Retouch](image/retouching.md) |
| IMG-005 | Noise, JPEG artifact, and motion-blur removal | planned-model | [Restoration/color](image/color-restoration-computational.md) |
| IMG-006 | Selective masked upscale | planned-native | [Operation graph](architecture/operation-graph.md) |
| IMG-007 | Content-aware crop and automatic composition | planned-model | [Advanced image](image/advanced-domains.md) |
| IMG-008 | Object removal with multiple generated alternatives | planned-model | [Retouch](image/retouching.md) |
| IMG-009 | White balance, curves, levels, color correction, LUTs | planned-native | [Restoration/color](image/color-restoration-computational.md) |
| IMG-010 | Preserve ICC, DPI, EXIF orientation, and configurable metadata | planned-native | [Color/metadata](architecture/color-metadata-precision.md) |

## Professional retouching

| ID | Capability | Status |
|---|---|---|
| RET-001 | Healing brush with automatic nearby texture sampling | planned-native |
| RET-002 | Clone stamp: aligned, fixed, mirrored, rotating source | planned-native |
| RET-003 | Patch tool replacing one selected region from another | planned-native |
| RET-004 | Content-aware object removal with candidate results | planned-model |
| RET-005 | Frequency separation for independent texture/color correction | planned-native |
| RET-006 | Dodge/burn layers with shadow, midtone, highlight control | planned-native |
| RET-007 | Texture-preserving skin smoothing | planned-model |
| RET-008 | Blemish, acne, wrinkle, and under-eye detection | planned-model |
| RET-009 | Stray-hair and flyaway removal | planned-model |
| RET-010 | Natural-strength teeth and eye enhancement | planned-model |
| RET-011 | Skin-tone unification that preserves pores | planned-model |
| RET-012 | Selective sharpening for eyes, hair, fabric, product details | planned-native |
| RET-013 | Liquify push, pull, pinch, expand, reconstruct, face-aware adjustments | planned-native |
| RET-014 | Symmetry and facial proportion guides | planned-native |
| RET-015 | Non-destructive retouch layers with adjustable strength | planned-native |

All `RET-*` logic and acceptance requirements are in
[Professional retouching](image/retouching.md).

## Compositing and relighting

| ID | Capability | Status |
|---|---|---|
| COMP-001 | Multi-image layer stack, groups, blend modes, clipping masks, adjustment layers | planned-native |
| COMP-002 | Smart objects preserving original resolution | planned-native |
| COMP-003 | Perspective-aware paste and automatic scale/perspective match | planned-model |
| COMP-004 | Poisson and multiband blending; color/exposure harmonization | planned-native |
| COMP-005 | Depth-matched background blur and depth ordering | planned-model |
| COMP-006 | Contact and directional cast shadows with softness/opacity | planned-model |
| COMP-007 | Product/floor reflections | planned-model |
| COMP-008 | Edge light-wrap | planned-native |
| COMP-009 | Atmospheric perspective, fog, and haze | planned-native |
| COMP-010 | Grain, lens-blur, and bokeh matching | planned-model |
| LIGHT-001 | Estimate depth, normals, and material properties | research |
| LIGHT-002 | Movable virtual light; key, fill, rim, background lights | research |
| LIGHT-003 | Light temperature/color; softbox, ring, window simulation | research |
| LIGHT-004 | Recover harsh facial shadows and correct mixed lighting | planned-model |
| LIGHT-005 | Match replacement-background lighting and relight selected objects | research |
| LIGHT-006 | Separate albedo/illumination and generate depth shadow maps | research |

All `COMP-*` and `LIGHT-*` logic is in
[Compositing and relighting](image/compositing-relighting.md).

## Color, restoration, and computational photography

| ID | Capability | Status |
|---|---|---|
| COLOR-001 | RGB/channel curves; levels, exposure, contrast, gamma, black point | planned-native |
| COLOR-002 | HSL/HSV, LAB, selective replacement, gradient maps | planned-native |
| COLOR-003 | Three-way color wheels; LUT import/export/intensity | planned-native |
| COLOR-004 | Reference color-grade matching | planned-model |
| COLOR-005 | Auto white balance plus neutral-point selection | planned-native |
| COLOR-006 | Skin-tone protection during global grading | planned-native |
| COLOR-007 | Gamut warnings, soft proofing, ICC preservation/conversion | planned-native |
| COLOR-008 | 16-bit/float processing, linear-light blending, HDR local tone map | planned-native |
| REST-001 | Scratch, dust, crease, film-damage removal | planned-model |
| REST-002 | Old-photo reconstruction; identity-controlled face reconstruction | planned-model |
| REST-003 | Motion/camera-shake/defocus deblur | planned-model |
| REST-004 | JPEG/block, moiré, chroma/luma noise removal | planned-model |
| REST-005 | Film-grain reconstruction after denoise | planned-native |
| REST-006 | Editable monochrome colorization and faded-color restoration | planned-model |
| REST-007 | Scan pattern/paper removal, torn regions/corners, uneven illumination | planned-model |
| PHOTO-001 | HDR merge, focus stack, panorama stitch | planned-native |
| PHOTO-002 | Multi-frame denoise and multi-frame super-resolution | research |
| PHOTO-003 | Perspective/keystone, horizon, lens distortion, CA, vignette correction | planned-native |
| PHOTO-004 | Rolling-shutter correction | planned-native |
| PHOTO-005 | Depth-of-field simulation, refocus, portrait-depth correction | planned-model |
| PHOTO-006 | Synthetic aperture and configurable bokeh shapes | planned-model |

See [Color, restoration, and computational photography](image/color-restoration-computational.md)
and [Color/metadata](architecture/color-metadata-precision.md).

## Generative, product, portrait, and geometry

| ID | Capability | Status |
|---|---|---|
| GEN-001 | Generative fill/outpaint with multiple candidates | planned-model |
| GEN-002 | Object replace preserving position/light; clothing/material/color/texture edits | planned-model |
| GEN-003 | Controlled backgrounds; reconstruct cropped subjects | planned-model |
| GEN-004 | Structure/style/sketch/depth/edge/pose-guided edits with strength | planned-model |
| GEN-005 | Consistent identity across images; expression alternatives | research |
| GEN-006 | Text replacement with surface reconstruction | planned-model |
| GEN-007 | Seamless textures/patterns and seam-free tiled high-resolution generation | planned-model |
| PROD-001 | Translucent product cutout, studio presets, ground/contact shadow, reflections | planned-model |
| PROD-002 | Fingerprint/dust/scratch/label cleanup | planned-model |
| PROD-003 | Product recolor preserving material; perspective-warped label replacement | planned-model |
| PROD-004 | Marketplace ratios, batch framing, background compliance, margins/coverage | planned-native |
| PROD-005 | 360° presentation frames from supplied views | research |
| PROD-006 | Detect and preserve logos and printed text | planned-model |
| PORT-001 | Face-part masks: skin, lips, teeth, eyes, brows, hair, facial hair | planned-model |
| PORT-002 | Pore-preserving retouch, makeup, strand-preserving hair recolor | planned-model |
| PORT-003 | Portrait background lighting, catchlights, glare/red-eye correction | planned-model |
| PORT-004 | Expression/gaze, portrait relight, depth-aware background | research |
| PORT-005 | Clothing cleanup/wrinkle reduction | planned-model |
| PORT-006 | ID/passport compliance guides | planned-native |
| PORT-007 | Group-face selection with independent settings | planned-model |
| GEO-001 | Perspective/mesh warp and puppet pins | planned-native |
| GEO-002 | Content-aware scale and seam carving | planned-native |
| GEO-003 | Curved-document, cylindrical, and spherical warps | planned-native |
| GEO-004 | Object alignment and cross-image size/position matching | planned-native |
| GEO-005 | Symmetry, kaleidoscope, repeat patterns, seamless textures | planned-native |
| GEO-006 | Intelligent crop using faces, subjects, text, and composition | planned-model |

See [Advanced image domains](image/advanced-domains.md).

## Video

| ID | Capability | Status |
|---|---|---|
| VID-001 | True video background removal with object tracking | planned-model |
| VID-002 | Temporally stable masks that prevent flicker | planned-model |
| VID-003 | Keyframe corrections and mask interpolation | planned-native |
| VID-004 | Preserve original audio | planned-native |
| VID-005 | Transparent WebM and ProRes 4444 export | planned-native |
| VID-006 | Timeline with frame thumbnails | planned-native |
| VID-007 | Brush correction on keyframes; track masks forward/backward | planned-model |
| VID-008 | Scene detection before processing | planned-native |
| VID-009 | Selected time-range preview | planned-native |
| VID-010 | Resume interrupted render from last completed chunk | planned-native |
| VID-011 | Hardware-aware codec selection | planned-native |
| VID-012 | H.264, H.265, AV1, WebM-alpha, GIF, image-sequence export | planned-native |
| VID-013 | Side-by-side original/processed playback | planned-native |
| VID-014 | Frame interpolation and slow motion | planned-model |
| VID-015 | Temporally consistent video upscale | planned-model |

See [Video architecture](video/README.md),
[Temporal masks](video/timeline-temporal-masks.md), and
[Pipeline/export](video/pipeline-codecs-export.md).

## Engine, reliability, and quality control

| ID | Capability | Status |
|---|---|---|
| ENG-001 | Editable/reorderable/toggleable/strength-adjustable operation graph | planned-native |
| ENG-002 | Smart previews, intermediate cache, per-operation masks/parameters/presets | planned-native |
| ENG-003 | Copy/paste adjustments, branching versions, before/after snapshots | planned-native |
| ENG-004 | Autosave, crash recovery, background render, proxy edit/full export | planned-native |
| PERF-001 | Automatic overlap-aware large-image tiling | planned-native |
| PERF-002 | ROI processing for every eligible masked operation | foundation |
| PERF-003 | Separate proxy and full-resolution caches | planned-native |
| PERF-004 | Adaptive CPU/GPU memory limits and time/memory estimates | planned-native |
| PERF-005 | Pause, resume, cancel, reorder jobs | planned-native |
| PERF-006 | Crash recovery and resumable projects | planned-native |
| QC-001 | Golden-image alpha-edge and color-preservation tests | planned-native |
| QC-002 | Halo/background-contamination detection | planned-native |
| QC-003 | Oversharpening/ringing, clipping, banding, over-smoothed skin detection | planned-native |
| QC-004 | Difference maps, alpha holes, isolated pixels | planned-native |
| QC-005 | Low-resolution warning and print-quality-at-DPI estimate | planned-native |
| QC-006 | Marketplace requirement checks | planned-native |
| QC-007 | Exact processing/model/settings history | planned-native |

See [Operation graph](architecture/operation-graph.md),
[Jobs/cache](architecture/jobs-cache-recovery.md), and
[Testing](delivery/testing-quality-gates.md).
