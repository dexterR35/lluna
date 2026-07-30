# Stage 07A — Model Settings and Preset Architecture

**Audit date:** 2026-07-27  
**Scope:** all model-facing configuration, tool controls, job snapshots, worker
normalization, memory recommendations, and model-specific hardcoded behavior.  
**Constraint:** audit and design only; no production code was changed.

## Executive assessment

Midgard exposes a small subset of its actual inference controls. The visible
controls are mostly model selectors, three square generation sizes, three step
presets, one upscale denoise switch, one Select Object quality switch, and
low-level subtitle sliders. Many consequential values—generation guidance,
precision and offload; rembg thresholds; tile sizes; low-light resolution;
selection thresholds; output codecs and quality—are hardcoded in runners.

Two partial recommendation mechanisms exist:

- `soft_defaults.py` changes STTN/ProPainter frame counts once from total VRAM;
- `vram_budget.py` chooses or clamps tiles/frame counts immediately before work.

Neither produces a durable recommendation object or shows the user configured,
recommended, and effective values. The video budget can reduce a requested
frame count and only write a worker log. Settings also mix unrelated models in
one global Qt-coupled `Config` class.

The target is a typed, model-specific settings system with four layers of
meaning:

```text
default != recommended != configured != effective
```

A fifth, `safety_clamped_from`, records any forced change. Presets should be
computed recommendations, not bags of constants.

## Current settings inventory

Legend: **UI** exposed to ordinary users; **Settings** exposed on the current
Settings page; **Runtime** accepted by worker/runner but not exposed; **HC**
hardcoded; **Missing** unsupported end to end.

### Image generation

| Setting | Current state | Validation/effective behavior | Finding |
|---|---|---|---|
| Model | UI and Settings expose FLUX.2 Klein, FLUX.2 Dev, Klein FP8, and Qwen-Image | Enum validation in config; UI substitutes an installed and enabled model | All supported choices are available on Home once installed and enabled |
| Width/height | UI: linked square 512, 768, 1024 presets | Plain `ConfigItem`; runner floors to multiples of 16 and minimum 64 | No aspect ratio/custom dimensions; silent normalization |
| Aspect ratio | Missing | — | Add task-level ratio presets and custom mode |
| Inference steps | UI: Fast/Normal/Quality from model catalog | Plain integer config; runner enforces only `>=1` | No upper safety limit; changing model chooses nearest preset rather than preserving semantic quality |
| Guidance scale | HC per model catalog (`1.0`, `0.0`, `7.5`) | Float payload; no range validation | Advanced model-specific setting |
| Seed | Runtime accepts optional integer | UI never sends it | Add Advanced field with “Random” default and reveal used seed in result metadata |
| Negative prompt | Missing | Runner does not accept it | Add only for pipelines that support it |
| Scheduler | Missing/HC pipeline default | Not cataloged | Expert, model-compatible choices only |
| Precision | HC: BF16 if CUDA reports support, otherwise FP16 | Not user visible; no per-model compatibility | Expert override; Auto in Simple/Advanced |
| CPU offload | HC enabled, exceptions suppressed | No setting or observed result | Advanced memory strategy; Auto default |
| Attention slicing | Missing | — | Expert, only where pipeline supports it |
| Model caching | HC single cached generation model | No user control | Expert cache policy, not a casual toggle |
| Output format | HC PNG | No UI | Advanced PNG/JPEG/WebP where safe |
| Output quality | HC/irrelevant for PNG | No UI | Show only for lossy formats |
| Safety constraints | SD 1.5 explicitly loads with `safety_checker=None`; others use pipeline defaults | No disclosure or policy | Critical missing product policy; must be explicit and model-specific |
| Memory mode | HC CPU offload + one-entry cache | No UI | Simple preset controls; Advanced strategy |

### Subtitle and text removal

