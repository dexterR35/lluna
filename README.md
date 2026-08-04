<p align="center">
  <img src="frontend/assets/app-icon/midgard.png" alt="Midgard" width="96" height="96" />
</p>

# Midgard

Local node editor for image and video work. Drag nodes on a canvas, wire them together, run the graph. Models and media stay on your machine — nothing is uploaded to a cloud API.

<p align="center">
  <img alt="Linux" src="https://img.shields.io/badge/Linux-supported-2ea44f?logo=linux&logoColor=white" />
  <img alt="Windows" src="https://img.shields.io/badge/Windows-supported-0078D6?logo=windows&logoColor=white" />
  <img alt="macOS" src="https://img.shields.io/badge/macOS-supported-000000?logo=apple&logoColor=white" />
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" />
  <img alt="Node" src="https://img.shields.io/badge/Node.js-22%2B-339933?logo=nodedotjs&logoColor=white" />
</p>

---

## What you can do

| | |
|---|---|
| 🖼️ | Load one image or a batch (up to 10) |
| 🎬 | Load video |
| ✂️ | Remove backgrounds |
| 🧽 | Remove burned-in subtitles / text from images and video |
| ⬆️ | Upscale with Real-ESRGAN |
| 🌙 | Fix low-light shots |
| ✨ | Generate images from a prompt (FLUX / Qwen, optional installs) |
| 🎯 | Select objects (SAM2 + Grounding DINO) |
| 💾 | Preview and save results locally |
| 🔗 | Chain steps into reusable workflows (`.midgard.json`) |

Build left → right, hit **Run**. Progress shows in the Activity panel.

---

## Platforms

| OS | Notes |
|---|---|
| **Linux** | Primary development target. NVIDIA GPU optional but recommended for generation / heavy models. |
| **Windows** | Same install flow via `install.bat`. CUDA or DirectML when available. |
| **macOS** | Supported; Apple Silicon can use MPS where the stack allows. |

You need:

- **Python 3.12** (64-bit)
- **Node.js 22+** and **npm 10+**
- Disk space for models (optional models are large — install only what you use)
- GPU drivers if you want CUDA / DirectML / MPS acceleration (no separate CUDA Toolkit install)

---

## Install (first time)

### 1. Get the repo

```bash
git clone <your-midgard-repo-url>
cd midgard
```

### 2. Install the Python runtime + deps

This creates the env, picks CPU/CUDA/DirectML/MPS, and verifies bundled pieces.

**Linux / macOS**

```bash
./install.sh --mode auto
```

**Windows**

```bat
install.bat
```

Useful modes if you already know your hardware:

```bash
./install.sh --mode cpu
./install.sh --mode cuda --yes
./install.sh --mode directml --yes   # Windows
./install.sh --mode mps --yes        # macOS
```

### 3. Install the desktop UI

```bash
npm install --allow-git=all
```

That’s the first-time setup. Models you install later live outside the app folder and survive upgrades.

---

## Open the app

From the project root:

```bash
npm run dev
```

Electron starts, then boots the local Python backend on a loopback port. No separate server step.

First session tip:

1. Open **Settings → Local model manager**
2. Install something small to start (e.g. **birefnet-general** for background removal)
3. Enable it so it shows up in node dropdowns
4. Drop nodes from the library, connect them, press **Run**

Example graph:

`Load Images` → `Remove Background` → `Preview Image` → `Save Image`

---

## Update

Models, settings, and workflows are stored outside the packaged app resources. Updating the code does not wipe them.

```bash
git pull
./install.sh --mode auto    # or install.bat on Windows
npm install --allow-git=all
npm run dev
```

If a dependency group fails after an update, re-run the installer with the same `--mode` you normally use. Check **Activity → Downloads** if a model reinstall fails.

---

## Models — what they’re for

Everything below runs **locally**. Check each license before use ([third-party notices](THIRD_PARTY_NOTICES.md)).

### Bundled (ship with the app)

| Model | Job |
|---|---|
| **STTN Auto / Detection** | Video text / subtitle inpainting |
| **LaMa** | Still-image inpainting |
| **ProPainter** | Motion-aware video inpainting |
| **PaddleOCR Server / Mobile** | Find text regions for subtitle tools |

### Optional (install from Settings → Local model manager)

| Group | Examples | Job |
|---|---|---|
| **Background removal** | BiRefNet, U²-Net, ISNet, BRIA | Cut subjects out of photos |
| **Upscale** | Real-ESRGAN ×2 / ×4 | Sharper, larger images |
| **Low light** | MIRNet | Brighten / clean dark shots |
| **Generation** | FLUX.2 Klein, FLUX.2 Dev, Qwen-Image | Text → image (needs VRAM + disk) |
| **Object selection** | SAM2, Grounding DINO | Point / text-driven masks |

Install only what you need. One model downloads at a time; the queue is in **Activity → Downloads**.

---

## Nodes you’ll use most

**Input** — Load Image, Load Images (max 10), Load Video, Load Mask, Prompt  

**Process** — Remove Background, Generate Image, Upscale Image, Fix Low Light, Select Object, Remove Text from Image / Video, Composite Background  

**Output** — Preview Image / Video, Save Image / Video  

If a node’s model list is empty: install the model, turn it **Enabled**, then reopen the node options.

---

## Workflows & settings

- Workflows save as `*.midgard.json` (atomic save + autosave).
- App preferences and model defaults live under **Settings** (Editor, Runtime, Subtitle, Enhancement, …).
- Layout (library width, drawer height) is stored in the desktop UI.

---

## Dev commands

```bash
npm run build           # production UI bundle
npm run test:frontend
npm run test:backend
npm run check
npm run lint
```

Packaging / frozen sidecar: see `packaging/build.py`.

---

## Privacy in one line

Loopback API, per-launch token, sandboxed renderer, path grants for files. Your media does not leave the machine unless you copy it somewhere yourself.
