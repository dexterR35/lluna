<p align="center">
  <img src="frontend/assets/app-icon/lluna.png" alt="Lluna logo" width="112" height="112" />
</p>

<h1 align="center">Lluna</h1>

<p align="center">
  A local-first, node-based workspace for image and video AI.
</p>

<p align="center">
  Build visual workflows, run them on your own hardware, and keep your media and models on your machine.
</p>

<p align="center">
  <img alt="Linux" src="https://img.shields.io/badge/Linux-supported-2ea44f?logo=linux&logoColor=white" />
  <img alt="Windows" src="https://img.shields.io/badge/Windows-supported-0078D6?logo=windows&logoColor=white" />
  <img alt="macOS" src="https://img.shields.io/badge/macOS-supported-000000?logo=apple&logoColor=white" />
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" />
  <img alt="Node.js" src="https://img.shields.io/badge/Node.js-22%2B-339933?logo=nodedotjs&logoColor=white" />
</p>

## Purpose

Lluna is a desktop application for practical, local AI-assisted media work. It turns common image and video operations into reusable visual workflows:

- remove subtitles, watermarks, and other burned-in text;
- upscale and restore images or video;
- improve low-light images;
- remove or composite backgrounds;
- select objects with clicks or natural-language descriptions; and
- generate images from prompts with locally installed diffusion models.


## Nodebase

 Connect nodes from left to right to describe the processing pipeline, then run the graph.

```text
Load Image  →  Select Object  →  Remove Background  →  Preview Image  →  Save Image
Load Video  →  Remove Text    →  Preview Video     →  Save Video
Prompt      →  Generate Image →  Upscale Image     →  Save Image
```

The main node groups are:

| Group | Examples |
| --- | --- |
| **Input** | Load Image, Load Images, Load Video, Load Mask, Prompt |
| **Process** | Generate Image, Upscale, Fix Low Light, Select Object, Remove Text, Remove Background, Composite |
| **Output** | Preview Image, Preview Video, Preview Mask, Preview Alpha, Save Image, Save Video |

Workflows are saved as `*.lluna.json` files. `Load Images` supports ordered batches of up to 10 images.

## Requirements

For running Lluna from source, install:

- **64-bit Python 3.12**;
- **Node.js 22 or newer** and **npm 10 or newer**;
- an internet connection for the initial dependency and model downloads; and
- enough free disk space for the models you select.

GPU acceleration is optional. Current drivers are required for GPU backends;

| Platform | Runtime profile | Acceleration |
| --- | --- | --- |
| Linux | CPU or CUDA | NVIDIA CUDA when an NVIDIA driver is available |
| Windows | CPU, CUDA, or DirectML | NVIDIA CUDA or DirectML-compatible hardware |
| macOS | CPU or MPS | Apple Silicon/Metal through PyTorch MPS where supported |

Large restoration and generation models are hardware-dependent. 

## First-time installation

### 1. Clone the repository

```bash
git clone https://github.com/dexterR35/lluna.git
cd lluna
```

### 2. Install Lluna

The installer creates the `llunaEnv` Python environment, installs the correct dependency profile, validates the bundled assets, and installs the desktop dependencies.

**Linux or macOS**

```bash
./install.sh --mode auto
```

**Windows**

```bat
install.bat
```

Use an explicit profile when needed:

```bash
./install.sh --mode cpu                 # CPU only
./install.sh --mode cuda --yes          # NVIDIA CUDA
./install.sh --mode directml --yes      # Windows DirectML
./install.sh --mode mps --yes           # macOS Metal/MPS
```

On Windows, the equivalent command is `install.bat --mode cuda --yes`, for example. `--yes` makes the selection non-interactive. With `--mode auto`, the installer detects the available hardware and chooses a suitable profile.

The installer runs `npm install` for the desktop UI automatically. If you are developing the UI separately, you can refresh its dependencies with:

```bash
npm install --allow-git=all
```

### 3. Start Lluna

```bash
npm run dev
```


## Installing models

Lluna separates application installation from model installation. This keeps the initial setup smaller and lets you install only the capabilities you need.

1. Open **Settings → Models** (or **Settings → Local model manager**).
2. Select a model and choose **Install**.
3. Wait for the download queue to finish in **Activity → Downloads**.
4. Enable the model if it is not enabled automatically.
5. Reopen the node and select the model in its model dropdown.

The default installer does not download optional models. To schedule the recommended starter set during installation, run:

```bash
./install.sh --mode auto --schedule-default-models
```

The starter set is Real-ESRGAN x2, MIRNet LOL, and the fast SAM2 + Grounding DINO selection pair. Models, settings, and workflows are stored in Lluna's user data area and survive application updates.

