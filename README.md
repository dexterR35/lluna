# Midgard

Midgard is a local-first Electron node editor for AI media workflows. Electron is the only desktop shell; a hidden Python 3.12 control plane validates and executes graphs through the existing persistent inference worker. Media stays on the machine.

## Architecture

- Electron Forge + Vite owns lifecycle, native menus/dialogs, secure IPC, window state, and the frozen Python sidecar.
- React 19 in JavaScript/JSX renders the `@xyflow/react` workflow editor.
- Tailwind CSS and Midgard-owned components provide the entire UI system.
- FastAPI binds to an ephemeral `127.0.0.1` port with a random per-launch token.
- WebSocket events carry progress/log metadata; artifacts and path grants keep large media out of JSON/IPC.
- The existing `InferClient` remains the one-worker GPU scheduling boundary.


## Quick install and run

Requirements: Python 3.12 (64-bit), Node.js 22+, npm 10+.

Minimal dev setup:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-control-plane.txt -r requirements-test-core.txt
npm install --allow-git=all
npm run dev
```

Full AI runtime setup (recommended for actual model usage):

```bash
./install.sh --mode auto
npm run dev
```

On Windows:

```bash
install.bat
npm run dev
```

`npm run dev` starts Electron. Electron starts the Python backend automatically.

On Linux, Electron requires a working Chromium sandbox. If the npm-installed `chrome-sandbox` helper is not owned by root with mode `4755` and unprivileged user namespaces are disabled, configure the helper through your system administrator before normal development. The automated Playwright smoke test uses `--no-sandbox` only inside its isolated test launch; packaged and normal development windows keep sandboxing enabled.

## Using models and nodes

1. Open **Models -> Manage Models**.
2. Install the optional models you want (background removal, generation, upscaling, etc.).
3. Keep models enabled so they appear in node model dropdowns.
4. Build a graph from left to right, then run:
   - Input nodes: `Load Image`, `Load Images`, `Load Video`, `Prompt`
   - Processing nodes: `Remove Background`, `Generate Image`, `Upscale Image`, `Fix Low Light`, `Composite Background`
   - Output nodes: `Preview Image`, `Preview Video`, `Save Image`, `Save Video`

Simple image workflow example:

`Load Images -> Remove Background -> Composite Background -> Preview Image -> Save Image`

Notes:
- Models are local on your machine (not cloud API calls).
- The Downloads panel shows active/queued model installs.
- If a node says a model is unavailable, install + enable it in the Models dialog.

## Commands

```bash
npm run build          # production renderer bundle
npm run test:frontend  # Vitest + Testing Library
npm run test:backend   # pytest
npm run check          # strict JS check plus migration guards
npm run lint
python scripts/static_guards.py
python scripts/export_contracts.py
python packaging/build.py --validate-only
python packaging/build.py --clean  # frozen sidecar + Electron Forge makers
```

## Local security model

The renderer has no Node integration, runs with context isolation and sandboxing, and receives a narrow frozen preload API. Navigation and new windows are denied except fixed project links. The API listens only on loopback; every `/api` HTTP request and WebSocket connection requires the random launch token. Desktop paths enter Python only through session-scoped grants.

## Workflow files

Workflows use `*.midgard.json`, schema version 1. Saves and autosaves are atomic. Functional settings use schema version 2 and migrate once from the old configuration with a timestamped backup. Installed models/settings live outside packaged application resources and survive upgrades.

## Models and licensing

Models are not cloud services. Install only models whose license is appropriate for your use. Bundled and optional model metadata is defined by the Python registry; the Models screen exposes installation state and actions. See [Third-party notices](THIRD_PARTY_NOTICES.md).

### Models available in this app

Core bundled runtimes:
- `sttn-auto` (video text removal)
- `sttn-detection`
- `lama`
- `propainter`
- `paddleocr-server`
- `paddleocr-mobile`

Optional/installable model groups:
- Background removal (`bg-remove:*`):
  - `birefnet-general`, `birefnet-general-lite`, `birefnet-portrait`
  - `birefnet-massive`, `birefnet-dis`, `birefnet-hrsod`, `birefnet-cod`
  - `u2net`, `u2netp`, `u2net_human_seg`, `u2net_cloth_seg`
  - `isnet-general-use`, `isnet-anime`, `silueta`, `bria-rmbg`
- Image generation (`generate:*`):
  - `FLUX.2-klein-base-4B`, `FLUX.2-klein-4B`
  - `FLUX.2-klein-base-9B`, `FLUX.2-klein-9B`
  - `FLUX.2-dev`, `FLUX.2-klein-9b-fp8`, `Qwen-Image`
- Upscale:
  - `realesrgan-x2`, `realesrgan-x4`
- Low light:
  - `mirnet`
- Object select helpers:
  - `sam2`, `grounding-dino`
