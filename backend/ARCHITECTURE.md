# Lluna backend structure

The backend is divided by ownership and side effects. A model reference can be
read without installing anything; an installer can download weights without
loading them; an AI runtime can execute an installed model without owning the
download policy.

```text
backend/
├── api/                  HTTP routes, auth, events, request dependencies
├── application/          bootstrap, preflight, application jobs
├── artifacts/             artifact grants, hashing, and workspace storage
├── configuration/         persisted application configuration and migrations
├── core/                  paths, atomic writes, release/build policy
├── diagnostics/           errors, redaction, logging, health/runtime probes
├── graph/                 node catalog, workflow compiler, validation, executor
├── hardware/              hardware detection and execution policy
├── media/                 masks, video, progress, and output paths
├── models/
│   ├── reference/         catalog, manifests, capabilities, runtime profiles
│   ├── service.py          control-plane lifecycle facade
│   ├── importer.py         user/Hugging Face model import
│   └── dynamic_registry.py user-model discovery and enablement
├── ai/
│   ├── architectures/     Lluna-owned neural-network implementations
│   ├── runtimes/           Lluna-owned inference bridges
│   └── seedvr2/            vendored Apache-2.0 SeedVR2 implementation
├── settings/
│   ├── schemas/            typed feature/model controls
│   └── presets.py          hardware-aware defaults
├── tools/
│   ├── installers/         model download and lifecycle implementations
│   ├── shared/             queues, auth, hardware/job utilities
│   ├── inference/          shared worker protocol/client/dispatch
│   ├── media/              FFmpeg, video, OCR, masks, subtitles
│   └── options/            graph-facing option resolution
├── inpaint/                inpainting model implementations
├── pipelines/              high-level media pipelines
├── services/               application services
└── updates/                signed update lifecycle
```

## Dependency direction

```text
API/application → services/graph/models
models/reference → core + hardware (declarative facts only)
tools/installers → models/reference + tools/shared
ai/runtimes → installers + media + ai/architectures
inference worker → ai/runtimes + pipelines
```

Weights are runtime data, not implementation source. In development they may
appear below `backend/models/` because that is the configured model store; in
packaged builds they live below Lluna's per-user data directory. The vendored
SeedVR2 source and small prompt embeddings are the only model implementation
assets shipped in `backend/ai/seedvr2/`. Large checkpoints are installed by the
corresponding installer.

The old root module names under `tools/` and `models/` are compatibility aliases
only. New imports must use the canonical subpackages shown above.
