# Tools boundaries

The tools package is organized by responsibility rather than model name:

```text
tools/
├── installers/        # model discovery, downloads, verification, lifecycle
│   ├── birefnet.py
│   ├── enhance.py
│   ├── generate.py
│   ├── low_light.py
│   ├── select_object.py
│   ├── seedvr2.py
│   └── supir.py
├── shared/            # download queue, Hugging Face auth, hardware, jobs
├── inference/         # one shared worker, protocol, and control-plane client
├── media/             # FFmpeg, video I/O, masks, OCR, and subtitle helpers
└── options/           # typed feature controls projected into graph nodes
```

Installer modules must not perform inference. Inference modules must not own
model download policy. The root-level legacy module names are thin aliases for
backward-compatible saved workflows and third-party integrations. The actual
model inference bridges live under `backend/ai/runtimes/`.
