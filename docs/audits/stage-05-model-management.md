# Stage 05 — AI Model Management Audit

**Audit date:** 2026-07-27  
**Scope:** bundled inpainting/OCR weights; rembg; Real-ESRGAN; MIRNet; SAM2;
Grounding DINO; FLUX.2 and Qwen-Image generation models; download registry
and queue; worker-side loading, switching, caching, and release.  
**Constraint:** audit and design only; no production code was changed.

## Executive assessment

Midgard has several useful model-management building blocks—catalogs, a
single-item download queue, `.part` files for direct downloads, Hugging Face
local snapshots, pending-download persistence, and explicit inference release
functions—but no authoritative model registry or lifecycle.

There are currently at least five incompatible definitions of “installed”:

- a bundled expected path exists after chunk merge;
- a file exists and has non-zero size;
- a MIRNet file is larger than 1 MB;
- a Hugging Face directory has one early metadata file;
- a local `.midgard_installed` marker exists.

None verifies a declared file set, checksum, revision, license acceptance, or
framework compatibility. A truncated or wrong weight can be called installed
until model loading fails. Conversely, recovery can delete useful data: Select
Object pair cancellation removes both model directories, even if one member was
previously complete, and rembg cancellation deletes the final `.onnx` path
because it has no separate Midgard staging filename.

The target is a manifest-driven manager with immutable metadata, content
verification, explicit state transitions, atomic installation, license/gating
records, capacity checks, and a separate runtime cache. Download state and
loaded-model state must not be inferred from files ad hoc.

## Sources inspected

Primary implementation paths include:

- `backend/tools/model_config.py`
- `backend/tools/bg_remove_models.py`, `bg_remove.py`
- `backend/tools/enhance_models.py`, `image_enhance.py`
- `backend/tools/low_light_models.py`, `image_low_light.py`
- `backend/tools/select_object_models.py`, `grounded_sam2.py`
- `backend/tools/generate_models.py`, `image_generate.py`
- `backend/tools/first_run_downloads.py`
- `backend/tools/model_download_registry.py`
- `backend/tools/model_download_queue.py`
- `backend/tools/model_download_lifecycle.py`
- `backend/tools/hf_auth.py`
- `backend/tools/infer_worker.py`, `inpaint_release.py`
- `backend/main.py`, `backend/inpaint/**`
- `install.py`, `requirements.txt`, and files under `backend/models/`

Local sizes below are observations of this checkout, not trustworthy expected
sizes. MiB means bytes divided by 1,048,576. Generated/ignored files can differ
between machines.

## Inventory conventions

Every requested model is covered by:

1. a per-model identity row;
2. a per-model artifact row; and
3. family runtime requirements and lifecycle policy.

“Unknown” means Midgard does not declare or verify the value. It is not an
estimate. RAM and VRAM entries describe current Midgard policy or its coarse
budget heuristic; they are not vendor-certified minima.

Backend abbreviations:

- **TC:** Torch CUDA
- **TD:** Torch DirectML
- **TM:** Torch MPS
- **TPU:** Torch CPU
- **ORT:** ordered ONNX Runtime providers, ending in CPU
- **PC/PG:** Paddle CPU/Paddle GPU

## Inventory — bundled video inpainting and OCR

### Identity and policy

