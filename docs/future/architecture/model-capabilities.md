# Model capability and provider contracts

## Why capability-first

Editor operations request `segment_object`, `matte_trimap`, `inpaint`,
`restore_face`, `estimate_depth`, `track_mask`, or another capability. They do not
import SAM2, LaMa, BiRefNet, ProPainter, or a framework directly. A registry chooses
an available provider based on quality profile, hardware, memory, license policy,
and installed artifacts.

## Provider descriptor

Each provider declares:

- stable provider/model/revision IDs and artifact hashes;
- capability and semantic version;
- accepted buffer/color/alpha descriptors;
- prompt/mask/trimap inputs and output schema;
- CPU/CUDA/DirectML/MPS support;
- minimum and estimated RAM/VRAM;
- proxy/tile/batch/temporal support;
- deterministic seed behavior;
- license, source, redistribution, and commercial-use status;
- offline/network behavior and data handling;
- quality tier and validated test corpus version.

Unknown provenance is not treated as approval. Such providers may be developer-only
until reviewed.

## Request/result

```text
CapabilityRequest
  request_id, capability, media descriptors
  prompts/selections/masks, parameters
  quality profile, deterministic seed
  cancellation token, resource budget

CapabilityResult
  artifacts with descriptors and hashes
  provider fingerprint, timing/resource metrics
  warnings, confidence/quality maps
  reproducibility record
```

Results are validated for finite values, dimensions, alpha range, duration/PTS,
declared color, and safe paths before entering cache or project state.

## Optional capabilities

Missing optional providers:

- do not break startup;
- disable only dependent controls with a clear reason;
- offer native/manual alternatives;
- can be installed through a deliberate model-management action;
- are re-probed after installation or hardware change, not every second.

## Candidate-producing operations

Generative fill, object removal, reconstruction, and expression edits return an
immutable candidate set. The graph stores prompt/control inputs and the chosen
candidate asset. Regeneration appends a set; it does not replace accepted history.

## Model upgrades

Opening a project pins the recorded provider fingerprint for reproducibility when
available. Upgrading is an explicit “re-render with…” action that creates a new
branch and difference preview. Cache keys include the fingerprint, so old and new
results cannot collide.
