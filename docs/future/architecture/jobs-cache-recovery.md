# Jobs, cache, performance, and cancellation

## Scheduler

Extend the current job phases with `PAUSED`, `CHECKPOINTING`, and `RESUMING`, while
keeping existing serialized values compatible. The scheduler owns a persistent
priority queue with:

- pause, resume, cancel, retry, and reorder;
- parent batch and child file/operation jobs;
- CPU/GPU/encoder resource reservations;
- per-project concurrency limits;
- structured progress, warnings, estimates, and failure actions.

Do not suspend a Python process to pause. Finish the smallest safe unit, commit its
checkpoint, release expensive resources, and transition to `PAUSED`.

## Work units

| Media/operation | Unit | Checkpoint |
|---|---|---|
| Local image operation | ROI or tile | artifact hash + safe-crop rectangle |
| Global image operation | full proxy/full image | output artifact hash |
| Frame-local video | frame chunk | first/last PTS + artifact hashes |
| Temporal video | scene chunk plus context | temporal state/version + safe output PTS |
| Export | encoded segment | mux manifest and encoder fingerprint |

Cancellation is cooperative and checked before model load, between tiles/frames,
between model stages, before encoding, and before output commit. Non-interruptible
provider calls are isolated; their results are discarded if cancellation wins.

## Preview vs final

`interactive`, `high_quality_preview`, and `final` are distinct render profiles.
They use separate cache namespaces and visible badges. Interactive rendering:

- debounces parameter changes (typically 80–150 ms);
- cancels superseded inference;
- renders viewport/ROI at proxy resolution;
- never promotes an approximate result into the final cache.

Final rendering starts from source-resolution assets and persisted graph state.

## Dirty rectangles and ROI

Mask paint produces a changed rectangle in source coordinates. The planner expands
it by the operation padding, downstream kernel radius, tile overlap, and transform
bounds. Only nodes declaring locality may use ROI. Seam validation compares an
overlap band against a reference full render.

The existing `mask_roi` helper is the initial primitive; future ROI data must also
carry affine transforms, mip level, frame/time range, and halo padding.

## Large-image tiling

- Estimate full-frame peak memory first.
- Choose tile dimensions from available RAM/VRAM minus a safety reserve.
- Align tile sizes to model stride.
- Include operation-declared overlap/context.
- Blend only the valid center using feathered or frequency-aware seams.
- Keep deterministic tile order and seeds.
- Fall back to CPU or smaller tiles before failing with an actionable estimate.

Global operations such as histogram-derived auto levels run a low-memory analysis
pass followed by tiled application where mathematically valid.

## Cache tiers

1. memory LRU for viewport tiles;
2. project-local durable preview/cache index;
3. optional shared model/artifact cache.

Entries are immutable and content-addressed. A SQLite index runs in WAL mode and
maps cache keys to blobs, descriptors, last access, size, and validation state.
Eviction never removes project sources, journals, candidates the user kept, or
published exports.

## Estimation and adaptive memory

Providers publish calibrated formulas using dimensions, frames, dtype, model,
tile/chunk size, device, and encoder. Before a job, show:

- predicted peak RAM/VRAM and disk workspace;
- estimated duration as a range, not false precision;
- chosen device/tile/chunk/codec;
- fallback and quality impact.

Measurements feed local rolling calibration without transmitting media or hardware
details. Out-of-memory retries reduce chunk/tile size once, optionally change
device, and never loop indefinitely.

## Worker health

- No unconditional idle polling loop.
- An active job may use bounded heartbeats tied to job timeout.
- IPC EOF/process exit triggers one crash event.
- Startup verifies only enabled/default capabilities; full diagnostics is manual.
- Repeated worker failure uses exponential restart limits and then reports a stable
  error rather than respawning forever.

## Output transaction

Workers write into a private staging workspace. The parent validates dimensions,
duration, frame count/PTS, alpha, color descriptor, and file readability. Only then
is the artifact atomically moved to its destination and the checkpoint committed.