## Which models do I need?

The following matrix maps each capability to its required models. **Bundled** models are included in the repository/package. **Optional** models are downloaded from Settings when you enable the corresponding feature.

| Capability / node | Required models | Status and notes |
| --- | --- | --- |
| Retouch a masked image | **LaMa** | Bundled; CPU-compatible |
| Remove text from an image | **PaddleOCR Server** + **LaMa** | Bundled; detects text, then inpaints it |
| Remove subtitles/text from video | **PaddleOCR Server** + **STTN Auto** | Bundled; preserves source timing and audio when possible |
| Upscale an image | **Real-ESRGAN x2** or **x4** | Optional; a good lightweight starting point |
| High-quality image restoration | **SUPIR v0** | Optional; CUDA only, about 75 GB, roughly 32 GB RAM and 12 GB VRAM minimum |
| One-step image/video restoration | **SeedVR2 3B** or **7B** | Optional; CUDA only; about 14.6 GB/66.9 GB and 24 GB/48 GB VRAM minimum |
| Fix low-light images | **MIRNet LOL** | Optional; CPU, CUDA, DirectML, or MPS |
| Select an object | **SAM2** + **Grounding DINO** | Optional; install the fast pair first, or the large/base pair for higher quality |
| Remove an image/video background | **BiRefNet** variant | Optional; variants include standard, Dynamic, HR, HR Matting, Lite 2K, and Matting |
| Generate an image | One **FLUX** or **Qwen-Image** model | Optional; generation models are large and generally require CUDA |
| Composite foreground and background | None | Uses already available image inputs |

### Generation model choices

Install only one generation model to begin with:

| Model | Best for | Approximate requirement |
| --- | --- | --- |
| **FLUX.2 Klein Base 4B** | Recommended starting point | About 16 GB RAM and 12 GB VRAM |
| **FLUX.2 Klein 4B / 9B** | General image generation | More memory as model size increases |
| **FLUX.2 Klein 9B FP8** | Lower-weight 9B option | About 32 GB RAM and 10 GB VRAM |
| **FLUX.2 Dev** | Higher-capacity generation | About 64 GB RAM; gated, non-commercial license |
| **Qwen-Image** | Alternative general image generation | About 64 GB RAM and 12 GB VRAM |

Generation models may require accepting the upstream license or gated-model terms. Review the model card before installation and use; model licenses are separate from the Lluna license.

### Custom Hugging Face and local models

From **Settings → Models → Add model**, you can add a reviewed Hugging Face repository, a local model folder, or a supported weight file (`.safetensors`, `.pth`, `.pt`, `.ckpt`, or `.bin`). Lluna checks metadata, compatibility, disk requirements, and the declared capability before enabling a custom model.

Remote repository code is disabled by default, SafeTensors is preferred, and pickle-capable weights require explicit opt-in. A model repository's `requirements.txt` is never installed into Lluna's main environment. See the [model platform guide](backend/models/reference/PLATFORM.md) and [model reference](backend/models/reference/README.md) for the manifest and capability rules.

## Common workflows

```text
Remove image text:
Load Image → Remove Text from Image → Preview Image → Save Image

Remove video subtitles:
Load Video → Remove Text from Video → Preview Video → Save Video

Make a transparent cut-out:
Load Image → Remove Background → Preview Alpha → Save Image

Generate and upscale:
Prompt → Generate Image → Upscale Image → Preview Image → Save Image

Select and retouch:
Load Image → Select Object → LaMa Retouch → Preview Image → Save Image
```

If a node's model list is empty, install the model listed in the matrix, enable it in Settings, and reopen the node options.

## Development commands

```bash
npm run build           # Build the production UI bundle
npm run lint            # Lint the frontend
npm run check           # Frontend checks and static guards
npm run test:frontend   # Frontend tests
npm run test:backend    # Python backend tests
npm test                # Frontend and backend tests
```

For frozen sidecars and packaged builds, see [packaging/build.py](packaging/build.py). For the backend layout, see [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md).

## Updating

```bash
git pull
./install.sh --mode auto       # Use install.bat on Windows
npm install --allow-git=all
npm run dev
```

Updating the source does not remove installed models, settings, or workflows.

## Privacy and licensing

Lluna uses a loopback API with a per-launch token and a sandboxed Electron renderer. Your media remains local unless you explicitly export or copy it elsewhere. Model downloads go to the upstream providers you select.

Source is distributed under the repository [LICENSE](LICENSE). Model weights and third-party components have their own terms; review [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and each model's upstream license before use or redistribution.