| ID | Display name | Purpose | Framework/source | License / gated | Compatible backends; dtype | Default enablement |
|---|---|---|---|---|---|---|
| `sttn-auto` | STTN Auto | Automatic subtitle video inpainting | Bundled PyTorch STTN derivative; upstream/version not recorded | Unknown; not gated | TPU, TC, TD, TM through general Torch device; effective dtype not declared | Built-in selectable mode |
| `sttn-det` | STTN Detection | Mask-guided subtitle video inpainting | Bundled PyTorch STTN derivative; upstream/version not recorded | Unknown; not gated | TPU, TC, TD, TM; dtype not declared | Built-in selectable mode |
| `lama` | LaMa | Image/frame inpainting | Bundled PyTorch checkpoint; [upstream LaMa](https://github.com/advimman/lama) | Upstream code Apache-2.0; weight provenance/license not recorded; not gated | TPU, TC, TM; DirectML is explicitly bypassed; dtype not declared | Built-in selectable mode |
| `propainter` | ProPainter | Temporal video inpainting | Bundled PyTorch checkpoints; [upstream ProPainter](https://github.com/sczhou/ProPainter) | Upstream NTU S-Lab License 1.0, non-commercial terms; Midgard records no acceptance; not gated | TPU or TC only; FP16 normally, CPU path adapts | Built-in selectable mode |
| `PP-OCRv5_server_det` | PaddleOCR v5 Server Detection | Higher-quality subtitle text detection | Bundled Paddle/PaddleOCR model | Source/revision and weight license not recorded; PaddleOCR code is Apache-2.0; not gated | PC only in current code (`device="cpu"`); inference dtype not declared | Selectable; current config decides server/mobile |
| `PP-OCRv5_mobile_det` | PaddleOCR v5 Mobile Detection | Faster/lighter subtitle text detection | Bundled Paddle/PaddleOCR model | Same provenance gap; not gated | PC only; optional HPI is enabled independently of device | Selectable |

### Artifacts, size, version, and integrity

| ID | Local path and expected files | Expected size / observed size | Checksum | Version |
|---|---|---|---|---|
| `sttn-auto` | `backend/models/sttn-auto/infer_model.pth` | Not declared; observed 63.2 MiB | None | Unknown |
| `sttn-det` | `backend/models/sttn-det/sttn.pth` | Not declared; observed 63.2 MiB | None | Unknown |
| `lama` | `backend/models/big-lama/big-lama.pt`; shipped as `big-lama_1.pt`…`_5.pt` plus `fs_manifest.csv` | Not declared; merged file observed 196.3 MiB | No cryptographic checksum; chunk manifest is not used as a content hash | Unknown |
| `propainter` | `backend/models/propainter/ProPainter.pth`, `raft-things.pth`, `recurrent_flow_completion.pth`; main file shipped in four chunks plus `fs_manifest.csv` | Main 150.5 MiB, RAFT 20.1 MiB, recurrent-flow 19.4 MiB observed | None | Unknown |
| `PP-OCRv5_server_det` | `backend/models/V5/ch_det/{config.json,inference.json,inference.pdiparams,inference.yml}` | Params observed 83.9 MiB; total expected not declared | None | Label says v5; exact model revision unknown |
| `PP-OCRv5_mobile_det` | `backend/models/V5/ch_det_fast/{config.json,inference.json,inference.pdiparams,inference.yml}` | Params observed 4.5 MiB; total expected not declared | None | Label says v5; exact model revision unknown |

### Runtime requirements and lifecycle

| Family | RAM/VRAM requirement | Cache/loading | Unload policy |
|---|---|---|---|
| STTN Auto/Detection | No validated minima. Budgeter estimates STTN as `400 MiB + 90 MiB × frames × megapixels`, then applies 1.5× headroom when VRAM is measurable. | Loaded on demand in inference worker; model references can remain warm after a job. | Registered video-inpaint release functions move/delete models and clear CUDA caches; exceptions during release are generally suppressed by worker orchestration. |
| LaMa | No declared RAM minimum. Budgeter estimates `200 MiB + 180 MiB × megapixels`. | Image-inpaint/retouch loaders cache model references. `ModelConfig()` can synchronously merge chunks before load. | Released on modality switch, explicit reset, or worker shutdown. |
| ProPainter | No declared RAM/VRAM minimum. Budgeter estimates `800 MiB + 140 MiB × frames × megapixels`. | On-demand, worker-local; supporting RAFT and flow completion weights are part of one logical model. | Released with video-inpaint cache. CUDA scratch depends on normal teardown. |
| PaddleOCR | No declared RAM/VRAM minimum. Server is materially larger than mobile. | `SubtitleDetect.text_detector` is a `cached_property`; created at first OCR use, not by a central manager. | No explicit Paddle model unload API is coordinated by the model manager; lifetime follows containing object/process and framework cleanup. |

Critical observations:

- `ModelConfig.__init__` performs chunk merging for LaMa and ProPainter. Model
  path lookup therefore mutates disk and can block any caller.
- Chunk merges are existence-based, not verified or atomic from the model
  manager's perspective.
- Paddle GPU wheel installation does not imply Paddle GPU use. `SubtitleDetect`
  passes `device="cpu"` unconditionally.
- `enable_hpi` depends on optional PaddleX HPI availability plus the global
  “has any accelerator” result; it does not identify the accelerator Paddle
  will use.

## Inventory — rembg models

All fifteen models are ONNX models delegated to rembg. Midgard stores them at
`BaseSession.u2net_home()`—normally the `U2NET_HOME`/XDG location or
`~/.u2net`—rather than under `backend/models`. Each expected artifact is
`<id>.onnx`.

The [rembg model catalog](https://github.com/danielgatis/rembg#models) is the
effective source registry. rembg itself is MIT, but that does **not** establish
one license for every third-party weight. Midgard records no per-model source
revision, license, gated status, expected size, or checksum. rembg has its own
download/hash behavior, but Midgard's installed check only tests `size > 0` and
does not capture the verified digest.

### Per-model identity

| ID / display name | Purpose/category | Source and license status | Default |
|---|---|---|---|
| `birefnet-general` / BiRefNet General | General, preferred quality | rembg catalog; underlying weight license/revision not recorded—must be verified | Enabled and first-install prefetched |
| `isnet-general-use` / IS-Net General | General foreground segmentation | rembg catalog; license/revision not recorded | Optional |
| `u2net` / U²-Net | General foreground segmentation | rembg catalog/U²-Net source; license/revision not recorded in Midgard | Optional |
| `u2netp` / U²-Net-p | Lightweight general segmentation | rembg catalog; license/revision not recorded | Optional |
| `silueta` / Silueta | Reduced-size U²-Net-like general model | rembg catalog; catalog describes about 43 MB, but Midgard does not enforce it | Optional |
| `birefnet-general-lite` / BiRefNet General Lite | Lightweight general segmentation | rembg catalog; license/revision not recorded | Optional |
| `birefnet-massive` / BiRefNet Massive | General model trained on a broad dataset | rembg catalog; license/revision not recorded | Optional |
| `bria-rmbg` / BRIA RMBG | General background removal | rembg/BRIA source; license terms must be checked separately before distribution/use | Optional |
| `u2net_human_seg` / U²-Net Human | Human segmentation | rembg catalog; license/revision not recorded | Enabled and first-install prefetched |
| `birefnet-portrait` / BiRefNet Portrait | Portrait segmentation | rembg catalog; license/revision not recorded | Optional |
| `isnet-anime` / IS-Net Anime | Anime character segmentation | rembg catalog; license/revision not recorded | Enabled and first-install prefetched |
| `u2net_cloth_seg` / U²-Net Cloth | Clothing segmentation, three output categories | rembg catalog; license/revision not recorded | Enabled and first-install prefetched |
| `birefnet-dis` / BiRefNet DIS | Dichotomous image segmentation | rembg catalog; license/revision not recorded | Optional |
| `birefnet-hrsod` / BiRefNet HRSOD | High-resolution salient-object detection | rembg catalog; license/revision not recorded | Optional |
| `birefnet-cod` / BiRefNet COD | Concealed-object detection | rembg catalog; license/revision not recorded | Optional |

### Per-model artifacts and runtime contract

The following table explicitly supplies the remaining fields for every rembg
entry. “ORT” means any provider returned by Midgard's ordered provider list,
with CPU fallback. Dtype and memory are not declared in Midgard.

| ID | Expected file | Expected size/checksum/version | RAM/VRAM | Backends/dtype | Cache/unload |
|---|---|---|---|---|---|
| `birefnet-general` | `birefnet-general.onnx` | Unknown / no Midgard digest / unpinned rembg asset | Unknown; budgeter uses a generic 900 MiB rembg estimate | ORT; model dtype unknown | rembg session cache; explicit `release_bg_sessions()` on modality switch/shutdown |
| `isnet-general-use` | `isnet-general-use.onnx` | Unknown / none / unpinned | Same | ORT; unknown | Same |
| `u2net` | `u2net.onnx` | Unknown / none / unpinned | Same | ORT; unknown | Same |
| `u2netp` | `u2netp.onnx` | Unknown / none / unpinned | Same | ORT; unknown | Same |
| `silueta` | `silueta.onnx` | About 43 MB per upstream catalog, not enforced / none / unpinned | Same | ORT; unknown | Same |
| `birefnet-general-lite` | `birefnet-general-lite.onnx` | Unknown / none / unpinned | Same | ORT; unknown | Same |
| `birefnet-massive` | `birefnet-massive.onnx` | Unknown / none / unpinned | Same | ORT; unknown | Same |
| `bria-rmbg` | `bria-rmbg.onnx` | Unknown / none / unpinned | Same | ORT; unknown | Same |
| `u2net_human_seg` | `u2net_human_seg.onnx` | Unknown / none / unpinned | Same | ORT; unknown | Same |
| `birefnet-portrait` | `birefnet-portrait.onnx` | Unknown / none / unpinned | Same | ORT; unknown | Same |
| `isnet-anime` | `isnet-anime.onnx` | Unknown / none / unpinned | Same | ORT; unknown | Same |
| `u2net_cloth_seg` | `u2net_cloth_seg.onnx` | Unknown / none / unpinned | Same | ORT; unknown | Same |
| `birefnet-dis` | `birefnet-dis.onnx` | Unknown / none / unpinned | Same | ORT; unknown | Same |
| `birefnet-hrsod` | `birefnet-hrsod.onnx` | Unknown / none / unpinned | Same | ORT; unknown | Same |
| `birefnet-cod` | `birefnet-cod.onnx` | Unknown / none / unpinned | Same | ORT; unknown | Same |

The generic 900 MiB budget is not model-specific and the current guard has an
unusual condition: it raises only when estimated need exceeds free VRAM **and**
free VRAM is below 500 MiB. It is not an enforceable requirement.

## Inventory — enhancement and low-light

| ID | Display/purpose | Framework/source/license/gated | Local path/files | Size/checksum/version | RAM/VRAM and backends/dtype | Default/cache/unload |
|---|---|---|---|---|---|---|
| `RealESRGAN_x2plus` | Real-ESRGAN x2; 2× super-resolution | PyTorch; [official release v0.2.1](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.1); BSD-3-Clause project license; not gated | `backend/models/realesrgan/RealESRGAN_x2plus.pth` | Expected size not declared; observed 64.0 MiB; no checksum; URL pins release v0.2.1 | Budgeter counts 70 MiB weights plus image/tile memory; TPU/TC/TD/TM through general device; model commonly FP32, effective dtype not declared | Enabled by default and selectable even before install; one cached enhancer keyed by model/device/tile; release moves to CPU/deletes and clears CUDA |
| `RealESRGAN_x4plus` | Real-ESRGAN x4; 4× super-resolution | PyTorch; [official release v0.1.0](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.1.0); BSD-3-Clause; not gated | `backend/models/realesrgan/RealESRGAN_x4plus.pth` | Not declared; absent in this checkout; no checksum; URL pins v0.1.0 | Same policy | Optional, installed + enabled before selectable; same single-entry cache |
| `MIRNet_LOL` | MIRNet LOL low-light enhancement | PyTorch; [official MIRNet repository](https://github.com/swz30/MIRNet), Google Drive asset; repository has custom license file; exact weight terms/revision not recorded; not gated | `backend/models/mirnet/MIRNet_LOL.pth` | Not declared; observed 364.4 MiB; no checksum; version unknown | No declared minima; TPU/TC/TD/TM; dtype not declared | Enabled/default selectable before install; one cached model; explicit release to CPU/delete/clear CUDA |

Real-ESRGAN and MIRNet direct downloads use `<file>.part`, check basic size, and
atomically replace the final file. This protects the final filename from a
half-written direct download, but does not prove content. MIRNet rejects files
smaller than 1 MB and obvious HTML responses; a large error document or corrupt
checkpoint still passes.

## Inventory — Select Object

SAM2 and Grounding DINO are installed and selected as pairs:

- `fast`: SAM2 Tiny + Grounding DINO Tiny; default and first-run queued;
- `complex`: SAM2 Large + Grounding DINO Base; optional.

### Per-model contract

| ID | Display/purpose | Framework/source/license/gated | Local path and expected files | Size/checksum/version | RAM/VRAM, backends, dtype | Default/cache/unload |
|---|---|---|---|---|---|---|
| `sam2-hiera-tiny` | SAM2 Tiny; promptable segmentation | Transformers/PyTorch; `facebook/sam2-hiera-tiny`; Apache-2.0; not marked gated | `backend/models/select_object/sam2-hiera-tiny/`; `config.json`, processor/preprocessor config, exactly one supported weight representation, `.midgard_installed` | Manifest has no expected list/size/digest/revision. Current snapshot observed both `model.safetensors` and `sam2_hiera_tiny.pt`, about 297 MiB combined | Fast-pair heuristic 4.5 GiB total pair VRAM; TPU/TC/TD/TM; loader dtype follows implementation/device, not cataloged | Default fast pair; SAM and DINO caches; pair retained after selection job until modality switch/reset/shutdown |
| `sam2-hiera-large` | SAM2 Large; higher-quality segmentation | Transformers/PyTorch; `facebook/sam2-hiera-large`; Apache-2.0; not marked gated | Equivalent local snapshot directory and marker | Unknown/unverified/unpinned; absent here | Complex-pair heuristic 12 GiB total pair VRAM; TPU/TC/TD/TM; dtype not cataloged | Optional complex pair; same cache policy |
| `grounding-dino-tiny` | Grounding DINO Tiny; text-grounded box detection | Transformers/PyTorch; `IDEA-Research/grounding-dino-tiny`; Apache-2.0; not marked gated | `backend/models/select_object/grounding-dino-tiny/`; `config.json`, processor/preprocessor config, one supported weight file, marker | No manifest/digest/revision. Current snapshot contains both `model.safetensors` and `pytorch_model.bin`, about 1.29 GiB combined | Included in 4.5 GiB pair heuristic; TPU/TC/TD/TM; dtype not cataloged | Default fast pair; same cache policy |
| `grounding-dino-base` | Grounding DINO Base; higher-quality text-grounded detection | Transformers/PyTorch; `IDEA-Research/grounding-dino-base`; Apache-2.0; not marked gated | Equivalent local snapshot directory and marker | Unknown/unverified/unpinned; absent here | Included in 12 GiB pair heuristic; TPU/TC/TD/TM; dtype not cataloged | Optional complex pair; same cache policy |

Because `snapshot_download` has no `allow_patterns`, this checkout downloaded
multiple equivalent weight formats for both default models. That consumes
roughly twice the necessary weight storage. No revision is pinned, so the same
Midgard version can install different upstream content at different times.

`is_model_installed()` may adopt any directory containing `config.json` and
touch the installed marker unless a matching pair is currently pending. A
partial snapshot can contain `config.json` early. Corrupt pending JSON or a
registry failure can therefore convert partial content to installed.

On pair cancellation/failure, `discard_pair_partial()` removes both member
directories without respecting an installed marker. Installing the second
member can therefore destroy a previously valid first member.

## Inventory — image generation

All generation pipelines are downloaded as complete Hugging Face snapshots
under `backend/models/generate/<id>/`. Midgard requires CUDA via an allocation
smoke test; it does not expose CPU, MPS, or DirectML fallback for this feature.
It uses BF16 when CUDA reports support, otherwise FP16.

| ID | Display/purpose | Framework/source | License / gated | Expected files and local path | Size/checksum/version | RAM/VRAM | Default/cache/unload |
|---|---|---|---|---|---|---|---|
| `FLUX.2-klein-4B` | FLUX.2 Klein 4B distilled; fast text-to-image | Diffusers/Transformers/PyTorch; `black-forest-labs/FLUX.2-klein-4B` | Apache-2.0; current model card describes open commercial use; not marked gated | Diffusers `model_index.json`, scheduler, transformer, text encoder(s), tokenizer(s), VAE, one supported weight format each, marker; `backend/models/generate/FLUX.2-klein-4B/` | Manifest absent; snapshot unpinned | About 13 GB VRAM upstream; CUDA only, BF16 or FP16 | Optional four-step model; install enables it. One generation pipeline is cached. |
| `FLUX.2-klein-9B` | FLUX.2 Klein 9B distilled; higher-capacity text-to-image | Same stack; `black-forest-labs/FLUX.2-klein-9B` | FLUX non-commercial license; gated with license/contact acceptance | Equivalent Diffusers snapshot at `.../FLUX.2-klein-9B/` | Unknown/unverified/unpinned | About 29 GB VRAM upstream; CUDA only, BF16/FP16 | Optional four-step model; same one-entry cache. |
| `FLUX.2-klein-base-4B` | FLUX.2 Klein 4B base; flexible text-to-image | Same stack; `black-forest-labs/FLUX.2-klein-base-4B` | Apache-2.0 | Equivalent Diffusers snapshot at `.../FLUX.2-klein-base-4B/` | Manifest absent; snapshot unpinned | About 13 GB VRAM; CUDA only, BF16/FP16 | Default catalog model; 50-step schedule. |
| `FLUX.2-klein-base-9B` | FLUX.2 Klein 9B base; flexible higher-capacity text-to-image | Same stack; `black-forest-labs/FLUX.2-klein-base-9B` | FLUX non-commercial license; gated | Equivalent Diffusers snapshot at `.../FLUX.2-klein-base-9B/` | Unknown/unverified/unpinned | About 29 GB VRAM; CUDA only, BF16/FP16 | Optional 50-step model; same one-entry cache. |
| `FLUX.2-dev` | FLUX.2 Dev 32B | Diffusers/Transformers/PyTorch; `black-forest-labs/FLUX.2-dev` | FLUX non-commercial license; gated | Filtered full Diffusers component snapshot | About 105.1 GiB downloaded | CUDA plus sequential CPU offload | Optional 50-step model. |
| `FLUX.2-klein-9b-fp8` | FLUX.2 Klein 9B distilled FP8 | Official single-file transformer plus full-9B Diffusers components | FLUX non-commercial license; both repositories gated | 9.43 GB FP8 transformer; BF16 transformer excluded | About 24.2 GiB combined | Upstream estimates about 29 GB VRAM; sequential CPU offload | Optional four-step model. |
| `Qwen-Image` | Qwen-Image 20B | Diffusers/Transformers/PyTorch; `Qwen/Qwen-Image` | Apache-2.0 | Filtered full Diffusers component snapshot | About 53.7 GiB downloaded | CUDA plus sequential CPU offload | Optional 50-step model using true CFG. |

The generation catalog stores pipeline type, guidance, and step presets, but no
revision, artifact allow-list, license ID/version, acceptance requirement,
expected size, digest, memory minimum, or compatibility record. Error handling
infers gating by matching strings such as `401`, `403`, `gated`, and
`unauthorized`.

Licenses are mutable external facts. The registry should pin a license document
identifier/digest with each model revision and require explicit re-acceptance
when terms change. Repository code licenses and model-weight licenses must be
separate fields.

## Storage audit

| Storage class | Current location | Ownership/problem |
|---|---|---|
| Bundled core models | `backend/models/` inside application tree | Installation/update can overwrite; may be read-only; chunk merge writes into application files |
| Downloaded Real-ESRGAN/MIRNet | `backend/models/` | Same issue; not user-scoped |
| HF Select/Generate | `backend/models/` | Very large mutable caches inside app tree; full snapshot duplicates formats |
| rembg | `U2NET_HOME`, XDG, or `~/.u2net` | Outside Midgard's path policy and inventory; shared with other rembg clients |
| Pending registry | user data/cache-derived path | Plain JSON without atomic replace or process lock |
| Hugging Face internal cache metadata | within local snapshot and/or HF cache conventions | Revision data exists incidentally but Midgard does not adopt it into its manifest |

Target layout:

```text
<user-data>/models/
  objects/sha256/<digest>             # optional content-addressed artifacts
  installed/<model-id>/<version>/     # atomic finalized installs
  staging/<transaction-id>/           # never considered installed
  manifests/<model-id>.json
  state/model-state.json
  locks/
```

Bundled read-only assets can remain in an application resource root, but the
manager should expose them through the same manifest and verification API.
Merged artifacts belong in user cache/data, not alongside shipped chunks.

## Download lifecycle audit

### What works

- one process-local queue serializes downloads;
- direct HTTP downloads for Real-ESRGAN and MIRNet use `.part` then
  `os.replace`;
- pending items can be remembered across normal GUI shutdown;
- a report hook can cancel `urlretrieve` during transfer;
- Hugging Face token resolution is centralized;
- UI catalog enablement is separated from whether some models are installed.

### Failure modes

1. **Non-atomic registry.** Pending JSON is written directly. A crash can
   truncate it; corrupt JSON is silently treated as no pending work.
2. **No process safety.** Locks guard threads in one process only. Installer,
   GUI, repeated tests, or two app instances can race on the same registry and
   paths.
3. **Daemon worker leak.** The download queue owns a daemon thread without a
   stop/join handshake. Process exit, cancellation, and filesystem deletion can
   race.
4. **Cancellation granularity.** Hugging Face and rembg cancellation is checked
   only before/after their blocking downloader. Shutdown may start deleting a
   destination while the library still writes it.
5. **Pending loss.** Most network/auth/general failures call
   `fail(..., keep_pending=False)`. Offline startup can permanently discard
   recovery intent instead of transitioning to a retryable state.
6. **Destructive recovery.** Startup recovery wipes partial content and starts
   over rather than resuming validated chunks.
7. **No disk reservation.** A download can consume the model volume until the
   filesystem is full.
8. **No checksum/manifest.** Size checks and marker files substitute for
   verification.
9. **No revision pinning.** HF snapshots track mutable repository heads.
10. **No transaction boundary.** Files, config enablement, marker creation, and
    pending state are separate writes.
11. **No license gate.** Token entry and string-matched HTTP errors replace a
    first-class acceptance workflow.
12. **No safe adoption.** `model_index.json` or `config.json` can cause marker
    creation without loading or complete-file verification.

## Loading, switching, caching, and GPU allocation

The inference worker calls `_release_all_except(job_type)` before dispatch.
This enforces approximately one feature family at a time, then leaves the
current family's cache warm after completion. Reset and shutdown attempt to
release all families.

Benefits:

- avoids retaining every large model simultaneously;
- isolates heavy framework state in a child process;
- explicit release functions exist for enhance, low-light, generate,
  background removal, inpainting, and selection.

Risks:

- no central accounting knows which artifacts are loaded, their device, dtype,
  memory, active references, or last use;
- five-second release locks can time out; callers may continue with old models
  alive;
- many release paths catch and suppress exceptions;
- `torch.cuda.empty_cache()` releases allocator cache, not live tensors held by
  hidden references;
- Paddle OCR has no coordinated explicit release;
- framework/process global state can outlive a logical cache entry;
- cache keys are feature-specific and inconsistent;
- selection loads a pair but uses coarse pair-level memory estimates;
- the mutable hardware singleton can select a backend incompatible with a
  cached model;
- model switching and shutdown can race with in-flight inference unless the
  worker protocol fully reaches a safe point.

Current VRAM policy is heuristic, not allocation management. It uses constants
and a 1.5× headroom multiplier only when CUDA-style VRAM is measurable. MPS
unified memory and DirectML get no reliable budgeting. There is no reservation,
admission queue, LRU eviction across models, OOM classification, or telemetry
feedback.

## Corruption, version, and license handling

### Corruption

No model has a Midgard-owned cryptographic verification contract. Current
signals—non-empty file, >1 MB, config/model-index presence, or marker—cannot
distinguish:

- truncated but non-empty data;
- HTML/error payloads above the threshold;
- a valid file for the wrong architecture;
- mixed files from different HF commits;
- incomplete multi-file snapshots;
- corrupted chunk merges;
- incompatible serialization or framework version.

Loading exceptions eventually expose some corruption, but do not consistently
mark the model broken or quarantine it.

### Version

Only Real-ESRGAN URLs pin release tags. Bundled models lack recorded revisions.
HF downloads omit `revision=`, and rembg assets follow the installed rembg
package/catalog. `requirements.txt` allows ranges for rembg, Transformers,
Hugging Face Hub, and Diffusers, so identical Midgard versions can resolve
different model/package combinations.

### License and gated access

Midgard has no license ledger. Required fields are:

- SPDX identifier when applicable;
- model-weight license name/version and canonical URL;
- source-code license separately;
- redistribution allowed;
- commercial-use constraints;
- attribution/notice files;
- gated status and required upstream action;
- accepted license digest, timestamp, and user decision;
- whether the application may prefetch the asset.

The FLUX 9B and ProPainter cases demonstrate why a boolean “gated” flag is not
enough: an ungated bundled/downloadable asset may still have non-commercial
terms. rembg's MIT license does not automatically cover its third-party model
weights.

## Target package

```text
backend/models/
  registry.py       # immutable catalog lookup; no downloads
  metadata.py       # ModelId, license, requirements, compatibility
  manifest.py       # versioned file/revision/digest manifests
  downloader.py     # resumable transactions and transports
  verifier.py       # size/hash/file-set/load-smoke verification
  loader.py         # framework adapters and typed load results
  cache.py          # loaded handles, leases, accounting
  manager.py        # state machine and public orchestration
  eviction.py       # admission, LRU/priority, memory pressure
  exceptions.py     # classified actionable failures
  manifests/
    sttn-auto.json
    ...
```

Core metadata should be immutable:

```python
@dataclass(frozen=True)
class ModelMetadata:
    id: ModelId
    display_name_key: str
    purpose: str
    framework: Framework
    source: SourceSpec
    license: LicenseSpec
    artifacts: tuple[ArtifactSpec, ...]
    requirements: ResourceRequirements
    compatible_backends: tuple[BackendSpec, ...]
    default_enabled: bool
    cache_policy: CachePolicy
    unload_policy: UnloadPolicy

@dataclass(frozen=True)
class ModelManifest:
    schema_version: int
    model_id: ModelId
    model_version: str
    source_revision: str
    artifacts: tuple[ArtifactDigest, ...]
    total_download_bytes: int
    installed_bytes: int
    framework_constraints: tuple[str, ...]
    license_digest: str
```

Manifests are shipped with Midgard and reviewed like code. A remote signed
manifest update may be added later, but mutable remote metadata must not
silently redefine an installed model.

## Model state machine

Required states:

```text
NOT_INSTALLED
    └─ queue ───────────────> QUEUED
QUEUED
    └─ worker lease ────────> DOWNLOADING
DOWNLOADING
    ├─ all artifacts staged > VERIFYING
    ├─ retryable failure ───> QUEUED (with backoff/reason)
    ├─ cancel ──────────────> NOT_INSTALLED or QUEUED-for-resume
    └─ invalid partial ─────> BROKEN
VERIFYING
    ├─ atomic commit ───────> INSTALLED
    └─ verification failure > BROKEN
INSTALLED
    ├─ compatible load ─────> LOADING
    ├─ incompatibility ─────> INCOMPATIBLE
    └─ uninstall ───────────> NOT_INSTALLED
LOADING
    ├─ ready ───────────────> READY
    ├─ compatibility fail ──> INCOMPATIBLE
    └─ corrupt/load fail ───> BROKEN
READY
    ├─ acquire job lease ───> BUSY
    └─ eviction/shutdown ───> UNLOADING
BUSY
    ├─ job complete ────────> READY
    └─ cooperative cancel ──> READY or BROKEN
UNLOADING
    ├─ references released ─> INSTALLED
    └─ timeout/failure ─────> BROKEN (runtime instance)
BROKEN
    ├─ repair/re-download ──> QUEUED
    └─ uninstall ───────────> NOT_INSTALLED
INCOMPATIBLE
    └─ profile/package change + re-evaluate -> INSTALLED
```

State is per `(model ID, version, installation root)` for installation and per
`(model ID, version, process, backend, device, dtype)` for runtime. Do not
collapse a broken runtime instance into corrupt on-disk artifacts without
evidence.

Every transition is validated and journaled with timestamps and a classified
reason. UI enablement is a separate user preference, not a model state.

## Download and verification design

### Transaction

```text
resolve manifest
  -> validate license/gate/token requirements
  -> calculate required bytes + safety reserve
  -> acquire cross-process model/version lock
  -> create unique staging directory
  -> download/resume declared artifacts
  -> verify exact file set, sizes, digests, revision
  -> optional framework-safe load smoke test
  -> fsync files and metadata
  -> atomically rename staging to final version directory
  -> atomically persist installed state
  -> release lock
```

Never download directly to a final path. Never delete a finalized installation
as “partial.” A pair install is either two independent transactions followed by
an atomic pair-availability record, or one composite transaction referencing
pre-existing verified members.

### Transport behavior

- HTTP: range resume only when ETag/content identity matches; otherwise restart
  staging.
- Hugging Face: pin commit SHA and request only manifest allow-listed files.
  Preserve resumable library cache, but materialize/verify a final snapshot.
- rembg: own the URL/digest in Midgard manifests or adapt rembg's checksum
  metadata into the verifier. Do not delegate installation state.
- bundled chunks: verify every chunk and merged digest; merge into staging and
  atomically finalize.

### Verification levels

1. **Structural:** exact required files, no forbidden substitutes, safe paths.
2. **Content:** byte size and SHA-256/BLAKE3 for every artifact.
3. **Source:** pinned HF commit/release and license digest.
4. **Serialization:** framework can inspect/load metadata safely.
5. **Runtime:** optional bounded smoke test on a selected compatible backend.

A failure moves the installation to `BROKEN`, preserves a bounded diagnostic,
and quarantines staging for inspection or deletes it according to policy.
Automatic repair must be explicit and never overwrite the last verified
version before a replacement is ready.

## Runtime loader, cache, and eviction

`loader.py` adapters return a managed handle:

```text
LoadedModel(
  model_id, version, backend, device_id, dtype,
  estimated_bytes, measured_bytes, handle, release_callback
)
```

Jobs acquire leases. A model cannot enter `UNLOADING` while a lease exists.
Shutdown stops new leases, cancels/waits for jobs according to policy, then
unloads in reverse dependency order.

Cache key:

```text
(model_id, version, source_revision, backend, device_id, dtype, load_options)
```

Eviction should use:

- hard compatibility and memory admission first;
- idle-only eviction;
- LRU within priority class;
- feature dependency groups (SAM + DINO, ProPainter + RAFT + flow completion);
- measured peak memory feedback;
- a configurable warm-cache budget;
- process restart as the final containment mechanism after a release failure.

CPU RAM, discrete VRAM, and unified memory are separate budgets. The manager
must reserve scratch/output memory, not just weight size. OOM is a classified
runtime failure; policy may evict and retry once with an approved lower tile,
batch, frame window, or dtype.

## Failure policy

| Failure | State/result | User behavior |
|---|---|---|
| Offline/DNS/timeout | `QUEUED` with retry metadata, not forgotten | App remains usable; show paused/retry action and exponential backoff |
| Authentication missing | `QUEUED` blocked by credentials | Explain token scope; never log token |
| License not accepted | `QUEUED` blocked by consent | Link canonical terms and record acceptance digest |
| Insufficient disk | Stay `QUEUED`; no download | Show required, available, reserve, and chosen model root |
| Checksum mismatch | `BROKEN`; quarantine/delete staging | Never mark installed; offer retry/report |
| Corrupt existing model | `BROKEN` | Disable selection, keep other features available, offer repair |
| Backend incompatible | `INCOMPATIBLE` | Explain hardware/framework requirement; do not redownload |
| Load OOM | Remain `INSTALLED`; runtime load failed | Evict/reduce once if allowed, otherwise actionable error |
| Download cancelled | Staging retained only if safely resumable; otherwise removed | Final verified version untouched |
| Process crash | Reconcile journal/locks on next start | Resume/reverify staging; never infer installed from one metadata file |
| Unknown model ID/version | Typed registry error | Do not construct a path or download |

Errors must be classified (`NetworkError`, `AuthRequired`, `LicenseRequired`,
`DiskSpaceError`, `IntegrityError`, `IncompatibleBackend`, `LoadError`,
`OutOfMemory`, `Cancellation`, `RegistryError`) rather than parsed from message
strings.

## Worker-safe operation

- The GUI owns desired actions; a dedicated download service owns mutations.
- Use OS file locks and transaction IDs so installer, GUI, tests, and multiple
  instances cannot install/uninstall the same version concurrently.
- Inference workers receive immutable manifest and hardware-policy snapshots.
- Workers never write catalog or installation state; they report load/runtime
  results to the manager.
- Uninstall requires zero active leases across workers.
- State writes use temp file, fsync, atomic replace, and a versioned schema.
- Test instances use isolated model roots by default, never the developer's
  real `~/.u2net` or HF cache.

## Migration plan

### Phase 1 — Freeze and describe the current catalog

- Assign stable IDs to every model listed in this audit.
- Add manifests initially marked `integrity: legacy-unverified`.
- Record exact bundled file digests, upstream revisions, and weight licenses
  through a separate provenance review.
- Add characterization tests for every current installed predicate and cache.

### Phase 2 — Registry facade

- Introduce `metadata.py`, `manifest.py`, and `registry.py`.
- Adapt current catalogs behind the registry without changing UI behavior.
- Keep existing helper functions as compatibility facades.
- Separate user enablement/selection from installation state.

### Phase 3 — Safe paths and verification

- Establish a writable user model root and staging root.
- Verify bundled chunks and merge atomically outside the application tree.
- Add full file-set/size/digest verification.
- Import existing files as `legacy-unverified`, verify where known, and only
  then mark `INSTALLED`; never silently delete an existing user model.

### Phase 4 — Transactional downloader

- Replace direct per-feature installers with one downloader and journal.
- Add disk reservations, cross-process locks, retry/backoff, and resumable
  staging.
- Pin HF commit SHAs and add `allow_patterns` to eliminate duplicate formats.
- Replace pending JSON with atomic, schema-versioned state.

### Phase 5 — State machine and runtime manager

- Implement the declared states and transition validation.
- Wrap existing loaders/release functions in adapters.
- Add runtime leases, measured allocation, cache keys, and reverse-order
  release.
- Preserve current one-feature-family behavior first; optimize only after
  instrumentation.

### Phase 6 — License and gated workflow

- Add source-code versus weight-license records and canonical notice storage.
- Implement acceptance keyed by license digest and model revision.
- Treat token availability, upstream approval, and license acceptance as
  distinct prerequisites.
- Block first-run prefetch for any model whose terms require prior consent.

### Phase 7 — Remove unsafe legacy behavior

- Stop adopting HF directories from `config.json`/`model_index.json`.
- Stop deleting pair members or final rembg files during partial cleanup.
- Remove path-lookup chunk merging.
- Deprecate feature-local installed checks, daemon download queue, and
  message-string gating detection after all callers migrate.

## Acceptance criteria

- Every model has a reviewed manifest containing source revision, exact files,
  sizes, hashes, license, requirements, backends, dtype, and lifecycle policy.
- A marker or non-empty file alone can never mean `INSTALLED`.
- Interrupted downloads cannot damage a prior verified version.
- Offline failures remain retryable and survive restart atomically.
- Downloads validate disk capacity before transfer and reserve safety space.
- HF installs are revision-pinned and do not fetch duplicate weight formats.
- Gated access, credentials, and license acceptance are separate states.
- GUI, installer, downloader, and workers are safe under concurrent access.
- Loaded models have leases, accounting, deterministic unload, and bounded
  shutdown behavior.
- Corrupt, incompatible, missing, and merely disabled models are visibly
  distinct.

