<p align="center">
  <img src="frontend/assets/app-icon/lluna.png" alt="Lluna logo" width="112" height="112" />
</p>

<h1 align="center">Lluna</h1>

<p align="center">
  A local, node-based desktop app for image and video AI workflows.
</p>

<p align="center">
  <img alt="Linux" src="https://img.shields.io/badge/Linux-supported-2ea44f?logo=linux&logoColor=white" />
  <img alt="Windows" src="https://img.shields.io/badge/Windows-supported-0078D6?logo=windows&logoColor=white" />
  <img alt="macOS" src="https://img.shields.io/badge/macOS-supported-000000?logo=apple&logoColor=white" />
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" />
  <img alt="Node.js" src="https://img.shields.io/badge/Node.js-22%2B-339933?logo=nodedotjs&logoColor=white" />
</p>

Lluna lets you build image and video processing pipelines by connecting nodes. It runs on your own computer, and your media, models, settings, and workflows stay on your machine.

You can use it to:

- remove subtitles, watermarks, and other burned-in text;
- upscale and restore images or video;
- improve low-light images;
- remove backgrounds and create composites;
- select objects with clicks or text descriptions; and
- generate images with locally installed diffusion models.

## See it in action

<p align="center">
  <img src="example/test1.png" alt="Lluna node-based workflow editor" width="49%" />
  <img src="example/test2.png" alt="Lluna local model manager" width="49%" />
</p>

## How it works

Add nodes to the workspace, connect them from left to right, and run the graph.

```text
Load Image → Select Object → Remove Background → Preview Image → Save Image
Load Video → Remove Text → Preview Video → Save Video
Prompt → Generate Image → Upscale Image → Save Image
```

Nodes are split into three groups:

| Group | Included nodes |
| --- | --- |
| **Input** | Load Image, Load Images, Load Video, Load Mask, Prompt |
| **Process** | Generate Image, Upscale, Fix Low Light, Select Object, Remove Text, Remove Background, Composite |
| **Output** | Preview Image, Preview Video, Preview Mask, Preview Alpha, Save Image, Save Video |

Workflows are stored as `*.lluna.json` files. The **Load Images** node accepts ordered batches of up to 10 images.

## Requirements

Before installing Lluna from source, make sure you have:

- 64-bit Python 3.12;
- Node.js 22 or newer;
- npm 10 or newer;
- an internet connection for the first installation and model downloads; and
- enough disk space for the models you plan to install.

A GPU is optional. Lluna can run on CPU, but larger restoration and generation models need supported hardware and recent drivers.

| Platform | Available profiles | GPU acceleration |
| --- | --- | --- |
| Linux | CPU or CUDA | NVIDIA CUDA |
| Windows | CPU, CUDA, or DirectML | NVIDIA CUDA or DirectML-compatible hardware |
| macOS | CPU or MPS | Apple Silicon/Metal through PyTorch MPS, where supported |

## Install

### 1. Clone the repository

```bash
git clone https://github.com/dexterR35/lluna.git
cd lluna
```

### 2. Run the installer

The installer creates the `llunaEnv` Python environment, chooses the appropriate dependency profile, checks the bundled assets, and installs the desktop dependencies.

#### Linux and macOS

```bash
./install.sh --mode auto
```

If the script is not executable, run:

```bash
chmod +x install.sh
./install.sh --mode auto
```

#### Windows

```bat
install.bat
```

The `auto` mode detects the available hardware. You can also choose a profile yourself:

```bash
./install.sh --mode cpu
./install.sh --mode cuda --yes
./install.sh --mode directml --yes
./install.sh --mode mps --yes
```

On Windows, use the same options with `install.bat`, for example:

```bat
install.bat --mode cuda --yes
```

The `--yes` option skips interactive confirmation.

### 3. Start Lluna

```bash
npm run dev
```

The installer already runs `npm install`. If you only need to refresh the desktop dependencies, use:

```bash
npm install --allow-git=all
```

## Install models

Optional models are not downloaded during the normal installation. This keeps the first setup smaller and lets you install only what your workflows need.

To install a model:

1. Open **Settings → Models** or **Settings → Local model manager**.
2. Find the model you want and select **Install**.
3. Check **Activity → Downloads** and wait for the download to finish.
4. Enable the model if it is not enabled automatically.
5. Reopen the relevant node and select the model from its dropdown.

To queue a useful starter set while installing Lluna, run:

```bash
./install.sh --mode auto --schedule-default-models
```

This schedules Real-ESRGAN x2, MIRNet LOL, and the fast SAM2 + Grounding DINO pair.

Installed models, settings, and workflows are stored in Lluna's user data directory and are kept when you update the application.

## Models by feature

If a node has an empty model list, install and enable the model shown for that feature, then reopen the node.

