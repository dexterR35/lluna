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

---

## What it's for

Wire nodes together on a canvas and run the graph. Everything happens on your machine — an Electron app talking to a local Python backend over loopback. Your media, models, and workflows never leave your computer.

- **Clean up** — remove subtitles, watermarks, and burned-in text from images and video
- **Restore** — upscale images and video, fix low light, one-step restoration with SUPIR or SeedVR2
- **Cut out** — remove or replace backgrounds, select objects by click or description, matte and composite
- **Create** — generate and edit images with FLUX.2 or Qwen-Image
- **Describe** — caption an image with a vision-language model you bring yourself

<p align="center">
  <img src="example/test1.png" alt="Lluna node-based workflow editor" width="49%" />
  <img src="example/test2.png" alt="Lluna local model manager" width="49%" />
</p>

---

## Install

You need **Python 3.12**, **Node.js 22+**, and an internet connection. Nothing else — the installer detects your hardware and picks its own dependencies.

```bash
git clone https://github.com/dexterR35/lluna.git
cd lluna
./install.sh          # install.bat on Windows
npm run dev
```

That's it. **No CUDA Toolkit, no manual driver setup, no choosing a build.** An NVIDIA GPU gets the CUDA wheels automatically; anything else gets CPU wheels, and Apple silicon gets MPS. The CUDA wheels contain the CPU kernels too, so a GPU install covers both — there is no second install to add.

No models are downloaded during install. Add `--schedule-default-models` to queue a small starter set (Real-ESRGAN x2, MIRNet, SAM2 + Grounding DINO).

<details>
<summary>Forcing a specific build</summary>

```bash
./install.sh --mode cpu        # CPU wheels even on a GPU machine
./install.sh --mode directml   # AMD/Intel GPUs on Windows
./install.sh --mode mps        # Apple silicon
```
</details>

### Platform support

| | Acceleration | Notes |
| --- | --- | --- |
| **Linux** | CUDA, CPU | Everything works here, including SUPIR and SeedVR2 |
| **Windows** | CUDA, DirectML, CPU | All models except SeedVR2 |
| **macOS** | MPS, CPU | Apple silicon via Metal; no CUDA-only models |

**SeedVR2 is Linux-only.** It requires flash-attn and Apex, which upstream publishes as Linux wheels only. Everything else runs on all three platforms.

Some models run in their own isolated Python environment (SUPIR, SeedVR2, BiRefNet) because their pinned dependencies conflict with the app's. Lluna builds those for you and fetches the Python version they need — you never install a second Python by hand.

---

## Which models work on your machine

**No GPU?** These 12 run on CPU. Slower, but fully functional.

| Model | Used for |
| --- | --- |
| **BiRefNet** ×6 (Standard, Dynamic, HR, HR Matting, Lite 2K, Matting) | Background removal, matting |
| **Real-ESRGAN x2 / x4** | Image and video upscaling |
| **LaMa** | Masked retouching |
| **MIRNet LOL** | Low-light restoration |
| **PaddleOCR** Server / Mobile | Text detection for subtitle removal |

**Have an NVIDIA GPU?** Everything above runs faster, plus:

| VRAM | Unlocks |
| --- | --- |
| **4.5 GB** | SAM2, Grounding DINO (object selection), STTN, ProPainter (video inpainting) |
| **10–12 GB** | SUPIR, FLUX.2 Klein, FLUX.2 Dev, Qwen-Image |
| **24 GB** | SeedVR2 3B |
| **48 GB+** | SeedVR2 7B |

Lluna checks this for you. A model your machine can't run is marked incompatible with the reason; a model that fits but is short on free memory right now gets a warning, not a block.

### What's best

| You want to… | Start with | Why |
| --- | --- | --- |
| **Upscale an image** | Real-ESRGAN x2 | Fast, runs anywhere, no download tax |
| **Restore a damaged photo** | SUPIR v0 | Best quality by a wide margin — 75 GB disk, 12 GB VRAM, non-commercial |
| **Upscale video** | SeedVR2 3B | One-step, temporally stable; Linux + 24 GB VRAM |
| **Remove a background** | BiRefNet Standard | Best quality/speed balance; use HR Matting for hair and soft edges |
| **Generate an image** | FLUX.2 Klein | Recommended default at 12 GB VRAM; Klein 9B FP8 is lighter at 10 GB |
| **Select an object** | SAM2 + Grounding DINO (fast pair) | Click or describe what you want; swap to the large pair for quality |
| **Remove subtitles** | PaddleOCR + STTN | Detection and inpainting run together automatically |