| Setting | Current state | Validation/effective behavior | Finding |
|---|---|---|---|
| Inpainting model | UI combo: STTN Auto, STTN Detection, LaMa, ProPainter, OpenCV | Enum; static images temporarily force LaMa and restore the previous mode | Per-media compatibility is implicit and mode substitution is not clearly explained |
| Detection model | UI combo: PaddleOCR server/mobile | Enum | Good basic control; label “Precise/Fast” is more user-friendly |
| Detection sensitivity | Missing as one semantic control | Seven pixel thresholds exposed separately in Settings | Ordinary users face implementation details instead of a meaningful sensitivity preset |
| Mask expansion | Settings: `subtitleAreaDeviationPixel` 1–300 px | Range only; no resolution scaling | Should be relative to input resolution, with px available in Expert |
| Timeline expansion | Settings: backward/forward 0–300 frames | Range only | Unsafe at high FPS/long values; present seconds/frames context |
| Reference frames | Settings: STTN 1–100 | Range only | Advanced; must validate with stride/load count |
| Neighbor stride | Settings: STTN 1–100 | Range only | Advanced, model-only |
| Batch/frame-load count | Settings: STTN 1–300 and ProPainter 1–300 | Runtime may reduce by VRAM; `getSttnMaxLoadNum()` can increase effective value to stride × references | Cross-field behavior is surprising; user request can be silently overridden both upward and downward |
| Scene splitting | HC precise path uses scene cuts | No setting | Advanced Auto/On/Off with model/video compatibility |
| Preview quality | HC full resolution (`previewMaxSide=0`) | UI-only constant, not persisted | Advanced UI preference, not model setting |
| Output codec | HC FFmpeg `libx264`; audio copied | No setting or capability validation | Advanced output profile |
| Output quality | FFmpeg defaults/implementation constants | No user setting | Add semantic video quality, resolve to CRF/preset |
| Processing area | Per-task selection rectangles; global serialized default | Weak string validation | Per-job state should not be a global model setting |
| A/B sections | Per task | UI shortcuts and task options | Correctly task-scoped, but discoverability is weak |

Current OCR settings named “Height-Width Pixel Difference Threshold,” “Y-axis
Pixel Tolerance,” and similar are Expert controls. They have descriptions and
risk badges, but remain too technical for the default Settings view.

### Background removal

| Setting | Current state | Finding |
|---|---|---|
| Model | UI installed/enabled model combo | Keep in Advanced; Simple should show task intent/quality |
| Alpha matting | Missing | rembg invocation does not enable it |
| Foreground/background thresholds | Missing | No runner parameters |
| Erosion size | Missing | No runner parameter |
| Edge refinement | Missing | Retouch tools exist after inference, but no automatic refinement policy |
| Output transparency | HC transparent PNG | Expose output background: transparent/color/image in Advanced |
| Mask cleanup | Missing beyond manual protect/retouch | Add model-compatible cleanup options |
| Model cache | HC sessions cached per model/provider until modality switch | Expert |
| Maximum resolution | HC `0` (unlimited) | Safety policy needed for RAM/ORT |
| Protect mask | UI Automatic/Protect + editor | Task-specific, not global; valuable workflow |

### Upscaling

| Setting | Current state | Finding |
|---|---|---|
| Model/scale | UI x2/x4 model combo | Model and scale are conflated; acceptable while each model has one native scale |
| Tile size | HC recommendation 512/256/128/64; retries smaller on OOM | Good candidate for Auto + Expert override |
| Tile overlap/padding | HC padding 10 | Expert only |
| Denoise strength | UI only On/Off; config has enum but no strength control | Expose semantic Light/Standard/Strong in Advanced |
| Face enhancement | Missing | Do not show until a supported face model/pipeline exists |
| Output limit | `enhanceMaxLongEdge` exists, not exposed, plain config | Advanced “Maximum output size”; validate scale and disk/RAM |
| Precision | HC FP32-style path | Expert Auto/FP32/FP16 only after backend validation |
| Memory mode | Automatic tile selection only | Simple preset and Advanced Auto/Low-memory |
| Output format/quality | Save dialog PNG/JPEG; JPEG quality HC 95 | Advanced output policy; current save behavior is per action, not job |

### Low-light enhancement

| Setting | Current state | Finding |
|---|---|---|
| Model | UI, currently one MIRNet model | Hide selector when only one compatible choice |
| Strength | Missing | Requires algorithm support/blend design |
| Maximum processing resolution | Config `2048`, clamped 64–2048 by runner, not UI | Important missing disclosure: larger input is downscaled for inference then resized back |
| Color preservation | HC model result; alpha preserved | Add only if implementation supports a controlled blend/color method |
| Noise reduction | Missing | Do not imply MIRNet exposes it; could be a pipeline stage |
| Tile size | HC based on free CUDA VRAM; CPU modest | Auto in normal UI, Expert override |
| Tile overlap | HC 16 | Expert |
| Memory mode | HC one-model cache and tile choice | Simple/Advanced policy |
| Output format/quality | Save PNG or JPEG; quality HC 95 | Advanced output policy |

### Object selection

