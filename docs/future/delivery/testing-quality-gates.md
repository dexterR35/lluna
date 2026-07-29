# Testing and quality gates

## Test layers

1. Pure unit tests for commands, schemas, graph validation, mask algebra, cache
   keys, color math, transforms, estimates, and timebase math.
2. Property tests for undo/redo, graph serialization, mask algebra identities,
   coordinate round trips, tile equivalence, and migration idempotence.
3. Provider contract tests using tiny fake providers on CPU.
4. Golden image/video tests for visible quality and preservation.
5. Integration tests for worker cancellation/crash, save/recovery, cache eviction,
   FFmpeg profiles, and missing models.
6. UI interaction tests for viewport alignment, stale-result rejection, history,
   timeline PTS, and disabled-capability behavior.
7. Soak/fault tests for large assets, long queues, disk full, OOM, process death,
   corrupted cache/project entries, and interrupted export.

## Golden corpus

Version a legally usable compact corpus with:

- solid, hair, fur, glass, veil, smoke, motion blur, and colored spill edges;
- dark/light/saturated subjects and holes/disconnected components;
- skin detail, eyes, hair, fabrics, product text/logos, and fine patterns;
- noise, JPEG, moiré, blur, scratches, scans, and faded photos;
- ICC profiles, gradients, HDR/SDR, premultiplied/straight alpha;
- constant/variable frame rate, cuts, occlusion, fast motion, transparent video,
  multichannel audio, and non-square pixels.

Store expected output or metric ranges, input licenses, provenance, and why each
fixture exists. Large/private evaluation sets may live outside Git but must be
version-addressed.

## Metrics

| Domain | Measures |
|---|---|
| Alpha | IoU/F-score, boundary F-score, SAD/MSE, gradient/connectivity, halo/spill heuristics |
| Retouch/restoration | masked LPIPS/SSIM/PSNR where meaningful, identity similarity, pore/detail spectrum, ringing |
| Color | Delta E, grayscale neutrality, clipping, gamut, gradient banding |
| Composite | edge/color mismatch, shadow contact, text/logo preservation, human review |
| Video mask | flow-warped alpha error, boundary jitter, component stability, flicker |
| Video/export | PTS monotonicity, A/V sync, duration, alpha/color round trip |
| Performance | input latency, preview first-result, final throughput, peak RAM/VRAM/disk |

Metrics inform gates but do not replace side-by-side human review for generative,
portrait, relighting, and perceptual composite quality.

## Required invariants

- No protect mask produces the normal background-removal result.
- Protect alpha uses union/max and never reduces model alpha.
- Source and prior project data remain unchanged.
- Undo→redo restores exact document/mask hashes.
- Proxy results never enter final cache.
- Full render and tiled/ROI render match within declared seam/numeric tolerance.
- CPU works for every capability declared CPU-compatible.
- Missing optional model/codec disables only its dependent feature.
- Cancelled or failed work never publishes a partial final output.
- Reopened projects preserve unknown nodes and assets.

## Performance targets

Targets are recorded per representative hardware tier, not one universal number:

- paint feedback p95 ≤ 16 ms after input sample;
- ordinary UI action response p95 ≤ 100 ms;
- superseded preview stops producing accepted tiles within 250 ms where provider
  cancellation boundaries permit;
- no unbounded RAM growth in a 30-minute paint/edit soak;
- project recovery replays a bounded journal with progress and cancellation.

Final inference throughput has regression budgets based on the baseline and quality
profile.

## Export gates

For every shown export profile:

- encoder/container/pixel format was probed;
- output reopens and decodes;
- expected streams exist;
- dimensions/duration/timebase are valid;
- A/V sync is within the declared tolerance;
- alpha/color/bit depth round trips meet profile tolerance;
- interrupted render resumes or cleanly restarts without corrupt publish.

## Quality review record

Each feature release records corpus version, model/provider fingerprints, hardware
matrix, metric comparison, human-review signoff, known failures, and rollback flag.
