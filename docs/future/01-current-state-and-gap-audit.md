# Current-state and gap audit

This audit is based on the repository structure and current contracts, not on
feature names alone.

## Reusable foundations

| Area | Current evidence | Reuse decision |
|---|---|---|
| Job state | `backend/application/jobs.py` has typed phases and terminal states. | Extend with pause/checkpoints/estimates; preserve phase compatibility. |
| Worker IPC | `backend/tools/infer_protocol.py` has versioned commands, progress, cancel, results, errors, and previews. | Add typed capability payloads and protocol negotiation; do not replace at once. |
| Mask layers | `backend/media/mask_layers.py` has fill/protect layers, transforms, persistence, and ROI calculation. | Migrate to stable layer IDs, richer roles, blend algebra, tile-diff history, and project storage. |
| Protect behavior | Fill and protect masks are composed separately. | Keep protection as post-model alpha union; absence means untouched model output. |
| Edge cleanup | `backend/tools/cutout_edges.py` decontaminates RGB fringe while preserving alpha. | Promote to parameterized edge-refinement operations and add trimap/transparent recovery. |
| Temporary workspaces | `backend/media/workspace.py` creates private per-job directories and cleans owned stale workspaces. | Keep for ephemeral jobs; project recovery needs durable, project-scoped storage. |
| Model inventory | `backend/models/registry.py` records IDs, artifacts, memory, backends, and partial provenance. | Make this the capability/model-adapter registry; require license and hash gates. |
| Video I/O | `backend/tools/video_io.py` overlaps decode and inference and provides an FFmpeg writer. | Replace fixed H.264 assumptions with probed codec profiles, audio remux, chunks, alpha, and cancellation. |
| Existing tools | Background removal, enhancement, low-light, generation, SAM2/DINO selection, LaMa, STTN, ProPainter, OCR, subtitle workflows. | Wrap working paths as graph operations before adding new model families. |
| Hardware | Detector/profile/policy modules and CPU operation already exist. | Add predictive memory/codec policy; CPU remains valid, CUDA optional. |

## Important gaps

- No document-wide non-destructive operation graph or common render contract.
- Mask persistence is a standalone NumPy archive rather than a versioned project
  package with layer identity, roles, history, and safe migrations.
- No durable queue checkpoints, crash journal, proxy/full-resolution cache split,
  or dependency-aware cache invalidation.
- Video writing is currently fixed to an H.264 path and does not define audio,
  alpha, color, variable-frame-rate, or interrupted-render behavior.
- Alpha refinement covers one useful fringe cleanup but not trimaps, defringing by
  sampled color, matting, hair/fur, glass, or edge quality inspection.
- Model-backed features are not yet exposed through a uniform capability contract.
- No explicit 16-bit/float linear-light editor buffer contract.
- No single quality corpus for masks, restoration, retouch, color, compositing,
  temporal stability, and export correctness.

## Architecture decision

Build an editor kernel alongside existing pages. First wrap stable existing
operations, then migrate tools one vertical slice at a time:

```text
existing page → editor command → operation graph → render planner
              → existing/model adapter → validated artifact → project/cache
```

Legacy direct execution stays behind compatibility adapters until its corresponding
vertical slice meets parity tests. This avoids a big-bang rewrite and protects the
working CPU paths.

## Immediate cleanup constraints

- Do not reintroduce a permanent one-second watchdog. Worker liveness is checked
  while a job is active, on IPC failure, or on an explicit diagnostic action.
- Optional missing models remain warnings when their feature is disabled.
- Existing `.npz` masks are imported read-only, validated with
  `allow_pickle=False`, and converted to the project mask representation on save.
- Existing images/videos and outputs are never deleted during migration.