| Setting | Current state | Finding |
|---|---|---|
| SAM2/DINO model | Settings exposes pair cards and a “More complex” switch | Pair is the correct compatibility unit; individual model selectors would permit invalid pairs |
| Text confidence | Runtime HC default 0.25 | Advanced, bounded 0–1, text-mode only |
| Box confidence | Runtime HC default 0.25 | Advanced, bounded 0–1, text-mode only |
| Mask threshold | HC inside Transformers/model post-processing | Expert only if adapter supports it |
| Refinement | UI allows repeated “Add to mask” clicks and manual brush | Per-operation state; describe as “Add missed areas” |
| Fast vs quality | Settings “More complex” global switch | Move to task preset; do not globally alter all future dialogs without local visibility |

## Missing-settings inventory

Priority reflects user impact, not implementation ease.

| Priority | Missing control/policy |
|---|---|
| P0 | Generation safety policy/disclosure; output ownership; explicit safety clamp reporting |
| P0 | Typed output profiles for video/image, overwrite and partial-output policy |
| P0 | Per-task effective settings snapshot including model/backend/device |
| P1 | Simple presets for every tool; semantic subtitle sensitivity; Low Memory |
| P1 | Generation aspect ratio/custom size, seed, negative prompt where supported |
| P1 | Background alpha matting/refinement thresholds when supported |
| P1 | Subtitle video quality/codec profile and scene splitting |
| P1 | Upscale denoise strength and maximum output dimension |
| P1 | Low-light maximum working resolution disclosure |
| P1 | Object-selection box/text thresholds |
| P2 | Scheduler, precision, attention slicing, tile/overlap and cache controls |
| P2 | Face enhancement, low-light strength/noise/color controls only after pipelines support them |

## Unsafe or misleading settings

- STTN frame count has a nominal 1–300 range, but the effective getter can
  raise it to `neighbor_stride × reference_length`, potentially 10,000.
- ProPainter permits 300 frames despite comments showing 50–80 can require
  19–25 GB at modest resolutions.
- Generation width, height, and steps use unvalidated `ConfigItem`s.
- Generation dimensions are silently floored to a multiple of 16.
- Low-light silently processes above-limit images at a smaller resolution and
  scales the result back.
- `enhanceMaxLongEdge`, `lowLightMaxLongEdge`, watchdog, and idle-release values
  are plain config values and can be corrupted/out of range.
- “Hardware acceleration” is global even though features support different
  backends.
- Select Object quality is global rather than per job.
- enabled-model lists are comma-separated strings with only ad hoc filtering.
- generation's disabled safety checker is neither configurable nor disclosed.
- JPEG quality 95, PNG optimization, codec, and output naming differ by tool.

## What belongs at each level

### Simple — default

Per tool, show:

- preset: **Fast**, **Balanced**, **Quality**, **Low Memory**;
- input and output summary;
- task-meaningful choice only when required;
- output destination.

Do not show CUDA, ONNX, dtype, tile size, batch size, OCR pixel tolerances,
scheduler, cache, or worker timeouts.

### Advanced

- compatible model or model pair;
- generation size/aspect, steps, guidance, seed, negative prompt;
- subtitle detection mode, semantic sensitivity, mask/timeline expansion,
  reference strategy, frame batch;
- background matting/refinement;
- upscale scale/model, denoise strength, output limit;
- low-light working resolution and supported strength/color/noise controls;
- object selection thresholds;
- memory strategy (`Auto`, `Keep warm`, `Release after job`, `Low memory`);
- output profile.

Advanced controls should be conditional on the selected task/model. A control
must not appear disabled without an explanation.

### Expert — hidden by default

- backend/device override;
- precision/dtype;
- scheduler;
- raw pixel thresholds;
- exact tile size, overlap, padding;
- worker watchdog/idle timeout;
- cache entry/budget policy;
- framework-specific flags and diagnostic experiments.

Expert mode requires a warning that invalid combinations can fail. It should be
session-visible or a deliberate preference, not accidentally enabled by
opening Diagnostics.

## Model-specific schemas

All schemas share:

```text
schema_version
preset_id
model_id
output_policy
memory_policy
user_overrides
```

Each field metadata includes type, unit, bounds, compatible model/backend,
visibility level, restart scope (`none`, `worker`, `application`), description
key, default factory, recommendation function, and migration aliases.

### `GenerateSettings`

```text
model_id: enum
width, height: int [64..4096], multiple constraint from model
steps: int [model minimum..model maximum]
guidance_scale: float [model range]
seed: int64 | Random
negative_prompt: str | unsupported
scheduler: compatible enum | Auto
precision: Auto | FP32 | FP16 | BF16
cpu_offload: Auto | On | Off
attention_slicing: Auto | On | Off
cache_policy: Auto | KeepWarm | ReleaseAfterJob
safety_policy: required enum, never implicit
output_format: PNG | JPEG | WEBP
output_quality: int [1..100] when lossy
```

