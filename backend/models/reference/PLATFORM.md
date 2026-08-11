# Lluna model platform

## Runtime architecture

```text
Electron
    |
Node backend / control plane
    |
Shared Python AI worker
    |-------------------------------|
 BiRefNet, native tools      SeedVR2 isolated Python runtime
    |                               |
    -------- managed model storage -
                    |
             Hugging Face weights
```

In development the managed storage is under `backend/models`; packaged builds
resolve the same logical location through Lluna's application-data paths. The
Node backend owns model inventory, install queues, enable/disable state, and
workflow routing. SeedVR2 is launched as a separate cancellable subprocess
because its official CUDA/Python dependencies must not be mixed with Lluna's
main Python environment.

Lluna-managed user models live in `models/custom/<model-id>/`. Each folder
contains a `lluna-model.json` manifest and its local weights. In development,
`models` is `backend/models`; packaged builds use the operating system's Lluna
application-data directory.

```text
models/
├── custom/                 # installed/imported user models
│   └── <model-id>/
│       ├── lluna-model.json
│       ├── .lluna-installed
│       └── <weights and configuration>
├── .staging/               # incomplete installs; never used for inference
├── .quarantine/            # reserved for failed/untrusted imports
└── .download_cache/        # disposable provider download cache
```

The manifest format is defined by `reference/model-manifest.schema.json`. Model ids are
stable workflow identifiers and cannot be changed after registration.

## Capability contracts

Every usable model declares a `variant` and `capabilities` contract. Lluna
resolves facts in this strict order:

1. a reviewed Lluna catalog contract or user-reviewed manifest;
2. explicit Hugging Face model-card and configuration metadata;
3. safe local inspection of declarative JSON configuration files.

Local inspection never imports model modules or loads weights. Unconfirmed facts
are not inferred from a repository name. The model remains **Needs
configuration** and cannot be enabled until its task, inputs, outputs, variant,
and task-specific controls are reviewed.

The node editor projects its controls from this contract. Distilled models can
fix a small step range and omit guidance; base models can expose guidance;
quantized models declare dtype and backend constraints; LoRA and ControlNet
declare a compatible base model and strengths; inpainting declares mask and
denoise behavior; upscalers declare scale and optional tiling; Transformers
models declare task-specific inputs and outputs. The same contract is validated
again by the graph compiler and runtime adapter, so unsupported values cannot be
introduced through a saved or crafted workflow.

Capability recognition is separate from execution support. In particular, a
LoRA or ControlNet repository is not a standalone pipeline. The generic
Diffusers adapter marks those composition variants incompatible until a reviewed
adapter can resolve and load their declared base model and conditioning inputs.
Lluna never attempts to run them as ordinary checkpoints.

## Runtime profiles

- `lluna-native`: reviewed inference code shipped with Lluna.
- `diffusers-torch`: Diffusers, Transformers, Accelerate, and the selected Torch build.
- `transformers-torch`: Transformers and the selected Torch build.
- `paddle`: the CPU or CUDA Paddle package selected by the installer.
- `seedvr-python`: isolated Python 3.9/3.10 CUDA runtime for the official
  SeedVR2 3B and 7B restoration models.

Repository `requirements.txt` files are never executed automatically. Hugging
Face installs are analyzed first, pinned to the returned commit, restricted to
reviewed files, downloaded into `.staging`, verified, and promoted atomically.
Custom models must use SafeTensors weights. Remote Python code and
pickle-capable custom weights are rejected unconditionally. Reviewed built-in
runtimes may use pinned, hash-verified legacy checkpoints inside their isolated
execution environments.

Folders already under `custom/` are loaded once at startup and are not revisited
during the session. New folders and standalone SafeTensors files should be
imported through **Add model**; this copies them into a managed folder, creates
the manifest, and updates the in-memory catalog. Direct filesystem changes
become visible after an app restart.

## SUPIR runtime

SUPIR is a reviewed built-in adapter pinned to official source commit
`bda91af2000042f8bedfec8897d92917e67c1d88`. It never installs the upstream
`requirements.txt` into Lluna. A dedicated Python 3.8–3.10 environment holds
the reviewed dependency pins and inference runs in a cancellable subprocess.

Installation downloads `SUPIR-v0Q.ckpt` and `SUPIR-v0F.ckpt` from the explicitly labeled XCogni
community mirror at pinned revision
`b13056f97b1f6e78cb76273330f5262d08455a6b`, and SDXL 1.0 from Stability AI at
pinned revision `462165984030d82259a11f4367a4eed129e94a7b`. Exact filenames, sizes,
and SHA-256 digests are verified before atomic promotion. Manual checkpoint
import is also supported. Upstream's Google Drive link remains
available in the UI. This distinction is intentional: XCogni is a convenient
weight mirror, not the authoritative SUPIR implementation or license source.

Upstream restricts SUPIR to non-commercial use and its `.ckpt` files require
pickle-capable PyTorch loading. Lluna therefore runs them only inside the
isolated, pinned SUPIR worker and never treats the mirror's incomplete model card
as executable configuration.

The Upscale node exposes the original sampler and restoration controls, plus
quality/fidelity presets, LLaVA captioning, gamma correction, precision, and
tiled-VAE memory controls. The official implementation is CUDA-only. Lluna
allows installation and configuration on non-CUDA machines so workflows and
assets can be prepared there, but execution stops immediately with a clear CUDA
requirement and keeps the installed files.

## SeedVR2 runtime

SeedVR2 3B and 7B are reviewed built-in models sourced from the official
`ByteDance-Seed/SeedVR2-3B` and `ByteDance-Seed/SeedVR2-7B` Hugging Face
repositories. The official source is pinned to SeedVR commit
`e4de8c24441a67e1b7df56abea10645059bb1185`; that reviewed inference source is
vendored in `backend/ai/seedvr2/` and shipped with Lluna. Settings downloads
only the selected checkpoint, VAE, and Apex wheel into `models/seedvr2/ckpts/`,
then installs a separate Python 3.9/3.10 CUDA runtime. The worker launches the
bundled inference script in a cancellable subprocess, so SeedVR2's compiled
dependencies never mix with Lluna's Python 3.12 environment.

The official 3B and 7B checkpoints are large `.pth` files; they are not
converted to generic `safetensors` files. The 7B model is intended for
very-large-memory CUDA hardware. SeedVR2 is Apache-2.0, but its upstream model
card notes that these are prototype restoration models and that lightly
degraded inputs can occasionally become oversharpened.
