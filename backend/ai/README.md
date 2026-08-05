# AI implementations

`backend/ai/` contains model implementation code, separate from model
catalogs, storage, and installers.

```text
ai/
└── seedvr2/            # vendored Apache-2.0 SeedVR2 inference implementation
    ├── configs_3b/      # model configuration
    ├── configs_7b/
    ├── models/          # upstream neural network modules
    ├── projects/        # Lluna entry scripts and upstream pipelines
    └── *.pt             # small prompt embeddings shipped with the implementation
```

The large SeedVR2 checkpoints are never committed here. They are downloaded
by `backend/tools/installers/seedvr2.py` into managed model storage. This keeps
implementation source, model references, user-installed weights, and runtime
dependencies independently replaceable.