### `STTNSettings`

```text
mode: Auto | Detection
detection_model: Server | Mobile
sensitivity: Conservative | Balanced | Aggressive
mask_expansion: relative fraction plus derived pixels
timeline_before/after: duration or frames
neighbor_stride: int [1..model max]
reference_frames: int [1..model max]
concurrent_frames: Auto | bounded int
scene_splitting: Auto | On | Off
```

Cross-field rule: concurrent frames must be at least the algorithmic minimum
and at most the hardware-safe maximum. If no value satisfies both, the
configuration is incompatible rather than silently inflated.

### `ProPainterSettings`

```text
detection_model
sensitivity
mask/timeline expansion
concurrent_frames: Auto | bounded int
scene_splitting
precision: Auto | FP16 | FP32
```

### `LamaSettings`

```text
detection_model
sensitivity
mask_expansion
working_resolution: Auto | bounded dimensions
precision: Auto | FP32 | FP16 where verified
```

### `BackgroundRemovalSettings`

```text
model_id
alpha_matting: Auto | On | Off
foreground_threshold, background_threshold: float [0..1]
erosion_px: bounded int
edge_refinement: Off | Light | Strong
mask_cleanup: Off | Conservative | Standard
output_background: Transparent | Color | Image
max_working_resolution: Auto | bounded
cache_policy
```

Only emit matting fields to rembg sessions that support them.

### `UpscaleSettings`

```text
model_id / scale
denoise: Off | Light | Standard | Strong
tile_size: Auto | supported integer
tile_overlap: Auto | bounded integer < tile_size/2
max_output_long_edge: Auto | bounded
face_enhancement: unsupported until adapter exists
precision
memory_policy
```

### `LowLightSettings`

```text
model_id
strength: model-supported blend [0..1]
max_working_long_edge: Auto | bounded
color_preservation, noise_reduction: model-supported enums
tile_size, overlap
memory_policy
```

### `ObjectSelectionSettings`

```text
pair_id: fast | complex
text_confidence: float [0..1]
box_confidence: float [0..1]
mask_threshold: compatible float
refinement_mode: Replace | Add | Subtract
```

## Preset design

A preset is a goal with constraints:

```text
PresetIntent(
  id=BALANCED,
  quality_weight=0.55,
  latency_weight=0.35,
  memory_weight=0.10,
  allow_offload=True,
  allow_resolution_reduction=True,
  minimum_quality=...
)
```

Resolution considers task, model manifest, installation state, hardware
profile, live RAM/VRAM, input dimensions/frame rate/duration, backend, and user
overrides.

### Semantic behavior

| Preset | Resolution policy |
|---|---|
| Fast | Prefer installed light model; lower working resolution/steps/reference count; larger safe tiles only when they reduce latency; do not compromise output dimensions without disclosure |
| Balanced | Choose recommended installed compatible model; middle validated model parameters; retain output fidelity; conservative memory reserve |
| Quality | Offer only when a compatible installed model and resource envelope meet thresholds; higher steps/stronger pair/more context; never imply unsupported quality gains |
| Low Memory | Prefer lighter model/backend; offload; smaller tiles/batches/frame windows; one cache entry or release-after-job; may lower working resolution with explicit disclosure |

If the ideal model is not installed, return both:

- best immediately runnable recommendation; and
- optional better recommendation with download size/license.

Do not auto-download or silently switch models.

## Settings resolution algorithm

```text
Application defaults
  -> overlay model defaults for exact model version
  -> compute HardwareRecommendation(input, HardwareProfile, live memory)
  -> apply selected PresetIntent
  -> apply compatible user overrides
  -> validate types, ranges, units, cross-fields, model/backend support
  -> safety policy clamps only explicitly clampable fields
  -> return EffectiveSettings + ResolutionTrace
```

Illustrative result:

```text
ResolvedValue[int](
  default=50,
  recommended=24,
  configured=70,
  effective=24,
  safety_clamped_from=70,
  source="VRAM admission for 1920×1080 STTN",
  reason_code="insufficient_vram"
)
```

Algorithm requirements:

1. Reject unknown fields and invalid units.
2. Preserve the configured value; never overwrite it merely because one input
   is large.
3. Recompute recommendations when model, hardware, input, or installation
   state changes.
