# Video processing pipeline, codecs, and export

## Media probe

Probe once per source fingerprint and record streams, codecs, time bases, PTS/DTS
behavior, frame-rate mode, duration, dimensions, SAR/DAR, rotation, pixel format,
color metadata, alpha, HDR metadata, audio layout/rate, and subtitle/data streams.
Do not infer these from file extension.

## Decode and proxy

- Decode frames with original PTS into typed buffers.
- Normalize rotation through an explicit transform.
- Build color-managed proxies and timeline thumbnails.
- Preserve source→proxy coordinate transforms.
- Keep proxy audio separate or use a synchronized low-bitrate copy.

## Chunk planner

Split at scene boundaries where possible. A temporal chunk contains:

- safe output PTS range;
- past/future context frames;
- provider state fingerprint;
- input graph/cache hashes;
- output frame/alpha hashes;
- validation metrics.

Only the safe center is published; context overlap is recomputed or verified on
resume. Recurrent model state is serialized only through a provider-defined,
versioned safe format—not pickle. If state cannot be safely serialized, resume from
the nearest prior anchor with context replay.

## Audio preservation

Image-only operations leave audio unaffected. Export:

1. encodes/muxes video to staging;
2. stream-copies compatible source audio when trim/timebase/container allow;
3. otherwise explicitly transcodes with a shown profile;
4. maps source PTS through trims/speed changes;
5. verifies A/V duration and sync before publish.

Never drop audio because the video path used a temporary silent file.

## Codec capability matrix

At runtime, probe the actual FFmpeg build and hardware encoders. Profiles cover:

| Output | Alpha | Typical purpose |
|---|---:|---|
| H.264 | no | broad SDR delivery |
| H.265/HEVC | profile-dependent; treat unavailable until probed | efficient delivery/HDR |
| AV1 | profile/container-dependent; validate | efficient modern delivery |
| WebM VP9/AV1 alpha | yes only with verified encoder/pixel format/container path | transparent delivery |
| ProRes 4444 | yes with validated pixel format | professional transparent intermediate |
| GIF | binary/limited transparency and palette limits | short previews |
| PNG/TIFF/EXR sequence | yes | lossless/interchange/checkpoint output |

The UI lists only working combinations of encoder, container, pixel format, alpha,
bit depth, color/HDR, audio, and hardware. It never promises alpha based solely on
a codec name.

## Hardware-aware selection

Choose software/hardware codec by probed support, alpha/HDR needs, quality target,
bit depth, resolution, and memory. Hardware encoders are optimizations, not required
for correctness. Show the resolved encoder and fallback before rendering.

## Transparent export

- Keep straight/premultiplied conversions explicit.
- Validate alpha variation with decoded sample frames.
- Preserve RGB under transparent pixels according to profile to avoid fringes.
- ProRes 4444 and WebM-alpha have separate golden round-trip fixtures.
- If the installed encoder cannot produce valid alpha, fail validation before the
  render rather than emit opaque output.

## Frame interpolation and slow motion

Scene-aware interpolation uses bidirectional flow, occlusion masks, cut resets, and
target PTS generation. Audio time stretching is a separate explicit operation.
Duplicates/cadence fallbacks remain available when a model is absent.

## Temporally consistent upscale

A video upscale provider consumes temporal context/flow and returns safe-center
frames. Chunk overlaps and scene resets prevent seam/flicker. Independent
Real-ESRGAN frames may remain a fast option but must be labeled frame-local.

## Final validation

Decode a sample plus first/last frames; validate stream presence, duration, frame
PTS monotonicity, dimensions, pixel format, alpha, color tags, audio sync, and
container readability. Publish atomically only after passing.
