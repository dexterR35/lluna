# Delivery roadmap and build sequence

This sequence honors the requested priority order while building reusable
foundations first. Each phase is independently releasable behind feature flags.

## Preserved requested priority sequences

The initial high-value order remains:

1. Alpha-edge refinement and spill removal.
2. Before/after comparison and alpha inspection.
3. Project saving and recovery.
4. Batch processing presets.
5. Temporally stable video background removal.
6. Keyframe mask tracking and transparent video export.

The requested advanced order remains:

1. Magnetic/semantic masking with positive and negative points.
2. Edge decontamination for hair and transparent objects.
3. Healing brush, clone stamp, and patch tool.
4. Adjustment layers and blend modes.
5. Frequency separation and dodge/burn.
6. Depth-aware relighting and background blur.
7. Color harmonization and contact shadows for composites.
8. 16-bit non-destructive operation graph.
9. Generative fill and outpainting with alternatives.
10. Project autosave, version snapshots, and crash recovery.

The engineering phases below add prerequisites without removing or changing those
product priorities.

## Phase 0 — Contracts and baseline

Deliver:

- feature inventory/status page in developer docs;
- typed media/color/alpha descriptors;
- operation/node and capability interfaces;
- current output golden corpus and performance baselines;
- event-driven worker health behavior with no idle polling loop.

Exit: existing tests pass, current CPU workflows are unchanged, and fixtures can
detect output regressions.

## Phase 1 — Alpha-edge refinement and spill removal

Vertical slice:

```text
source → existing background remove → protect union
→ contract/expand → guided edge → RGB decontaminate → PNG
```

Add edge inspector, parameter schemas, cache keys, and alpha golden tests. This is
the first requested priority.

## Phase 2 — Comparison and advanced masks

Deliver wipe/split/original/result/alpha/checkerboard/edge/100% views; stable mask
IDs and roles; brush/shape/lasso/polygon; algebra; tile history; range selections;
AI positive/negative points; proxy/ROI render cancellation.

## Phase 3 — Project save, autosave, and recovery

Deliver version-1 `.midgard`, current `.npz` mask import, atomic save, linked and
embedded assets, journal replay, recovery UI, compatibility/read-only behavior,
and no-data-loss fault injection.

## Phase 4 — Operation graph and batch presets

Wrap background removal, edge refine, Real-ESRGAN 2×, face enhancement provider,
and PNG export. Deliver the reference batch preset, per-file overrides, estimates,
pause/resume/cancel/reorder, and durable checkpoints.

## Phase 5 — Professional retouch and color

Recommended advanced order:

1. healing, clone, and patch;
2. adjustment layers and blend modes;
3. frequency separation and dodge/burn;
4. curves, levels, white balance, color wheels, LUTs;
5. selective sharpening and quality warnings;
6. face/skin candidates with visible masks and identity/detail controls;
7. liquify and face guides.

## Phase 6 — Temporally stable video background removal

Deliver timeline/proxies/scenes, frame-local baseline, audio-preserving opaque
export, then object tracking, temporal stabilization, flicker metrics, and selected
range preview.

## Phase 7 — Keyframe masks and transparent video

Deliver keyframe brush corrections, forward/backward tracking, mask interpolation,
resumable chunks, hardware-aware codec profiles, transparent WebM, ProRes 4444, and
image sequences. Add H.264/H.265/AV1/GIF profiles only where capability probing and
round-trip validation pass.

## Phase 8 — Compositing, restoration, and computational photography

Deliver layer compositor/smart objects, perspective paste, native blending, contact
shadows/light wrap/grain, restoration providers, lens correction, HDR/focus
stack/panorama, depth blur, and background harmonization. Depth relighting remains
experimental until quality gates pass.

## Phase 9 — Generative and specialized workflows

Deliver candidate infrastructure before generative fill/outpaint/object replace,
then product and portrait workflows, geometry, intelligent crop, marketplace/ID
guides, and model-governed advanced controls.

## Phase 10 — Temporal enhancement

Deliver scene-aware frame interpolation/slow motion and temporally consistent video
upscale with chunk seam and flicker benchmarks. Keep frame-local fallback labeled.

## Pull-request boundaries

Each vertical slice should be split into small reviewable PRs:

1. schema/contracts plus fixtures;
2. reference/native implementation;
3. worker/provider adapter;
4. project persistence/migration;
5. UI/controller;
6. cache/performance/cancellation;
7. export and end-to-end acceptance evidence.

A PR must not silently change defaults, install large models, or migrate user data.
Use the [implementation playbook](implementation-playbook.md) for each slice.

## Feature flags

Use stable capability flags, for example `editor_graph_v1`,
`alpha_refine_v1`, `project_package_v1`, `video_temporal_mask_v1`. A flag has an
owner, default per release channel, telemetry-free local diagnostic state, and
removal issue. Flags do not fork schemas; persisted data remains versioned.