Full disk footprint if you install **every** model: roughly **157 GB**, dominated by SUPIR (75 GB) and SeedVR2 7B (67 GB). Install what you need.

Gated models (FLUX.2 Dev) need a Hugging Face token — accept the license upstream, then connect your account under **Settings → Models → Hugging Face**.

---

## The nodes

| Group | Nodes |
| --- | --- |
| **Input** | Load Image, Load Images, Load Video, Load Mask, Prompt, Number, Integer, Boolean, LLaVA Caption, Describe Image |
| **Image** | Generate Image, Edit Image, Upscale Image, Remove Background, Fix Low Light, Composite Background, LaMa Retouch, Remove Text from Image |
| **Video** | Upscale Video, Remove Text from Video, Remove Background from Video |
| **Mask** | Select Object |
| **Output** | Save Image, Save Video |

Ports connect left to right, and every node declares the model, capability, and hardware it needs — so bad connections and missing models are caught before anything runs. Independent branches of a graph run in parallel; model-backed nodes take turns on the GPU. Workflows save as `*.lluna.json`.

```text
Load Image  → Remove Text from Image → Save Image
Load Video  → Remove Text from Video → Save Video
Load Image  → Remove Background      → Save Image
Prompt      → Generate Image → Upscale Image → Save Image
Load Image  → Select Object  → LaMa Retouch  → Save Image
Load Image  → Describe Image → Generate Image → Save Image
```

---

## Results

<p align="center">
  <img src="example/birefnet_ex2.png" alt="BiRefNet foreground and mask segmentation examples" width="49%" />
  <img src="example/birfet.png" alt="BiRefNet object mask example" width="49%" />
</p>

<p align="center">
  <img src="example/bifrent_2.png" alt="BiRefNet foreground and mask output example" width="72%" />
</p>

<p align="center">
  <img src="example/images_supir.jpeg" alt="SUPIR image restoration before and after example" width="49%" />
  <img src="example/real_ergan.png" alt="Real-ESRGAN image upscaling before and after example" width="49%" />
</p>

<p align="center">
  <img src="example/seed_vr2_image_upscale.png" alt="SeedVR2 image upscaling example" width="49%" />
  <img src="example/seed_vr2_video_upscale.png" alt="SeedVR2 video upscaling example" width="49%" />
</p>

<p align="center">
  <img src="example/flux2.avif" alt="FLUX.2 generated image examples" width="49%" />
  <img src="example/flux22.avif" alt="More FLUX.2 generated image examples" width="49%" />
</p>

---

## Adding models

Open **Settings → Models**, pick a model, select **Install**, and watch **Activity → Downloads**. Installed models persist across app updates until you uninstall them.

**Your own models** go through **Settings → Models → Add model** — a Hugging Face repo URL, a local folder, or a single weight file (`.safetensors`, `.pth`, `.pt`, `.ckpt`, `.bin`, `.onnx`).

Lluna identifies a custom model from a reviewed catalog entry, its model card and config, or safe inspection of its declarative config files — **it never imports model code or loads weights just to identify them**. A model stays *Needs configuration* until that review passes. SafeTensors is preferred; pickle-carrying formats and a repository's own `requirements.txt` are never trusted or installed automatically.

See the [model platform guide](backend/models/reference/PLATFORM.md) and the [model reference](backend/models/reference/README.md).

---

## Development

```bash
npm run dev             # Run the app
npm run build           # Build the production UI
npm run lint            # Lint the frontend
npm run check           # Frontend type checks and static guards
npm test                # Frontend and backend tests
```

Backend structure: [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md). Packaged builds: [packaging/build.py](packaging/build.py).

**Update:**

```bash
git pull
./install.sh
npm install --allow-git=all
npm run dev
```

Updating never removes your models, settings, or workflows.

---

## Privacy

The API binds to loopback with a token generated each launch, and the Electron renderer is sandboxed. Your media stays on your computer unless you export it. Model downloads go directly to the upstream provider you chose.

## License

Source code: [LICENSE](LICENSE). Model weights and third-party components carry their own licenses — read [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and each model card before use or redistribution. Several models (SUPIR, FLUX.2 Dev) are non-commercial.
