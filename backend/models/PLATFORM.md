# Midgard model platform

Midgard-managed user models live in `models/custom/<model-id>/`. Each folder
contains a `midgard-model.json` manifest and its local weights. In development,
`models` is `backend/models`; packaged builds use the operating system's Midgard
application-data directory.

```text
models/
├── custom/                 # installed/imported user models
│   └── <model-id>/
│       ├── midgard-model.json
│       ├── .midgard-installed
│       └── <weights and configuration>
├── .staging/               # incomplete installs; never used for inference
├── .quarantine/            # reserved for failed/untrusted imports
└── .download_cache/        # disposable provider download cache
```

The manifest format is defined by `model-manifest.schema.json`. Model ids are
stable workflow identifiers and cannot be changed after registration.

## Capability contracts

Every usable model declares a `variant` and `capabilities` contract. Midgard
resolves facts in this strict order:

1. a reviewed Midgard catalog contract or user-reviewed manifest;
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
Midgard never attempts to run them as ordinary checkpoints.

## Runtime profiles

- `midgard-native`: reviewed inference code shipped with Midgard.
- `diffusers-torch`: Diffusers, Transformers, Accelerate, and the selected Torch build.
- `transformers-torch`: Transformers and the selected Torch build.
- `paddle`: the CPU or CUDA Paddle package selected by the installer.

Repository `requirements.txt` files are never executed automatically. Hugging
Face installs are analyzed first, pinned to the returned commit, restricted to
reviewed files, downloaded into `.staging`, verified, and promoted atomically.
Remote Python code and pickle-capable weights are disabled by default.

Folders placed directly under `custom/` are detected automatically. A folder
without a manifest is shown as **Needs configuration** so the user can select a
task, runtime, variant, and capabilities. Standalone files should be imported
through **Add model**; this copies them into a managed folder and creates the
manifest.

## SUPIR runtime

SUPIR is a reviewed built-in adapter pinned to official source commit
`bda91af2000042f8bedfec8897d92917e67c1d88`. It never installs the upstream
`requirements.txt` into Midgard. A dedicated Python 3.8–3.10 environment holds
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
pickle-capable PyTorch loading. Midgard therefore runs them only inside the
isolated, pinned SUPIR worker and never treats the mirror's incomplete model card
as executable configuration.

The Upscale node exposes the original sampler and restoration controls, plus
quality/fidelity presets, LLaVA captioning, gamma correction, precision, and
tiled-VAE memory controls. The official implementation is CUDA-only. Midgard
allows installation and configuration on non-CUDA machines so workflows and
assets can be prepared there, but execution stops immediately with a clear CUDA
requirement and keeps the installed files.
