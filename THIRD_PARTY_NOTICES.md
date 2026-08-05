# Third-party notices

Lluna source is licensed under the repository `LICENSE`. Key desktop/runtime dependencies include Electron, React, React DOM, `@xyflow/react`, Tailwind CSS, Zustand, Zod, Lucide, FastAPI, Uvicorn, Pydantic, PyInstaller, and existing Python AI/media packages. Their upstream licenses apply; consult the installed package metadata and lockfiles for the exact release set.

Model weights are separate works and may have research-only, non-commercial, attribution, acceptable-use, or redistribution restrictions. Installing or enabling a model does not grant rights beyond its upstream license. Lluna does not upload media or models to a cloud inference service.

The UI is an independent Lluna implementation. No chaiNNer source, branding, icons, artwork, or GPL implementation code is included.

SeedVR and SeedVR2 source code and model cards are provided by ByteDance Seed
under Apache-2.0. The reviewed source is vendored in `backend/ai/seedvr2/` and
its upstream `LICENSE` is included there. Lluna downloads only the optional
weights and runtime dependencies after a user selects Install in Settings; the
upstream model license and usage terms remain applicable.
