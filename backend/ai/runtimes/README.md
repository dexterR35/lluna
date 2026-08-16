# AI runtimes

These modules are Lluna-owned inference boundaries. They load model weights,
manage model memory, and expose cancellable operations to the shared worker.

They are intentionally separate from:

- `backend/models/reference/`: model identity and capability declarations;
- `backend/tools/installers/`: downloads and lifecycle state;
- `backend/ai/seedvr2/`: vendored upstream SeedVR2 implementation source.

```text
ai/runtimes/
├── birefnet.py       # image/video background removal and alpha/mask output
├── realesrgan.py     # image upscaling
├── mirnet.py         # low-light restoration
├── diffusion.py      # local image generation pipelines
├── supir.py          # SUPIR control bridge
├── supir_process.py  # isolated SUPIR subprocess bridge
├── sam3.py           # isolated SAM 3.1 subprocess bridge
├── sam3_process.py   # isolated SAM 3.1 subprocess entry point
└── seedvr2.py        # isolated SeedVR2 subprocess bridge
```