4. Clamp only fields whose schema declares safe degradation.
5. Fail incompatible combinations rather than inventing behavior.
6. Include an immutable effective snapshot in the job.
7. Store the resolution trace with job diagnostics and result metadata.

## Validation and application timing

| Category | Validation | Apply timing |
|---|---|---|
| Model/preset/task options | Before Run and again in worker | Next job immediately |
| UI/output preferences | On edit | Immediately |
| Cache/memory strategy | Validate leases | Next idle boundary or next job |
| Backend/device/precision | Hardware/model compatibility | Worker restart recommended |
| Worker timeouts | Positive bounded duration | Next job; worker restart if protocol requires |
| Model root/framework environment | Filesystem/process validation | Application restart |

No current model setting intrinsically needs full application restart except
process-wide framework/environment changes. The UI must state exact scope.

## Hardware-aware recommendations

- Use immutable hardware capability plus a fresh memory sample.
- Reserve OS/UI/encoding memory and output buffers.
- Treat CUDA VRAM, DirectML budget, MPS unified memory, and CPU RAM differently.
- Use model manifest requirements and calibrated peak telemetry, not GPU-name
  lists.
- Include input megapixels, frame rate, frame window, scale factor, and output
  dimensions.
- Prefer Auto tile/batch; calculate exact effective value at job admission.
- Quality is unavailable—not merely disabled—when the model is missing,
  licensed access is incomplete, or the hardware envelope cannot meet it.
- Recalculate after OOM and record the retry change once; do not loop.

## User-facing diagnostics

Any clamp or substitution produces a persistent preflight summary:

```text
Concurrent frames adjusted

Configured value: 70 frames
Recommended value: 24 frames
Effective value: 24 frames

Reason:
Your available GPU memory is not sufficient for 70 frames at 1920 × 1080.

[Use 24 for this job] [Switch to Low Memory] [Cancel]
```

For harmless alignment such as 769 → 768 pixels, show the effective size in
the output preview before Run. Never rely on worker logs as the only notice.

## UI presentation

- Put a four-choice preset control at the top of each tool settings panel.
- Under it, show a one-line outcome: model, expected working resolution,
  backend, and memory mode.
- “Customize” expands Advanced; “Expert controls” is a separate hidden switch.
- Show a reset affordance for the current tool/model, not one giant settings
  page containing every model.
- Mark overridden fields and provide “Use recommended.”
- Use plain labels: “Frames processed together,” not `MaxLoadNum`; “Text
  detection sensitivity,” not pixel-axis tolerance.
- Keep installation/enablement in Models, operational choices in each tool.
- Display units beside every number.

## Configuration migration

1. Introduce versioned model-specific schemas and a read-only compatibility
   facade over current `backend.config`.
2. Map current fields:
   `generate* -> GenerateSettings`, STTN/ProPainter fields to their schemas,
   model selections/enabled lists to model policy, and output directory to
   application output policy.
3. Preserve every legacy configured value as an explicit user override.
4. Translate `selectObjectMoreComplex` to `pair_id=complex`.
5. Convert pixel/frame settings without changing semantics; mark them legacy
   Expert overrides until the user selects a semantic preset.
6. Keep old keys for one release as read-only migration aliases.
7. Write new files atomically with schema version and migration receipt.
8. Workers receive immutable serialized effective settings, never live Qt
   configuration.

## Testing requirements

- Table-driven schema tests for type, range, unit, compatibility, and
  cross-field constraints.
- Golden preset tests across mocked CPU, CUDA 4/8/12/24 GB, DirectML, and MPS
  profiles plus varying RAM/disk.
- Inputs: small/4K/8K image; 480p/1080p/4K video; multiple FPS/durations.
- Assert all five values: default, recommended, configured, effective, clamp.
- Property tests ensuring effective values always satisfy model invariants.
- Migration tests for missing, corrupt, old, and partially customized config.
- Worker round-trip tests proving the GUI snapshot is exactly what executes.
- OOM tests proving at most one disclosed degradation/retry.
- UI tests for Simple/Advanced/Expert visibility, incompatible control
  explanations, immediate/restart badges, and keyboard operation.
- Snapshot tests for user-facing clamp diagnostics without raw exceptions.

## Acceptance criteria

- Every effective inference parameter comes from a typed model-specific schema.
- Simple mode requires no framework vocabulary.
- Expert mode is hidden by default.
- Presets vary by model, hardware, live memory, input, and installation state.
- A safety change is never silent.
- Per-job overrides do not mutate unrelated model defaults.
- Invalid/incompatible values cannot reach a worker.
- Result diagnostics can reconstruct exactly what ran.