| Feature or node | Required model | Notes |
| --- | --- | --- |
| Retouch a masked image | **LaMa** | Bundled; works on CPU |
| Remove text from an image | **PaddleOCR Server** + **LaMa** | Bundled; detects the text and inpaints the area |
| Remove subtitles or text from video | **PaddleOCR Server** + **STTN Auto** | Bundled; keeps the original timing and audio when possible |
| Upscale an image | **Real-ESRGAN x2** or **x4** | Optional; x2 is a good first choice |
| High-quality image restoration | **SUPIR v0** | Optional; CUDA only; about 75 GB disk, 32 GB RAM, and 12 GB VRAM minimum |
| Restore image or video in one step | **SeedVR2 3B** or **7B** | Optional; CUDA only; about 14.6 GB/66.9 GB disk and 24 GB/48 GB VRAM minimum |
| Fix low-light images | **MIRNet LOL** | Optional; supports CPU, CUDA, DirectML, and MPS |
| Select an object | **SAM2** + **Grounding DINO** | Optional; start with the fast pair, or use the large/base pair for better quality |
| Remove an image or video background | **BiRefNet** | Optional; standard, Dynamic, HR, HR Matting, Lite 2K, and Matting variants are available |
| Generate an image | One **FLUX** or **Qwen-Image** model | Optional; large models that generally need CUDA |
| Composite a foreground and background | None | Uses image inputs already loaded in the graph |

### Model examples

#### Background removal with BiRefNet

<p align="center">
  <img src="example/birefnet_ex2.png" alt="BiRefNet foreground and mask segmentation examples" width="49%" />
  <img src="example/birfet.png" alt="BiRefNet object mask example" width="49%" />
</p>

<p align="center">
  <img src="example/bifrent_2.png" alt="BiRefNet foreground and mask output example" width="72%" />
</p>

#### Image restoration and upscaling

<p align="center">
  <img src="example/images_supir.jpeg" alt="SUPIR image restoration before and after example" width="49%" />
  <img src="example/real_ergan.png" alt="Real-ESRGAN image upscaling before and after example" width="49%" />
</p>

#### SeedVR2 image and video upscaling

<p align="center">
  <img src="example/seed_vr2_image_upscale.png" alt="SeedVR2 image upscaling example" width="49%" />
  <img src="example/seed_vr2_video_upscale.png" alt="SeedVR2 video upscaling example" width="49%" />
</p>

## Choosing a generation model

Generation models are large, so start with one.

| Model | Good choice when | Approximate requirement |
| --- | --- | --- |
| **FLUX.2 Klein Base 4B** | You want the recommended starting model | About 16 GB RAM and 12 GB VRAM |
| **FLUX.2 Klein 4B / 9B** | You want general image generation | Memory use increases with model size |
| **FLUX.2 Klein 9B FP8** | You want a lighter 9B option | About 32 GB RAM and 10 GB VRAM |
| **FLUX.2 Dev** | You have more memory and want a higher-capacity model | About 64 GB RAM; gated, non-commercial license |
| **Qwen-Image** | You want an alternative general-purpose model | About 64 GB RAM and 12 GB VRAM |

#### FLUX.2 examples

<p align="center">
  <img src="example/flux2.avif" alt="FLUX.2 generated image examples" width="49%" />
  <img src="example/flux22.avif" alt="More FLUX.2 generated image examples" width="49%" />
</p>

Some models require you to accept an upstream license or gated-model terms before downloading them. Model licenses are separate from Lluna's license, so check the model card before use or redistribution.

## Custom and local models

Open **Settings → Models → Add model** to add:

- a reviewed Hugging Face repository;
- a local model directory; or
- a supported weight file: `.safetensors`, `.pth`, `.pt`, `.ckpt`, or `.bin`.

Before enabling a custom model, Lluna checks its metadata, declared capability, compatibility, and disk requirements.

Remote repository code is disabled by default. SafeTensors is preferred, and formats that can contain Python pickle data require explicit approval. Lluna never installs a model repository's `requirements.txt` into its main environment.

For the full model format and manifest rules, see the [model platform guide](backend/models/reference/PLATFORM.md) and [model reference](backend/models/reference/README.md).

## Example workflows

### Remove text from an image

```text
Load Image → Remove Text from Image → Preview Image → Save Image
```

### Remove subtitles from a video

```text
Load Video → Remove Text from Video → Preview Video → Save Video
```

### Create a transparent cut-out

```text
Load Image → Remove Background → Preview Alpha → Save Image
```

### Generate and upscale an image

```text
Prompt → Generate Image → Upscale Image → Preview Image → Save Image
```

### Select and retouch an object

```text
Load Image → Select Object → LaMa Retouch → Preview Image → Save Image
```

## Development

```bash
npm run build           # Build the production UI
npm run lint            # Lint the frontend
npm run check           # Run frontend checks and static guards
npm run test:frontend   # Run frontend tests
npm run test:backend    # Run Python backend tests
npm test                # Run frontend and backend tests
```

See [packaging/build.py](packaging/build.py) for packaged builds and frozen sidecars. The backend structure is documented in [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md).

## Update

```bash
git pull
./install.sh --mode auto
npm install --allow-git=all
npm run dev
```

On Windows, use `install.bat --mode auto` instead of `./install.sh --mode auto`.

Updating the source does not remove your installed models, settings, or saved workflows.

## Privacy

Lluna runs its API on the local loopback interface with a token generated for each launch. The Electron renderer is sandboxed. Your media stays on your computer unless you choose to export or copy it elsewhere.

When you install a model, the download request is sent to the upstream provider you selected.

## License

Lluna's source code is distributed under the repository [LICENSE](LICENSE).

Model weights and third-party components use their own licenses. Read [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the upstream license for each model before using or redistributing it.
