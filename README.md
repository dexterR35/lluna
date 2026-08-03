# Midgard

Midgard is a local-first Electron node editor for AI media workflows. Electron is the only desktop shell; a hidden Python 3.12 control plane validates and executes graphs through the existing persistent inference worker. Media stays on the machine.

## Architecture

- Electron Forge + Vite owns lifecycle, native menus/dialogs, secure IPC, window state, and the frozen Python sidecar.
- React 19 in JavaScript/JSX renders the `@xyflow/react` workflow editor.
- Tailwind CSS and Midgard-owned components provide the entire UI system.
- FastAPI binds to an ephemeral `127.0.0.1` port with a random per-launch token.
- WebSocket events carry progress/log metadata; artifacts and path grants keep large media out of JSON/IPC.
- The existing `InferClient` remains the one-worker GPU scheduling boundary.

See [Electron architecture](docs/ELECTRON_ARCHITECTURE.md) and [implementation status](docs/IMPLEMENTATION_STATUS.md).

## Source development

Requirements: Python 3.12 (64-bit), Node.js 22+ and npm 10+.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-control-plane.txt -r requirements-test-core.txt
npm install --allow-git=all
npm run dev
```

`npm run dev` starts Electron; Electron starts Python invisibly and waits for `/ready` before opening the editor. There is no Python GUI launcher.

On Linux, Electron requires a working Chromium sandbox. If the npm-installed `chrome-sandbox` helper is not owned by root with mode `4755` and unprivileged user namespaces are disabled, configure the helper through your system administrator before normal development. The automated Playwright smoke test uses `--no-sandbox` only inside its isolated test launch; packaged and normal development windows keep sandboxing enabled.

For the full AI runtime and hardware-specific Torch/Paddle/ONNX profile:

```bash
./install.sh --mode auto
npm run dev
```

On Windows use `install.bat` and then `npm run dev`.

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
