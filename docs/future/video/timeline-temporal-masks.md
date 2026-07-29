# Timeline, temporal masks, and video background removal

## Timeline data model

- Clip: source asset, in/out PTS, timeline start, speed, transform.
- Scene: start/end PTS, detector confidence, manual/automatic boundary.
- Mask track: stable subject ID, layer role, interpolation/provider settings.
- Keyframe: PTS, raster/vector correction, transform, confidence.
- Propagation segment: source keyframe(s), direction, model fingerprint, result
  chunk hashes, confidence.

Thumbnails and proxies are caches. Timeline edits and keyframes are project data.

## Scene detection

Use histogram/feature discontinuity plus optional learned detection. Never propagate
temporal state across a confirmed hard cut. Show suggested boundaries and allow
merge/split. Cache the detector/version/settings and results.

## True temporal background removal

For each scene:

1. segment one or more anchor frames;
2. establish stable object identity;
3. track/propagate masks forward and backward using flow and/or a video object
   segmentation capability;
4. incorporate user keyframe add/subtract/protect corrections;
5. interpolate corrections between keyframes;
6. refine with a temporal consistency window;
7. reset recurrent state at scene boundaries;
8. output alpha plus confidence/occlusion maps.

Temporal stabilization balances current-frame evidence and warped neighboring masks.
Occlusions and newly visible regions reduce historical weight. Do not blindly
average alpha, which produces trails.

## Keyframe correction semantics

A brush edit at time `t` is immutable keyframe data:

- add/remove/protect role;
- source coordinate raster tile diffs or vector path;
- propagation range and direction;
- falloff/interpolation policy;
- optional “hold until next keyframe.”

Forward/backward tracking produces a derived mask track. Manual keyframes always
win at their exact PTS. Conflicting propagated edits resolve by confidence and
explicit layer algebra, not last-writer accident.

## Interpolation

Native interpolation supports hold and linear signed-distance interpolation for
nearby compatible masks. Tracked interpolation warps endpoints using bidirectional
flow, tests forward/backward consistency, handles occlusion, and blends signed
distance/confidence. Surface low-confidence regions for correction.

## Flicker metrics

Evaluate:

- warped alpha temporal error outside occlusions;
- boundary position jitter;
- component birth/death instability;
- alpha pumping on semi-transparent edges;
- color spill variation after compositing;
- user-rated error around hair, hands, and fast motion.

Compare against the per-frame baseline and require no unacceptable spatial quality
regression.

## Player and preview

The player decodes original and processed proxies on a shared clock. Modes include
side-by-side, wipe, alpha, checkerboard, and overlay. Selected-range preview renders
only the marked PTS interval plus required temporal context; UI clearly marks
context frames as non-export range.

Scrubbing cancels stale frame requests. A small frame cache is keyed by revision,
PTS, view mode, proxy profile, and color transform.

## Acceptance

- Keyframes land on exact source PTS for constant and variable frame-rate fixtures.
- Hard cuts reset tracking and recurrent state.
- Forward/backward propagation is cancellable and chunk-resumable.
- Manual correction is exact at its keyframe and stable after reopen.
- Temporal metrics improve over independent-frame segmentation.
- Protect masks keep painted subject alpha; absent masks preserve normal removal.
